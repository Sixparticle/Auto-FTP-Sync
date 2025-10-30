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
            
            logging.info(f"FTP{'S' if use_tls else ''} 连接成功到 {host} ({ip_address})")
            return True
        except Exception as e:
            logging.error(f"FTP 连接失败: {e}")
            return False

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
            self._ensure_remote_dir(remote_path)
            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {remote_path}', f)
            logging.info(f"  [上传成功] {remote_path}")
            return True
        except FileNotFoundError:
            logging.warning(f"  [上传跳过] 文件已不存在: {local_path}")
            return False
        except Exception as e:
            logging.error(f"  [上传失败] {remote_path}: {e}")
            return False

    def delete_file(self, remote_path):
        try:
            self.ftp.delete(remote_path)
            logging.info(f"  [删除成功] {remote_path}")
            return True
        except error_perm as e:
            # It's often okay if the file is already gone.
            logging.warning(f"  [删除失败] {remote_path}: {e}. 可能文件已不存在。")
            return False
        except Exception as e:
            logging.error(f"  [删除失败] {remote_path}: {e}")
            return False

    def delete_directory(self, remote_path):
        """递归删除远程目录及其所有内容"""
        try:
            # 切换到目标目录的父目录
            parent_dir = os.path.dirname(remote_path).replace('\\', '/')
            if parent_dir:
                self.ftp.cwd(self.config['remote_dir'])
                if parent_dir:
                    self.ftp.cwd(parent_dir)
            else:
                self.ftp.cwd(self.config['remote_dir'])
            
            # 获取目录名
            dir_name = os.path.basename(remote_path)
            
            try:
                # 尝试列出目录内容
                self.ftp.cwd(dir_name)
                items = []
                self.ftp.retrlines('LIST', items.append)
                
                # 递归删除目录中的所有内容
                for item in items:
                    # 解析 LIST 输出（简化版，可能需要根据服务器调整）
                    parts = item.split()
                    if len(parts) < 9:
                        continue
                    
                    permissions = parts[0]
                    name = ' '.join(parts[8:])
                    
                    # 跳过 . 和 ..
                    if name in ['.', '..']:
                        continue
                    
                    # 判断是文件还是目录
                    if permissions.startswith('d'):
                        # 递归删除子目录
                        sub_path = f"{remote_path}/{name}".replace('//', '/')
                        self.delete_directory(sub_path)
                    else:
                        # 删除文件
                        self.ftp.delete(name)
                        logging.info(f"  [删除文件] {remote_path}/{name}")
                
                # 返回父目录并删除空目录
                self.ftp.cwd('..')
                self.ftp.rmd(dir_name)
                logging.info(f"  [删除目录成功] {remote_path}")
                
            except error_perm:
                # 目录可能已经不存在或为空，尝试直接删除
                self.ftp.cwd(self.config['remote_dir'])
                if parent_dir:
                    self.ftp.cwd(parent_dir)
                self.ftp.rmd(dir_name)
                logging.info(f"  [删除空目录成功] {remote_path}")
            
            # 返回根目录
            self.ftp.cwd(self.config['remote_dir'])
            return True
            
        except error_perm as e:
            logging.warning(f"  [删除目录失败] {remote_path}: {e}. 可能目录已不存在。")
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

    def _is_ignored(self, path):
        # Check if the path contains any of the ignored directory/file names.
        return any(ignored in path.replace('\\', '/').split('/') for ignored in self.ignored_items)

    def _queue_task(self, action, path):
        if self._is_ignored(path):
            return
        logging.info(f"检测到变更，加入队列: {action.upper()} -> {path}")
        self.task_queue.put((action, path))

    def on_created(self, event):
        if not event.is_directory:
            self._queue_task('upload', event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._queue_task('upload', event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            self._queue_task('delete_dir', event.src_path)
        else:
            self._queue_task('delete', event.src_path)

    def on_moved(self, event):
        if event.is_directory:
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
        if not uploader.connect():
            logging.error("FTP 任务处理器无法连接，线程终止。")
            return

        logging.info("FTP 任务处理器已启动并连接成功。")

        while True:
            task = self.task_queue.get()
            if task is None:  # Sentinel to stop the thread
                break

            action, local_path = task
            rel_path = os.path.relpath(local_path, self.project_path).replace('\\', '/')

            if action == 'upload':
                uploader.upload_file(local_path, rel_path)
            elif action == 'delete':
                uploader.delete_file(rel_path)
            elif action == 'delete_dir':
                uploader.delete_directory(rel_path)

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
        self.observer.schedule(event_handler, self.project_path, recursive=True)
        self.observer.start()  # This starts observer in its own thread automatically
        logging.info(f"开始监控目录: {self.project_path}")

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
