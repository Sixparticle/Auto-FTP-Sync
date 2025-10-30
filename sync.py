# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (Watcher Edition)

A Python script that monitors a project directory for file changes in real-time
and automatically uploads them to an FTP server.

Author: Sixparticle
"""

import os
import json
import hashlib
import argparse
import logging
import time
from ftplib import FTP, error_perm
from getpass import getpass
from threading import Timer, Lock
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Constants ---
CONFIG_FILE = '.ftp_config.json'
STATE_FILE = '.sync_state.json'
LOG_FILE = 'sync.log'
SCRIPT_NAME = os.path.basename(__file__)
# Files/dirs to ignore during sync and watch
IGNORED_ITEMS = {CONFIG_FILE, STATE_FILE, LOG_FILE, SCRIPT_NAME, '.git', '.idea', '__pycache__'}

# --- Global Lock ---
sync_lock = Lock()

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class ConfigManager:
    """Handles loading and saving of FTP configuration."""
    def __init__(self, file_path=CONFIG_FILE):
        self.file_path = file_path

    def load_config(self):
        if not os.path.exists(self.file_path):
            logging.info(f"配置文件 '{self.file_path}' 不存在，将引导您进行创建。")
            return self._create_config()
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"读取配置文件 '{self.file_path}' 失败: {e}")
            return None

    def _create_config(self):
        try:
            config = {
                'host': input("请输入 FTP 主机地址: "),
                'port': int(input("请输入 FTP 端口 (默认为 21): ") or 21),
                'username': input("请输入 FTP 用户名: "),
                'password': getpass("请输入 FTP 密码: "),
                'remote_dir': input("请输入远程服务器的根目录 (例如 /www/myproject): ")
            }
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            logging.info(f"配置已成功保存到 '{self.file_path}'。")
            return config
        except (ValueError, IOError) as e:
            logging.error(f"创建配置文件失败: {e}")
            return None

class SyncStateManager:
    """Manages the synchronization state file."""
    def __init__(self, state_file_path):
        self.file_path = state_file_path

    def load_state(self):
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logging.warning(f"无法读取状态文件 '{self.file_path}'，将执行完整同步。")
            return {}

    def save_state(self, state):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
        except IOError as e:
            logging.error(f"保存状态文件 '{self.file_path}' 失败: {e}")

class FileChangeDetector:
    """Detects file changes by comparing current state with the last sync state."""
    def __init__(self, project_path):
        self.project_path = os.path.abspath(project_path)

    @staticmethod
    def _calculate_hash(file_path):
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except IOError:
            return None

    def get_current_state(self):
        current_state = {}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_ITEMS]
            for file in files:
                if file in IGNORED_ITEMS or file.endswith('.tmp'):
                    continue
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.project_path).replace('\\', '/')
                file_hash = self._calculate_hash(file_path)
                if file_hash:
                    current_state[relative_path] = file_hash
        return current_state

    def detect_changes(self, old_state, new_state):
        added = {p: h for p, h in new_state.items() if p not in old_state}
        modified = {p: h for p, h in new_state.items() if p in old_state and old_state[p] != h}
        deleted = {p: h for p, h in old_state.items() if p not in new_state}
        return {'added': added, 'modified': modified, 'deleted': deleted}

class FTPUploader:
    """Handles all FTP operations."""
    def __init__(self, config):
        self.config = config
        self.ftp = None

    def connect(self):
        try:
            self.ftp = FTP()
            self.ftp.connect(self.config['host'], self.config['port'])
            self.ftp.login(self.config['username'], self.config['password'])
            self.ftp.set_pasv(True)
            self.ftp.encoding = 'utf-8'
            self.ftp.cwd(self.config['remote_dir'])
            return True
        except Exception as e:
            logging.error(f"FTP 连接失败: {e}")
            return False

    def _ensure_remote_dir(self, remote_path):
        parts = os.path.dirname(remote_path).split('/')
        if not parts or parts == ['']: return
        current_path = ""
        for part in parts:
            if not part: continue
            current_path = f"{current_path}/{part}" if current_path else part
            try:
                self.ftp.cwd(current_path)
            except error_perm:
                self.ftp.mkd(current_path)
                self.ftp.cwd(current_path)
        self.ftp.cwd(self.config['remote_dir'])

    def upload_file(self, local_path, remote_path):
        try:
            self._ensure_remote_dir(remote_path)
            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {remote_path}', f)
            logging.info(f"  [上传成功] {local_path} -> {remote_path}")
            return True
        except Exception as e:
            logging.error(f"  [上传失败] {local_path} -> {remote_path}: {e}")
            return False

    def delete_file(self, remote_path):
        try:
            self.ftp.delete(remote_path)
            logging.info(f"  [删除成功] {remote_path}")
            return True
        except Exception as e:
            logging.error(f"  [删除失败] {remote_path}: {e}")
            return False

    def close(self):
        if self.ftp:
            self.ftp.quit()

class Debouncer:
    """A simple debouncer to delay function execution."""
    def __init__(self, delay, callback, args=None, kwargs=None):
        self.delay = delay
        self.callback = callback
        self.args = args or []
        self.kwargs = kwargs or {}
        self.timer = None

    def call(self):
        self.cancel()
        self.timer = Timer(self.delay, self._execute)
        self.timer.start()

    def cancel(self):
        if self.timer:
            self.timer.cancel()

    def _execute(self):
        self.callback(*self.args, **self.kwargs)

def run_sync(project_path, force=False):
    """The core synchronization logic, refactored into a function."""
    if not sync_lock.acquire(blocking=False):
        logging.warning("同步任务已在运行中，本次触发被跳过。")
        return

    try:
        logging.info("="*50)
        logging.info("开始执行同步任务...")
        
        config_manager = ConfigManager()
        ftp_config = config_manager.load_config()
        if not ftp_config:
            return

        state_file_path = os.path.join(project_path, STATE_FILE)
        state_manager = SyncStateManager(state_file_path)
        old_state = {} if force else state_manager.load_state()

        detector = FileChangeDetector(project_path)
        current_state = detector.get_current_state()
        changes = detector.detect_changes(old_state, current_state)
        
        to_upload = {**changes['added'], **changes['modified']}
        to_delete = changes['deleted']

        if not to_upload and not to_delete:
            logging.info("项目没有检测到任何变更，无需同步。")
            return

        logging.info(f"检测到变更: {len(to_upload)} 个文件待上传, {len(to_delete)} 个文件待删除。")

        uploader = FTPUploader(ftp_config)
        if not uploader.connect():
            return

        success_uploads, failed_uploads = 0, 0
        if to_upload:
            for rel_path, _ in to_upload.items():
                local_path = os.path.join(project_path, rel_path.replace('/', os.sep))
                if uploader.upload_file(local_path, rel_path):
                    success_uploads += 1
                else:
                    failed_uploads += 1
        
        success_deletes, failed_deletes = 0, 0
        if to_delete:
            for rel_path, _ in to_delete.items():
                if uploader.delete_file(rel_path):
                    success_deletes += 1
                else:
                    failed_deletes += 1

        uploader.close()

        if failed_uploads == 0 and failed_deletes == 0:
            state_manager.save_state(current_state)
            logging.info(f"同步成功，已更新状态文件 '{state_file_path}'。")
        else:
            logging.warning("由于存在失败的操作，本次同步的状态将不会被保存。")

        logging.info(f"同步报告: 上传成功 {success_uploads}, 失败 {failed_uploads} | 删除成功 {success_deletes}, 失败 {failed_deletes}")
    finally:
        logging.info("同步任务结束。")
        logging.info("="*50 + "\n")
        sync_lock.release()

class SyncHandler(FileSystemEventHandler):
    """Handles file system events and triggers a debounced sync."""
    def __init__(self, project_path):
        self.project_path = project_path
        self.debouncer = Debouncer(1.5, run_sync, args=[self.project_path])

    def on_any_event(self, event):
        # Ignore events in ignored directories or for ignored files
        if any(ignored in event.src_path for ignored in IGNORED_ITEMS):
            return
        
        logging.info(f"检测到事件: {event.event_type} - {event.src_path}")
        self.debouncer.call()

def main():
    """Main function to start the file watcher."""
    parser = argparse.ArgumentParser(description="Auto FTP Sync Tool (Watcher Edition)")
    parser.add_argument('--path', default='.', help='要监控的项目路径 (默认为当前目录)。')
    parser.add_argument('--now', action='store_true', help='立即执行一次同步，然后开始监控。')
    args = parser.parse_args()

    project_path = os.path.abspath(args.path)
    if not os.path.isdir(project_path):
        logging.error(f"错误: 路径 '{project_path}' 不是一个有效的目录。")
        return

    # Run an initial sync if requested
    if args.now:
        run_sync(project_path, force=True)

    event_handler = SyncHandler(project_path)
    observer = Observer()
    observer.schedule(event_handler, project_path, recursive=True)
    
    logging.info(f"--- Auto FTP Sync v2.0 ---")
    logging.info(f"开始监控目录: {project_path}")
    logging.info("按 Ctrl+C 停止监控。")
    
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("监控已停止。")
    observer.join()

if __name__ == '__main__':
    main()
