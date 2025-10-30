# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (GUI Application)

A graphical user interface for the Auto FTP Sync tool, allowing users to
manage multiple FTP server sync configurations and monitor them simultaneously.

Author: Sixparticle
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
        self.title("🔄 AutoFTPSync")
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
        
        # Add separator
        ttk.Separator(server_ctrl_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Save/Import/Export buttons
        ttk.Button(server_ctrl_frame, text="💾 保存配置", command=self._save_config_manual).pack(side=tk.LEFT, padx=2)
        ttk.Button(server_ctrl_frame, text="📥 导入配置", command=self._import_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(server_ctrl_frame, text="📤 导出配置", command=self._export_config).pack(side=tk.LEFT, padx=2)

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

    def _save_config_manual(self):
        """手动保存配置到 data.json"""
        if not self.servers:
            messagebox.showwarning("警告", "当前没有任何服务器配置可以保存。")
            return
        
        if ConfigManager.save_servers(self.servers):
            messagebox.showinfo("成功", f"配置已保存到 data.json\n\n下次启动时会自动加载此配置。")
            logging.info("配置已手动保存到 data.json", extra={'tag': 'SUCCESS'})
        else:
            messagebox.showerror("错误", "保存配置失败，请查看日志。")

    def _export_config(self):
        """Export current server configurations to data.json"""
        if not self.servers:
            messagebox.showwarning("警告", "当前没有任何服务器配置可以导出。")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="导出配置到文件",
            defaultextension=".json",
            initialfile="data.json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            if ConfigManager.export_to_file(self.servers, file_path):
                messagebox.showinfo("成功", f"配置已成功导出到:\n{file_path}")
                logging.info(f"配置已导出到: {file_path}", extra={'tag': 'SUCCESS'})
            else:
                messagebox.showerror("错误", "导出配置失败，请查看日志。")

    def _import_config(self):
        """Import server configurations from a file"""
        file_path = filedialog.askopenfilename(
            title="选择要导入的配置文件",
            defaultextension=".json",
            initialfile="data.json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        imported_servers = ConfigManager.import_from_file(file_path)
        
        if imported_servers is None:
            messagebox.showerror("错误", "无法读取配置文件，请检查文件格式。")
            return
        
        if not imported_servers:
            messagebox.showwarning("警告", "配置文件中没有找到有效的服务器配置。")
            return
        
        # Ask user whether to replace or merge
        if self.servers:
            response = messagebox.askyesnocancel(
                "导入选项",
                f"找到 {len(imported_servers)} 个服务器配置。\n\n"
                "是 - 合并到现有配置（添加新服务器）\n"
                "否 - 替换现有配置（清空后导入）\n"
                "取消 - 取消导入"
            )
            
            if response is None:  # Cancel
                return
            elif response:  # Yes - Merge
                # Check for duplicate IDs and regenerate if needed
                existing_ids = {s['id'] for s in self.servers}
                for server in imported_servers:
                    if server['id'] in existing_ids:
                        # Regenerate ID for duplicates
                        old_id = server['id']
                        server['id'] = str(uuid.uuid4())[:8]
                        logging.info(f"重复ID已重新生成: {old_id} -> {server['id']}")
                
                self.servers.extend(imported_servers)
                messagebox.showinfo("成功", f"已合并 {len(imported_servers)} 个服务器配置。")
            else:  # No - Replace
                self.servers = imported_servers
                messagebox.showinfo("成功", f"已导入 {len(imported_servers)} 个服务器配置（替换模式）。")
        else:
            # No existing servers, just import
            self.servers = imported_servers
            messagebox.showinfo("成功", f"已导入 {len(imported_servers)} 个服务器配置。")
        
        self._save_servers()
        self._populate_server_list()
        logging.info(f"从 {file_path} 导入配置成功", extra={'tag': 'SUCCESS'})

    def _start_all_watchers(self):
        if not self.servers:
            messagebox.showerror("错误", "没有配置任何服务器。")
            return

        # 清理可能存在的旧监控器（防止内存泄漏）
        if self.watchers:
            logging.warning("检测到旧的监控器实例，正在清理...")
            for server_id in list(self.watchers.keys()):
                try:
                    old_watcher = self.watchers[server_id]
                    if old_watcher:
                        old_watcher.stop()
                except Exception as e:
                    logging.warning(f"清理旧监控器 [{server_id}] 时出错: {e}")
            self.watchers.clear()

        # 禁用启动按钮，显示启动中状态
        self.start_button.config(state="disabled", text="▶️ 启动中...")
        self.update_idletasks()  # 立即更新UI
        
        # 在后台线程中启动所有监控器，避免阻塞GUI
        def start_async():
            servers_to_start = list(self.servers)  # 复制列表避免并发问题
            
            for server in servers_to_start:
                server_id = server['id']
                local_dir = server.get('local_dir')

                if not local_dir or not os.path.exists(local_dir):
                    logging.error(f"[{server_id}] 本地目录 '{local_dir}' 无效或不存在，跳过。")
                    # 在主线程中更新UI
                    self.after(0, lambda sid=server_id, s=server, ld=local_dir: 
                              self.server_tree.item(sid, values=(s['id'], s['host'], ld, "错误")))
                    continue

                try:
                    # 创建新的 Watcher 实例
                    logging.info(f"[{server_id}] 正在启动监控...")
                    watcher = Watcher(local_dir, server)
                    watcher.start()
                    self.watchers[server_id] = watcher
                    
                    # 在主线程中更新UI（避免TreeView并发问题）
                    self.after(0, lambda sid=server_id, s=server, ld=local_dir: 
                              self.server_tree.item(sid, values=(s['id'], s['host'], ld, "监控中")))
                    logging.info(f"[{server_id}] 监控已启动 -> {local_dir}", extra={'tag': 'SUCCESS'})
                    
                except Exception as e:
                    logging.error(f"[{server_id}] 启动监控失败: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                    # 在主线程中更新UI
                    self.after(0, lambda sid=server_id, s=server, ld=local_dir: 
                              self.server_tree.item(sid, values=(s['id'], s['host'], ld, "启动失败")))
            
            # 所有启动完成后，在主线程中更新UI状态
            self.after(0, self._finalize_start)
        
        # 在后台线程中启动
        Thread(target=start_async, daemon=True).start()

    def _finalize_start(self):
        """启动完成后的UI更新"""
        self._set_ui_state("watching")
        self.start_button.config(text="▶️ 开始全部")
        logging.info("所有监控器启动完成。", extra={'tag': 'SUCCESS'})

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
