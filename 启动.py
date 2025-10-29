"""
快速启动脚本 - Auto FTP Sync
直接运行此脚本启动应用程序
"""

import subprocess
import sys
import os

def main():
    print("=" * 60)
    print("🔄 Auto FTP Sync v4.0 启动器")
    print("=" * 60)
    print()
    
    # 检查是否存在打包的 exe
    exe_path = os.path.join('dist', 'AutoFTPSync.exe')
    
    if os.path.exists(exe_path):
        print("✓ 找到打包版本，正在启动...")
        print(f"路径: {exe_path}")
        subprocess.Popen([exe_path])
    else:
        print("✓ 运行开发版本...")
        subprocess.Popen([sys.executable, 'app.py'])
    
    print()
    print("应用程序已启动！")
    print("=" * 60)

if __name__ == "__main__":
    main()
