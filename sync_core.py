# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (Core Logic Module)

This module contains the backend logic for file detection, FTP operations,
and state management. It is designed to be used by a GUI or other frontends.

Author: Cline (AI Software Engineer)
Version: 4.0.2 - Bug Fix: Complete non-blocking stop
"""

import os
import json
import logging
import time
from ftplib import FTP, error_perm
from threading import Thread
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigManager:
    """Handles loading and saving of FTP configuration from a given path."""
    @staticmethod
    def load_config(config_path):
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def save_config(config_path, config_data):
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)
            return True
        except IOError:
            return False

class FTPUploader:
    """Handles all FTP operations."""
    def __init__(self, config):
        self.config = config
        self.ftp = None

    def connect(self):
        try:
            self.ftp = FTP()
            self.ftp.connect(self.config['host'], int(self.config['port']))
            self.ftp.login(self.config['username'], self.config['password'])
            self.ftp.set_pasv(True)
            self.ftp.encoding = 'utf-8'
            self.ftp.cwd(self.config['remote_dir'])
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
        if not event.is_directory:
            self._queue_task('delete', event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._queue_task('delete', event.src_path)
            self._queue_task('upload', event.dest_path)

class Watcher:
    """File system watcher that runs in a separate thread."""
    def __init__(self, project_path, ftp_config):
        self.project_path = os.path.abspath(project_path)
        self.ftp_config = ftp_config
        self.observer = Observer()
        self.task_queue = Queue()
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

            self.task_queue.task_done()

        uploader.close()
        logging.info("FTP 任务处理器已停止。")

    def start(self):
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
