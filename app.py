# -*- coding: utf-8 -*-

"""
Auto FTP Sync Tool (GUI Application)

A graphical user interface for the Auto FTP Sync tool, allowing users to
easily select a project, configure FTP settings, and monitor file changes.

Author: Cline (AI Software Engineer)
Version: 4.0.2
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import logging
import time
from datetime import datetime
from threading import Thread
from ttkthemes import ThemedTk
from sync_core import ConfigManager, Watcher

class App(ThemedTk):
    def __init__(self):
        super().__init__()
        self.set_theme("arc")
        self.title("🔄 Auto FTP Sync v4.0.2")
        self.geometry("900x700")
        self.minsize(800, 600)
        
        # 居中显示
        self._center_window()

        self.watcher = None
        self.project_path = tk.StringVar()
        self.ftp_config = {}
        
        # 统计信息
        self.stats = {
            'synced_files': 0,
            'errors': 0,
            'start_time': None
        }

        self._create_widgets()
        self._setup_logging()
        self._update_status_bar()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _center_window(self):
        """将窗口居中显示"""
        self.update_idletasks()
        width = 900
        height = 700
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _create_widgets(self):
        # 顶部容器
        top_container = ttk.Frame(self)
        top_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧面板（配置区域）
        left_panel = ttk.Frame(top_container)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 右侧面板（状态和统计）
        right_panel = ttk.Frame(top_container, width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_panel.pack_propagate(False)
        
        # === 左侧面板内容 ===
        
        # --- 1. 项目目录 ---
        path_frame = ttk.LabelFrame(left_panel, text="📁 项目目录", padding="15")
        path_frame.pack(fill=tk.X, pady=(0, 10))
        
        path_entry = ttk.Entry(path_frame, textvariable=self.project_path, 
                              state="readonly", font=('Arial', 10))
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        browse_button = ttk.Button(path_frame, text="浏览...", 
                                   command=self._browse_directory, width=10)
        browse_button.pack(side=tk.LEFT)
        
        # --- 2. FTP 配置 ---
        self.config_frame = ttk.LabelFrame(left_panel, text="⚙️ FTP 服务器配置", padding="15")
        self.config_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.entries = {}
        fields = ["host", "port", "username", "password", "remote_dir"]
        labels = ["服务器地址", "端口", "用户名", "密码", "远程目录"]
        placeholders = ["例如: ftp.example.com", "21", "your_username", "", "/public_html"]
        
        for i, field in enumerate(fields):
            # 标签
            label = ttk.Label(self.config_frame, text=labels[i], 
                            font=('Arial', 9, 'bold'))
            label.grid(row=i*2, column=0, sticky=tk.W, pady=(8 if i > 0 else 0, 2), padx=2)
            
            # 输入框
            entry = ttk.Entry(self.config_frame, 
                            show="●" if field == "password" else None,
                            font=('Arial', 10))
            entry.grid(row=i*2+1, column=0, sticky=tk.EW, pady=(0, 5), padx=2)
            
            # 设置占位符提示
            if placeholders[i]:
                entry.insert(0, placeholders[i])
                entry.config(foreground='gray')
                entry.bind('<FocusIn>', lambda e, ent=entry, ph=placeholders[i]: 
                          self._on_entry_focus_in(ent, ph))
                entry.bind('<FocusOut>', lambda e, ent=entry, ph=placeholders[i]: 
                          self._on_entry_focus_out(ent, ph))
            
            self.entries[field] = entry
            
        self.config_frame.grid_columnconfigure(0, weight=1)
        
        # 测试连接按钮
        test_btn_frame = ttk.Frame(self.config_frame)
        test_btn_frame.grid(row=len(fields)*2, column=0, sticky=tk.EW, pady=(5, 0))
        
        self.test_button = ttk.Button(test_btn_frame, text="🔌 测试连接", 
                                     command=self._test_connection)
        self.test_button.pack(side=tk.LEFT, padx=2)
        
        self.save_config_button = ttk.Button(test_btn_frame, text="💾 保存配置", 
                                            command=self._save_config)
        self.save_config_button.pack(side=tk.LEFT, padx=2)

        # --- 3. 控制面板 ---
        control_frame = ttk.LabelFrame(left_panel, text="🎮 监控控制", padding="15")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        self.start_button = ttk.Button(button_frame, text="▶️ 开始监控", 
                                      command=self._start_watching,
                                      style='Accent.TButton')
        self.start_button.pack(side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True)
        
        self.stop_button = ttk.Button(button_frame, text="⏸️ 停止监控", 
                                     state="disabled", 
                                     command=self._stop_watching)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 清空日志按钮
        self.clear_log_button = ttk.Button(button_frame, text="🗑️", 
                                          command=self._clear_log, width=4)
        self.clear_log_button.pack(side=tk.LEFT, padx=(8, 0))

        # --- 4. 日志输出 ---
        log_frame = ttk.LabelFrame(left_panel, text="📋 实时日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", 
                                                  wrap=tk.WORD, height=12,
                                                  font=('Consolas', 9),
                                                  bg='#f5f5f5', fg='#333333')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 配置日志文本标签颜色
        self.log_text.tag_config('INFO', foreground='#0066cc')
        self.log_text.tag_config('WARNING', foreground='#ff9800')
        self.log_text.tag_config('ERROR', foreground='#f44336', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('SUCCESS', foreground='#4caf50', font=('Consolas', 9, 'bold'))
        
        # === 右侧面板内容 ===
        
        # --- 状态指示器 ---
        status_frame = ttk.LabelFrame(right_panel, text="📊 运行状态", padding="15")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_canvas = tk.Canvas(status_frame, height=80, bg='white', 
                                      highlightthickness=0)
        self.status_canvas.pack(fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="⚪ 就绪", 
                                     font=('Arial', 11, 'bold'),
                                     foreground='#666666')
        self.status_label.pack(pady=(5, 0))
        
        # --- 统计信息 ---
        stats_frame = ttk.LabelFrame(right_panel, text="📈 统计信息", padding="15")
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stats_labels = {}
        stats_items = [
            ('synced', '同步文件数', '0'),
            ('errors', '错误次数', '0'),
            ('uptime', '运行时长', '--:--:--'),
        ]
        
        for i, (key, label, initial) in enumerate(stats_items):
            frame = ttk.Frame(stats_frame)
            frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(frame, text=label, font=('Arial', 9)).pack(side=tk.LEFT)
            value_label = ttk.Label(frame, text=initial, 
                                   font=('Arial', 10, 'bold'),
                                   foreground='#2196F3')
            value_label.pack(side=tk.RIGHT)
            self.stats_labels[key] = value_label
        
        # --- 快捷操作 ---
        quick_frame = ttk.LabelFrame(right_panel, text="⚡ 快捷操作", padding="15")
        quick_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(quick_frame, text="📂 打开项目文件夹", 
                  command=self._open_project_folder).pack(fill=tk.X, pady=2)
        ttk.Button(quick_frame, text="📝 查看配置文件", 
                  command=self._view_config_file).pack(fill=tk.X, pady=2)
        ttk.Button(quick_frame, text="ℹ️ 关于", 
                  command=self._show_about).pack(fill=tk.X, pady=2)
        
        # === 底部状态栏 ===
        self.status_bar = ttk.Label(self, text="就绪", relief=tk.SUNKEN, 
                                   anchor=tk.W, padding=(5, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_entry_focus_in(self, entry, placeholder):
        """输入框获得焦点时清除占位符"""
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground='black')
    
    def _on_entry_focus_out(self, entry, placeholder):
        """输入框失去焦点时恢复占位符"""
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(foreground='gray')
    
    def _clear_log(self):
        """清空日志"""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")
        logging.info("日志已清空")
    
    def _test_connection(self):
        """测试 FTP 连接"""
        try:
            from ftplib import FTP
            
            host = self.entries['host'].get()
            port = self.entries['port'].get()
            username = self.entries['username'].get()
            password = self.entries['password'].get()
            
            # 检查占位符
            if not host or host == "例如: ftp.example.com":
                messagebox.showerror("错误", "请输入服务器地址")
                return
            
            logging.info(f"正在测试连接到 {host}:{port}...")
            
            ftp = FTP()
            ftp.connect(host, int(port) if port and port != '21' else 21, timeout=10)
            ftp.login(username, password)
            
            logging.info("✓ 连接成功！", extra={'tag': 'SUCCESS'})
            messagebox.showinfo("成功", f"成功连接到 FTP 服务器！\n服务器: {host}\n欢迎信息: {ftp.getwelcome()}")
            ftp.quit()
            
        except Exception as e:
            logging.error(f"连接失败: {str(e)}")
            messagebox.showerror("连接失败", f"无法连接到 FTP 服务器:\n{str(e)}")
    
    def _open_project_folder(self):
        """打开项目文件夹"""
        path = self.project_path.get()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("警告", "请先选择项目目录")
    
    def _view_config_file(self):
        """查看配置文件"""
        path = self.project_path.get()
        if not path:
            messagebox.showwarning("警告", "请先选择项目目录")
            return
        
        config_path = os.path.join(path, '.ftp_config.json')
        if os.path.exists(config_path):
            os.startfile(config_path)
        else:
            messagebox.showinfo("提示", "配置文件不存在，请先保存配置")
    
    def _show_about(self):
        """显示关于对话框"""
        about_text = """
🔄 Auto FTP Sync v4.0.1

一个强大的文件自动同步工具

功能特点:
• 实时监控文件变化
• 自动上传到 FTP 服务器
• 智能过滤系统文件
• 可视化状态监控

更新日志:
v4.0.2 - 彻底修复停止监控卡死问题
v4.0.1 - 首次尝试修复停止监控问题

作者: AI Software Engineer
版本: 4.0.2
日期: 2025
        """
        messagebox.showinfo("关于 Auto FTP Sync", about_text)
    
    def _update_status_bar(self):
        """更新状态栏"""
        if self.watcher and self.stats['start_time']:
            # 计算运行时长
            uptime = int(time.time() - self.stats['start_time'])
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60
            uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            self.stats_labels['uptime'].config(text=uptime_str)
            self.status_bar.config(text=f"监控中 | 已同步: {self.stats['synced_files']} | 错误: {self.stats['errors']} | 运行时长: {uptime_str}")
        else:
            self.status_bar.config(text="就绪")
        
        # 每秒更新一次
        self.after(1000, self._update_status_bar)
    
    def _update_status_indicator(self, status='idle'):
        """更新状态指示器"""
        self.status_canvas.delete('all')
        width = self.status_canvas.winfo_width()
        height = self.status_canvas.winfo_height()
        
        if width < 10:  # 还未渲染
            self.after(100, lambda: self._update_status_indicator(status))
            return
        
        center_x = width // 2
        center_y = height // 2
        
        if status == 'idle':
            color = '#9e9e9e'
            self.status_label.config(text="⚪ 就绪", foreground='#666666')
        elif status == 'watching':
            color = '#4caf50'
            self.status_label.config(text="🟢 监控中", foreground='#4caf50')
            # 绘制波纹动画
            for i in range(3):
                radius = 15 + i * 10
                self.status_canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    outline=color, width=2
                )
        elif status == 'error':
            color = '#f44336'
            self.status_label.config(text="🔴 错误", foreground='#f44336')
        
        # 绘制中心圆
        self.status_canvas.create_oval(
            center_x - 20, center_y - 20,
            center_x + 20, center_y + 20,
            fill=color, outline=''
        )

    def _browse_directory(self):
        path = filedialog.askdirectory(title="选择项目目录")
        if path:
            self.project_path.set(path)
            self._load_config()
            logging.info(f"✓ 已选择项目: {path}", extra={'tag': 'SUCCESS'})

    def _load_config(self):
        path = self.project_path.get()
        if not path:
            return
            
        config_path = os.path.join(path, '.ftp_config.json')
        self.ftp_config = ConfigManager.load_config(config_path)
        
        for field, entry in self.entries.items():
            # 清除占位符样式
            entry.config(foreground='black')
            entry.delete(0, tk.END)
            if field in self.ftp_config:
                entry.insert(0, self.ftp_config[field])
        
        if self.ftp_config:
            logging.info(f"✓ 已从 '{config_path}' 加载配置", extra={'tag': 'SUCCESS'})
        else:
            logging.info("未找到配置文件，请手动输入 FTP 配置")

    def _save_config(self):
        path = self.project_path.get()
        if not path:
            messagebox.showwarning("警告", "请先选择项目目录")
            return False
            
        config_path = os.path.join(path, '.ftp_config.json')
        
        current_config = {}
        for field, entry in self.entries.items():
            value = entry.get()
            # 跳过占位符
            if value and not value.startswith('例如:'):
                current_config[field] = value
            
        if ConfigManager.save_config(config_path, current_config):
            logging.info(f"✓ 配置已保存到 '{config_path}'", extra={'tag': 'SUCCESS'})
            self.ftp_config = current_config
            messagebox.showinfo("成功", "配置已保存！")
            return True
        else:
            logging.error(f"✗ 保存配置到 '{config_path}' 失败")
            return False

    def _start_watching(self):
        if not self.project_path.get():
            messagebox.showerror("错误", "请先选择一个项目目录")
            return
        
        # 检查配置是否完整
        for field, entry in self.entries.items():
            value = entry.get()
            if not value or value.startswith('例如:'):
                messagebox.showerror("错误", f"请填写完整的 FTP 配置\n缺少: {field}")
                return

        if not self._save_config():
            return

        self._set_ui_state("watching")
        
        # 重置统计
        self.stats['synced_files'] = 0
        self.stats['errors'] = 0
        self.stats['start_time'] = time.time()
        self._update_stats()
        
        self.watcher = Watcher(self.project_path.get(), self.ftp_config)
        self.watcher.start()
        
        logging.info("=" * 60, extra={'tag': 'SUCCESS'})
        logging.info("🚀 监控已启动！", extra={'tag': 'SUCCESS'})
        logging.info("=" * 60, extra={'tag': 'SUCCESS'})

    def _stop_watching(self):
        """停止监控，异步方式不阻塞 GUI"""
        if self.watcher:
            # 先禁用停止按钮，防止重复点击
            self.stop_button.config(state="disabled", text="⏸️ 停止中...")
            
            logging.info("⏸️ 正在停止监控...", extra={'tag': 'WARNING'})
            
            # 异步停止 - 在单独的线程中调用 stop 方法
            def stop_async():
                try:
                    self.watcher.stop()
                    # 等待一小段时间让清理完成
                    time.sleep(0.5)
                    # 在主线程中完成 UI 更新
                    self.after(0, self._finalize_stop)
                except Exception as e:
                    logging.error(f"停止监控时出错: {e}")
                    self.after(0, self._finalize_stop)
            
            Thread(target=stop_async, daemon=True).start()
    
    def _finalize_stop(self):
        """完成停止操作，重置 UI 状态"""
        self.watcher = None
        self._set_ui_state("idle")
        self.stop_button.config(text="⏸️ 停止监控")
        logging.info("✓ 监控已完全停止", extra={'tag': 'SUCCESS'})

    def _set_ui_state(self, state):
        if state == "watching":
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.test_button.config(state="disabled")
            self.save_config_button.config(state="disabled")
            for entry in self.entries.values():
                entry.config(state="disabled")
            self._update_status_indicator('watching')
        else: # idle
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.test_button.config(state="normal")
            self.save_config_button.config(state="normal")
            for entry in self.entries.values():
                entry.config(state="normal")
            self._update_status_indicator('idle')
    
    def _update_stats(self):
        """更新统计信息"""
        self.stats_labels['synced'].config(text=str(self.stats['synced_files']))
        self.stats_labels['errors'].config(text=str(self.stats['errors']))

    def _setup_logging(self):
        log_handler = TextHandler(self.log_text, self)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', 
                                                   datefmt='%H:%M:%S'))
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)
        
        logging.info("=" * 60)
        logging.info("🔄 Auto FTP Sync v4.0.1 启动成功", extra={'tag': 'SUCCESS'})
        logging.info("=" * 60)

    def _on_closing(self):
        """处理窗口关闭事件"""
        if self.watcher and self.watcher.observer.is_alive():
            if messagebox.askokcancel("退出", "监控正在运行中，确定要退出吗？\n程序将在后台完成清理工作。"):
                # 异步停止，不等待完成
                if self.watcher:
                    self.watcher.stop()
                # 给一点时间让停止命令发出
                self.after(200, self.destroy)
        else:
            self.destroy()

class TextHandler(logging.Handler):
    """Custom logging handler to redirect logs to a tkinter Text widget."""
    def __init__(self, text_widget, app=None):
        super().__init__()
        self.text_widget = text_widget
        self.app = app

    def emit(self, record):
        msg = self.format(record)
        
        # 确定标签
        tag = getattr(record, 'tag', record.levelname)
        
        self.text_widget.config(state="normal")
        self.text_widget.insert(tk.END, msg + "\n", tag)
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")
        
        # 更新统计信息
        if self.app and hasattr(self.app, 'stats'):
            if 'ERROR' in record.levelname or '错误' in msg or '失败' in msg:
                self.app.stats['errors'] += 1
                self.app._update_stats()
            elif '上传' in msg or '同步' in msg:
                self.app.stats['synced_files'] += 1
                self.app._update_stats()

if __name__ == "__main__":
    app = App()
    app.mainloop()
