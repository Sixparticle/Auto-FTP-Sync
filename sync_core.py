# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (Core Logic Module)

This module contains the backend logic for file detection, FTP operations,
and state management. It is designed to be used by a GUI or other frontends.

Author: Sixparticle
"""

import os
import sys
import json
import logging
import time
import socket
from ftplib import FTP, FTP_TLS, error_perm
from threading import Thread
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigManager:
    """Handles loading and saving of FTP configurations."""
    
    @staticmethod
    def get_config_path():
        """Returns the standard path for the config file."""
        # 获取 exe 文件所在目录（打包后）或脚本所在目录（开发时）
        if getattr(sys, 'frozen', False):
            # 打包后的 exe 文件
            base_path = os.path.dirname(sys.executable)
        else:
            # 开发环境中的 .py 文件
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, 'data.json')

    @staticmethod
    def load_servers():
        """Loads the list of server configurations."""
        config_path = ConfigManager.get_config_path()
        if not os.path.exists(config_path):
            return []
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Support both the new format and migrate the old one
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'servers' in data:
                    return data.get('servers', [])
                elif isinstance(data, dict) and 'host' in data:
                     # This looks like an old single-server config, wrap it
                    return [data]
            return []
        except (json.JSONDecodeError, IOError):
            logging.error(f"无法加载或解析配置文件: {config_path}")
            return []

    @staticmethod
    def save_servers(servers_data):
        """Saves the list of server configurations."""
        config_path = ConfigManager.get_config_path()
        try:
            # 如果文件已存在且是只读，先移除只读属性
            if os.path.exists(config_path):
                import stat
                os.chmod(config_path, stat.S_IWRITE | stat.S_IREAD)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                # Store in the new format
                json.dump({"servers": servers_data}, f, indent=4, ensure_ascii=False)
            
            # 确保文件是可读可写的
            import stat
            os.chmod(config_path, stat.S_IWRITE | stat.S_IREAD)
            return True
        except IOError as e:
            logging.error(f"无法保存配置文件到: {config_path}, 错误: {e}")
            return False

    @staticmethod
    def export_to_file(servers_data, file_path):
        """Export server configurations to a specified file."""
        try:
            # 如果文件已存在且是只读，先移除只读属性
            if os.path.exists(file_path):
                import stat
                os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({"servers": servers_data}, f, indent=4, ensure_ascii=False)
            
            # 确保文件是可读可写的
            import stat
            os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            return True
        except IOError as e:
            logging.error(f"无法导出配置到文件: {file_path}, 错误: {e}")
            return False

    @staticmethod
    def import_from_file(file_path):
        """Import server configurations from a specified file."""
        if not os.path.exists(file_path):
            logging.error(f"配置文件不存在: {file_path}")
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Support both the new format and simple list format
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'servers' in data:
                    return data.get('servers', [])
                elif isinstance(data, dict) and 'host' in data:
                    # Single server config, wrap it
                    return [data]
            return []
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"无法加载或解析配置文件: {file_path}, 错误: {e}")
            return None

class FTPUploader:
    """Handles all FTP operations."""
    def __init__(self, config):
        self.config = config
        self.ftp = None
        self.last_activity_time = 0  # 记录最后活动时间

    def connect(self):
        """Connects to the FTP server, with optional FTPS support."""
        try:
            host = self.config['host']
            # Manually resolve hostname to IP address first
            try:
                ip_address = socket.gethostbyname(host)
                logging.info(f"成功将主机名 '{host}' 解析为 IP 地址: {ip_address}")
            except socket.gaierror as e:
                logging.error(f"无法解析主机名 '{host}': {e}")
                raise e  # Re-raise to be caught by the outer block

            use_tls = self.config.get('secure', False)
            
            if use_tls:
                self.ftp = FTP_TLS()
            else:
                self.ftp = FTP()

            # 设置超时时间（30秒）防止连接长时间阻塞
            # Connect using the resolved IP address
            self.ftp.connect(ip_address, int(self.config.get('port', 21)), timeout=30)
            self.ftp.login(self.config['username'], self.config['password'])
            
            if use_tls:
                # self.ftp.prot_p()  # Temporarily disabled. Some servers reject this command.
                pass

            self.ftp.set_pasv(True)
            self.ftp.encoding = 'utf-8'
            self.ftp.cwd(self.config['remote_dir'])
            
            self.last_activity_time = time.time()  # 更新活动时间
            logging.info(f"FTP{'S' if use_tls else ''} 连接成功到 {host} ({ip_address})")
            return True
        except Exception as e:
            logging.error(f"FTP 连接失败: {e}")
            return False

    def is_connected(self):
        """检查FTP连接是否仍然有效"""
        if not self.ftp:
            return False
        try:
            # 发送 NOOP 命令检查连接
            self.ftp.voidcmd("NOOP")
            self.last_activity_time = time.time()
            return True
        except Exception:
            return False

    def reconnect_if_needed(self):
        """如果连接超时或断开，尝试重新连接"""
        # 如果距离上次活动超过20秒，先检查连接
        if time.time() - self.last_activity_time > 20:
            if not self.is_connected():
                logging.warning("FTP 连接已断开，尝试重新连接...")
                self.close()
                if self.connect():
                    logging.info("FTP 重新连接成功")
                    return True
                else:
                    logging.error("FTP 重新连接失败")
                    return False
        return True

    def _ensure_remote_dir(self, remote_path):
        # Ensure remote directory exists, creating it if necessary.
        remote_dir = os.path.dirname(remote_path).replace('\\', '/')
        if remote_dir:
            # Navigate to the base directory first
            self.ftp.cwd(self.config['remote_dir'])
            
            parts = remote_dir.split('/')
            for part in parts:
                if not part:
                    continue
                try:
                    # Try to enter the subdirectory
                    self.ftp.cwd(part)
                except error_perm:
                    # If it fails, create it and then enter
                    try:
                        self.ftp.mkd(part)
                        self.ftp.cwd(part)
                    except Exception as e:
                        logging.error(f"无法创建远程子目录 '{part}': {e}")
                        # Important: Go back to base dir before failing
                        self.ftp.cwd(self.config['remote_dir'])
                        return
            
            # After creating all subdirectories, return to the base remote directory
            self.ftp.cwd(self.config['remote_dir'])

    def upload_file(self, local_path, remote_path):
        try:
            # 在执行操作前检查并重连
            if not self.reconnect_if_needed():
                logging.error(f"  [上传失败] {remote_path}: 无法建立FTP连接")
                return False
            
            self._ensure_remote_dir(remote_path)
            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {remote_path}', f)
            self.last_activity_time = time.time()  # 更新活动时间
            logging.info(f"  [上传成功] {remote_path}")
            return True
        except FileNotFoundError:
            logging.warning(f"  [上传跳过] 文件已不存在: {local_path}")
            return False
        except Exception as e:
            logging.error(f"  [上传失败] {remote_path}: {e}")
            # 如果出现超时等错误，尝试重新连接
            if "timed out" in str(e).lower() or "connection" in str(e).lower():
                logging.warning("检测到连接问题，下次操作时将自动重连")
                self.last_activity_time = 0  # 强制下次重连
            return False

    def delete_file(self, remote_path):
        try:
            # 在执行操作前检查并重连
            if not self.reconnect_if_needed():
                logging.error(f"  [删除失败] {remote_path}: 无法建立FTP连接")
                return False
            
            self.ftp.delete(remote_path)
            self.last_activity_time = time.time()  # 更新活动时间
            logging.info(f"  [删除成功] {remote_path}")
            return True
        except error_perm as e:
            # It's often okay if the file is already gone.
            logging.warning(f"  [删除失败] {remote_path}: {e}. 可能文件已不存在。")
            return False
        except Exception as e:
            logging.error(f"  [删除失败] {remote_path}: {e}")
            # 如果出现超时等错误，尝试重新连接
            if "timed out" in str(e).lower() or "connection" in str(e).lower():
                logging.warning("检测到连接问题，下次操作时将自动重连")
                self.last_activity_time = 0  # 强制下次重连
            return False

    def delete_directory(self, remote_path):
        """递归删除远程目录及其所有内容"""
        try:
            # 在执行操作前检查并重连
            if not self.reconnect_if_needed():
                logging.error(f"  [删除目录失败] {remote_path}: 无法建立FTP连接")
                return False
            
            logging.info(f"  [开始删除目录] {remote_path}")
            
            # 先尝试用 nlst 获取目录内容（更简单可靠）
            try:
                # 切换到远程根目录
                self.ftp.cwd(self.config['remote_dir'])
                
                # 切换到目标目录
                self.ftp.cwd(remote_path)
                current_path = self.ftp.pwd()
                logging.info(f"  [当前目录] {current_path}")
                
                # 获取目录内容列表
                items = []
                try:
                    items = self.ftp.nlst()
                except error_perm:
                    # nlst 可能失败，使用 LIST
                    items = []
                    lines = []
                    self.ftp.retrlines('LIST', lines.append)
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 9:
                            name = ' '.join(parts[8:])
                            if name not in ['.', '..']:
                                items.append(name)
                
                # 删除目录中的所有内容
                for item in items:
                    if item in ['.', '..']:
                        continue
                    
                    item_path = f"{current_path}/{item}".lstrip('/')
                    
                    # 尝试判断是文件还是目录
                    try:
                        # 尝试切换到该路径，如果成功则是目录
                        self.ftp.cwd(item)
                        self.ftp.cwd('..')  # 返回
                        # 是目录，递归删除
                        logging.info(f"  [发现子目录] {item}")
                        self.delete_directory(item_path)
                    except error_perm:
                        # 不是目录，是文件，直接删除
                        try:
                            self.ftp.delete(item)
                            logging.info(f"  [删除文件] {item}")
                        except error_perm as e:
                            logging.warning(f"  [删除文件失败] {item}: {e}")
                
                # 返回父目录
                self.ftp.cwd(self.config['remote_dir'])
                
                # 删除空目录
                self.ftp.rmd(remote_path)
                logging.info(f"  [删除目录成功] {remote_path}")
                return True
                
            except error_perm as e:
                # 可能目录已经不存在或为空，尝试直接删除
                logging.info(f"  [尝试直接删除目录] {remote_path}")
                self.ftp.cwd(self.config['remote_dir'])
                self.ftp.rmd(remote_path)
                logging.info(f"  [删除空目录成功] {remote_path}")
                return True
            
        except error_perm as e:
            logging.warning(f"  [删除目录失败] {remote_path}: {e}. 可能目录已不存在。")
            # 确保返回根目录
            try:
                self.ftp.cwd(self.config['remote_dir'])
            except:
                pass
            return False
        except Exception as e:
            logging.error(f"  [删除目录失败] {remote_path}: {e}")
            # 确保返回根目录
            try:
                self.ftp.cwd(self.config['remote_dir'])
            except:
                pass
            return False

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                self.ftp.close()

class SyncHandler(FileSystemEventHandler):
    """Handles file system events and puts tasks into a queue."""
    def __init__(self, project_path, task_queue):
        self.project_path = project_path
        self.task_queue = task_queue
        # Added .vscode as per user request
        self.ignored_items = {'.ftp_config.json', '.sync_state.json', 'sync.log', '.vscode', '.git'}
        # Track known directories to handle delete events correctly
        self.known_directories = set()
        # 去重：记录最近的操作，防止短时间内重复
        self.recent_tasks = {}  # {(action, path): timestamp}
        self.debounce_seconds = 2  # 2秒内的相同操作会被忽略

    def _is_ignored(self, path):
        # Check if the path contains any of the ignored directory/file names.
        return any(ignored in path.replace('\\', '/').split('/') for ignored in self.ignored_items)

    def _queue_task(self, action, path):
        if self._is_ignored(path):
            return
        
        # 去重：检查是否在短时间内有相同的任务
        task_key = (action, path)
        current_time = time.time()
        
        if task_key in self.recent_tasks:
            last_time = self.recent_tasks[task_key]
            if current_time - last_time < self.debounce_seconds:
                # 忽略重复的任务
                return
        
        # 记录这次任务
        self.recent_tasks[task_key] = current_time
        
        # 清理过期的记录（保持字典大小合理）
        if len(self.recent_tasks) > 1000:
            expired_keys = [k for k, v in self.recent_tasks.items() if current_time - v > self.debounce_seconds * 2]
            for k in expired_keys:
                del self.recent_tasks[k]
        
        logging.info(f"检测到变更，加入队列: {action.upper()} -> {path}")
        self.task_queue.put((action, path))

    def on_created(self, event):
        if event.is_directory:
            # Track created directories
            self.known_directories.add(event.src_path)
            logging.info(f"检测到目录创建: {event.src_path}")
        else:
            self._queue_task('upload', event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._queue_task('upload', event.src_path)

    def on_deleted(self, event):
        # 当路径被删除后，event.is_directory 可能不准确
        # 检查我们是否追踪了这个路径为目录
        is_dir = event.is_directory or event.src_path in self.known_directories
        
        if is_dir:
            logging.info(f"检测到目录删除: {event.src_path}")
            self._queue_task('delete_dir', event.src_path)
            # 从追踪集合中移除
            self.known_directories.discard(event.src_path)
        else:
            logging.info(f"检测到文件删除: {event.src_path}")
            self._queue_task('delete', event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            # 更新目录追踪
            self.known_directories.discard(event.src_path)
            self.known_directories.add(event.dest_path)
            # 目录移动：删除旧目录，然后需要重新上传整个目录（这里简化处理）
            self._queue_task('delete_dir', event.src_path)
            # 注意：完整实现需要递归上传新目录的所有内容
            logging.warning(f"检测到目录移动: {event.src_path} -> {event.dest_path}. 已删除旧目录，请手动上传新目录内容。")
        else:
            self._queue_task('delete', event.src_path)
            self._queue_task('upload', event.dest_path)

class Watcher:
    """File system watcher that runs in a separate thread."""
    def __init__(self, project_path, ftp_config):
        self.project_path = os.path.abspath(project_path)
        self.ftp_config = ftp_config
        self.observer = None
        self.task_queue = None
        self.worker_thread = None
        self.observer_thread = None
        self.is_stopping = False

    def _ftp_task_processor(self):
        """Worker that processes tasks from the queue."""
        uploader = FTPUploader(self.ftp_config)
        
        # 首次连接，最多重试3次
        max_retries = 3
        for attempt in range(max_retries):
            if uploader.connect():
                break
            if attempt < max_retries - 1:
                logging.warning(f"FTP 连接失败，{2}秒后重试... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(2)
        else:
            logging.error("FTP 任务处理器无法连接，已达到最大重试次数，线程终止。")
            return

        logging.info("FTP 任务处理器已启动并连接成功。")

        while True:
            try:
                # 使用超时获取任务，这样可以定期检查连接状态
                task = self.task_queue.get(timeout=10)
            except:
                # 队列超时，发送保活命令
                if uploader.is_connected():
                    continue
                else:
                    # 连接断开，尝试重连
                    logging.warning("检测到连接断开，尝试重新连接...")
                    if not uploader.connect():
                        logging.error("重新连接失败，任务处理器继续等待...")
                    continue
            
            if task is None:  # Sentinel to stop the thread
                break

            action, local_path = task
            rel_path = os.path.relpath(local_path, self.project_path).replace('\\', '/')

            # 执行任务，如果失败则重试一次
            success = False
            for retry in range(2):  # 最多尝试2次
                if action == 'upload':
                    success = uploader.upload_file(local_path, rel_path)
                elif action == 'delete':
                    logging.info(f"执行文件删除: {rel_path}")
                    success = uploader.delete_file(rel_path)
                elif action == 'delete_dir':
                    logging.info(f"执行目录删除: {rel_path}")
                    success = uploader.delete_directory(rel_path)
                
                if success:
                    break
                elif retry == 0:
                    # 第一次失败，等待1秒后重试
                    logging.warning(f"操作失败，1秒后重试...")
                    time.sleep(1)

            self.task_queue.task_done()

        uploader.close()
        logging.info("FTP 任务处理器已停止。")

    def start(self):
        # Reset stopping flag
        self.is_stopping = False
        
        # Create new Observer and Queue for each start (Observer cannot be restarted)
        self.observer = Observer()
        self.task_queue = Queue()
        
        # Start the FTP worker thread
        self.worker_thread = Thread(target=self._ftp_task_processor, daemon=True)
        self.worker_thread.start()

        # Start the file system observer
        event_handler = SyncHandler(self.project_path, self.task_queue)
        
        # 初始化时扫描现有目录结构
        logging.info(f"正在扫描现有目录结构...")
        self._scan_existing_directories(event_handler)
        
        self.observer.schedule(event_handler, self.project_path, recursive=True)
        self.observer.start()  # This starts observer in its own thread automatically
        logging.info(f"开始监控目录: {self.project_path}")

    def _scan_existing_directories(self, handler):
        """扫描并记录所有现有的目录"""
        try:
            for root, dirs, files in os.walk(self.project_path):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    # 检查是否应该忽略
                    if not handler._is_ignored(dir_path):
                        handler.known_directories.add(dir_path)
            logging.info(f"已扫描 {len(handler.known_directories)} 个目录")
        except Exception as e:
            logging.warning(f"扫描目录结构时出错: {e}")

    def stop(self):
        """停止监控，使用非阻塞方式避免 GUI 冻结"""
        if self.is_stopping:
            return
        
        self.is_stopping = True
        logging.info("正在停止监控...")
        
        # 停止文件监控器（非阻塞）
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            # 使用单独的线程来执行 join，避免阻塞主线程
            Thread(target=self._cleanup_observer, daemon=True).start()
        else:
            logging.info("文件监控器未运行")
        
        # 发送停止信号给工作线程
        if self.worker_thread and self.worker_thread.is_alive():
            self.task_queue.put(None)  # 发送哨兵值
            # 使用单独的线程来执行 join
            Thread(target=self._cleanup_worker, daemon=True).start()
        else:
            logging.info("FTP 工作线程未运行")
            self.is_stopping = False
        
        logging.info("监控停止指令已发送")
    
    def _cleanup_observer(self):
        """在后台线程中清理 observer"""
        try:
            self.observer.join(timeout=5)
            logging.info("文件监控器已停止")
        except Exception as e:
            logging.warning(f"停止文件监控器时出错: {e}")
    
    def _cleanup_worker(self):
        """在后台线程中清理 worker"""
        try:
            self.worker_thread.join(timeout=5)
            logging.info("FTP 工作线程已停止")
        except Exception as e:
            logging.warning(f"停止工作线程时出错: {e}")
        finally:
            self.is_stopping = False
