# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (GUI Application)

A graphical user interface for the Auto FTP Sync tool, allowing users to
manage multiple FTP server sync configurations and monitor them simultaneously.

Author: Cline (AI Software Engineer)
Version: 5.0.0 - Multi-Server Support
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import logging
import time
import uuid
from datetime import datetime
from threading import Thread
from ttkthemes import ThemedTk
from sync_core import ConfigManager, Watcher

class ServerConfigDialog(tk.Toplevel):
    """Dialog for adding or editing a server configuration."""
    def __init__(self, parent, server_config=None):
        super().__init__(parent)
        self.transient(parent)
        self.title("编辑服务器配置" if server_config else "添加新服务器")
        self.parent = parent
        self.result = None
        
        self.config = dict(server_config) if server_config else {}

        self._create_widgets()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _create_widgets(self):
        frame = ttk.Frame(self, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        fields = ["id", "host", "port", "username", "password", "remote_dir", "local_dir"]
        labels = ["ID (唯一标识)", "服务器地址", "端口", "用户名", "密码", "远程目录", "本地目录"]
        
        self.entries = {}
        for i, field in enumerate(fields):
            ttk.Label(frame, text=labels[i]).grid(row=i, column=0, sticky=tk.W, pady=2)
            entry = ttk.Entry(frame, width=50)
            entry.grid(row=i, column=1, sticky=tk.EW, pady=2)
            if field in self.config:
                entry.insert(0, self.config.get(field, ''))
            self.entries[field] = entry
        
        # Add FTPS/Secure checkbox
        self.secure_var = tk.BooleanVar(value=self.config.get('secure', False))
        secure_check = ttk.Checkbutton(frame, text="使用 FTPS (安全连接)", variable=self.secure_var)
        secure_check.grid(row=len(fields), column=1, sticky=tk.W, pady=(5,0))

        # Special handling for ID and local_dir
        if 'id' not in self.config:
            self.entries['id'].insert(0, str(uuid.uuid4())[:8])
        self.entries['id'].config(state="readonly")
        
        browse_button = ttk.Button(frame, text="浏览...", command=self._browse_local_dir)
        browse_button.grid(row=fields.index("local_dir"), column=2, padx=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=3, pady=(10, 0))
        
        ttk.Button(btn_frame, text="保存", command=self._on_ok, style='Accent.TButton').pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel).pack(side=tk.RIGHT)

    def _browse_local_dir(self):
        path = filedialog.askdirectory(title="选择本地同步目录")
        if path:
            self.entries['local_dir'].delete(0, tk.END)
            self.entries['local_dir'].insert(0, path)

    def _on_ok(self):
        self.result = {}
        for field, entry in self.entries.items():
            self.result[field] = entry.get()
        
        self.result['secure'] = self.secure_var.get()

        if not all([self.result.get('host'), self.result.get('username'), self.result.get('local_dir'), self.result.get('remote_dir')]):
            messagebox.showerror("错误", "服务器地址, 用户名, 本地目录和远程目录不能为空", parent=self)
            return

        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

class App(ThemedTk):
    def __init__(self):
        super().__init__()
        self.set_theme("arc")
        self.title("🔄 Auto FTP Sync v5.0.0 - 多服务器版")
        self.geometry("1000x750")
        self.minsize(900, 600)
        
        self._center_window()

        self.watchers = {}
        self.servers = []
        
        self.stats = {'synced_files': 0, 'errors': 0, 'start_time': None}

        self._create_widgets()
        self._setup_logging()
        self._load_servers()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel for server list and controls
        left_panel = ttk.Frame(main_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Right panel for logs
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Server List ---
        server_frame = ttk.LabelFrame(left_panel, text="📁 服务器列表", padding="10")
        server_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "host", "local_dir", "status")
        self.server_tree = ttk.Treeview(server_frame, columns=columns, show="headings")
        
        self.server_tree.heading("id", text="ID")
        self.server_tree.heading("host", text="服务器地址")
        self.server_tree.heading("local_dir", text="本地目录")
        self.server_tree.heading("status", text="状态")

        self.server_tree.column("id", width=80, anchor=tk.W)
        self.server_tree.column("host", width=150, anchor=tk.W)
        self.server_tree.column("local_dir", width=250, anchor=tk.W)
        self.server_tree.column("status", width=100, anchor=tk.CENTER)

        self.server_tree.pack(fill=tk.BOTH, expand=True)
        
        # --- Server Controls ---
        server_ctrl_frame = ttk.Frame(left_panel)
        server_ctrl_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(server_ctrl_frame, text="➕ 添加", command=self._add_server).pack(side=tk.LEFT, padx=2)
        ttk.Button(server_ctrl_frame, text="✏️ 编辑", command=self._edit_server).pack(side=tk.LEFT, padx=2)
        ttk.Button(server_ctrl_frame, text="➖ 删除", command=self._delete_server).pack(side=tk.LEFT, padx=2)

        # --- Main Controls ---
        control_frame = ttk.LabelFrame(left_panel, text="🎮 监控控制", padding="10")
        control_frame.pack(fill=tk.X, pady=(20, 0))
        
        self.start_button = ttk.Button(control_frame, text="▶️ 开始全部", command=self._start_all_watchers, style='Accent.TButton')
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.stop_button = ttk.Button(control_frame, text="⏸️ 停止全部", state="disabled", command=self._stop_all_watchers)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # --- Log Area ---
        log_frame = ttk.LabelFrame(right_panel, text="📋 实时日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config('INFO', foreground='#0066cc')
        self.log_text.tag_config('WARNING', foreground='#ff9800')
        self.log_text.tag_config('ERROR', foreground='#f44336', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('SUCCESS', foreground='#4caf50', font=('Consolas', 9, 'bold'))

    def _load_servers(self):
        self.servers = ConfigManager.load_servers()
        self._populate_server_list()
        logging.info(f"已加载 {len(self.servers)} 个服务器配置。")

    def _save_servers(self):
        if ConfigManager.save_servers(self.servers):
            logging.info("服务器配置已保存。", extra={'tag': 'SUCCESS'})
        else:
            logging.error("保存服务器配置失败。")

    def _populate_server_list(self):
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)
        
        for server in self.servers:
            self.server_tree.insert("", tk.END, iid=server['id'], values=(
                server.get('id', ''),
                server.get('host', ''),
                server.get('local_dir', ''),
                "就绪"
            ))

    def _add_server(self):
        dialog = ServerConfigDialog(self)
        if dialog.result:
            self.servers.append(dialog.result)
            self._save_servers()
            self._populate_server_list()

    def _edit_server(self):
        selected_item = self.server_tree.focus()
        if not selected_item:
            messagebox.showwarning("警告", "请先选择一个要编辑的服务器。")
            return

        server_id = selected_item
        server_config = next((s for s in self.servers if s['id'] == server_id), None)
        
        if server_config:
            dialog = ServerConfigDialog(self, server_config)
            if dialog.result:
                # Update the server in the list
                for i, s in enumerate(self.servers):
                    if s['id'] == server_id:
                        self.servers[i] = dialog.result
                        break
                self._save_servers()
                self._populate_server_list()

    def _delete_server(self):
        selected_item = self.server_tree.focus()
        if not selected_item:
            messagebox.showwarning("警告", "请先选择一个要删除的服务器。")
            return

        if messagebox.askyesno("确认删除", f"确定要删除服务器配置 '{selected_item}' 吗？"):
            self.servers = [s for s in self.servers if s['id'] != selected_item]
            self._save_servers()
            self._populate_server_list()

    def _start_all_watchers(self):
        if not self.servers:
            messagebox.showerror("错误", "没有配置任何服务器。")
            return

        self._set_ui_state("watching")
        
        for server in self.servers:
            server_id = server['id']
            local_dir = server.get('local_dir')

            if not local_dir or not os.path.exists(local_dir):
                logging.error(f"[{server_id}] 本地目录 '{local_dir}' 无效或不存在，跳过。")
                self.server_tree.item(server_id, values=(server['id'], server['host'], local_dir, "错误"))
                continue

            if server_id in self.watchers:
                logging.warning(f"[{server_id}] 监控已在运行，跳过。")
                continue

            try:
                watcher = Watcher(local_dir, server)
                watcher.start()
                self.watchers[server_id] = watcher
                self.server_tree.item(server_id, values=(server['id'], server['host'], local_dir, "监控中"))
                logging.info(f"[{server_id}] 监控已启动 -> {local_dir}", extra={'tag': 'SUCCESS'})
            except Exception as e:
                logging.error(f"[{server_id}] 启动监控失败: {e}")
                self.server_tree.item(server_id, values=(server['id'], server['host'], local_dir, "启动失败"))

    def _stop_all_watchers(self):
        self.stop_button.config(state="disabled", text="⏸️ 停止中...")
        
        def stop_async():
            for server_id, watcher in self.watchers.items():
                try:
                    watcher.stop()
                    logging.info(f"[{server_id}] 正在停止监控...")
                except Exception as e:
                    logging.error(f"[{server_id}] 停止监控时出错: {e}")
            
            # Give some time for threads to receive stop signal
            time.sleep(1)
            self.after(0, self._finalize_stop)

        Thread(target=stop_async, daemon=True).start()

    def _finalize_stop(self):
        self.watchers.clear()
        self._set_ui_state("idle")
        self.stop_button.config(text="⏸️ 停止全部")
        self._populate_server_list() # Reset status to "就绪"
        logging.info("所有监控任务已停止。", extra={'tag': 'SUCCESS'})

    def _set_ui_state(self, state):
        if state == "watching":
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        else: # idle
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")

    def _setup_logging(self):
        log_handler = TextHandler(self.log_text)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)
        logging.info("Auto FTP Sync v5.0.0 启动成功", extra={'tag': 'SUCCESS'})

    def _on_closing(self):
        if self.watchers:
            if messagebox.askokcancel("退出", "监控正在运行中，确定要退出吗？"):
                self._stop_all_watchers()
                self.after(1500, self.destroy) # Give time to stop
        else:
            self.destroy()

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        tag = getattr(record, 'tag', record.levelname)
        
        def append_message():
            self.text_widget.config(state="normal")
            self.text_widget.insert(tk.END, msg + "\n", tag)
            self.text_widget.see(tk.END)
            self.text_widget.config(state="disabled")
        
        # Ensure UI updates are done in the main thread
        self.text_widget.after(0, append_message)

if __name__ == "__main__":
    app = App()
    app.mainloop()
