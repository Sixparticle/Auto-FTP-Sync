"""
创建同步图标的脚本
使用 PIL (Pillow) 库生成一个简单的同步图标
"""

from PIL import Image, ImageDraw
import math

def create_sync_icon(size=256):
    """创建一个同步图标（双箭头循环）"""
    # 创建透明背景
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 蓝色渐变色
    color1 = (0, 120, 215, 255)  # Windows 蓝色
    color2 = (16, 137, 255, 255)  # 亮蓝色
    
    center = size // 2
    radius = size // 3
    arrow_width = size // 10
    
    # 绘制圆形箭头（上半部分 - 顺时针）
    draw.arc(
        [center - radius, center - radius, center + radius, center + radius],
        start=-90, end=180, fill=color1, width=arrow_width
    )
    
    # 绘制圆形箭头（下半部分 - 逆时针）
    draw.arc(
        [center - radius, center - radius, center + radius, center + radius],
        start=90, end=360, fill=color2, width=arrow_width
    )
    
    # 绘制箭头头部
    arrow_size = size // 8
    
    # 上方箭头（指向右）
    arrow1_x = center + radius - arrow_width // 2
    arrow1_y = center
    draw.polygon([
        (arrow1_x, arrow1_y - arrow_size // 2),
        (arrow1_x + arrow_size, arrow1_y),
        (arrow1_x, arrow1_y + arrow_size // 2)
    ], fill=color1)
    
    # 下方箭头（指向左）
    arrow2_x = center - radius + arrow_width // 2
    arrow2_y = center
    draw.polygon([
        (arrow2_x, arrow2_y - arrow_size // 2),
        (arrow2_x - arrow_size, arrow2_y),
        (arrow2_x, arrow2_y + arrow_size // 2)
    ], fill=color2)
    
    # 中心圆圈
    inner_radius = radius // 3
    draw.ellipse(
        [center - inner_radius, center - inner_radius, 
         center + inner_radius, center + inner_radius],
        fill=(255, 255, 255, 255),
        outline=color1,
        width=arrow_width // 2
    )
    
    return img

def save_icon(filename='sync_icon.ico'):
    """保存为 .ico 格式，包含多个尺寸"""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        img = create_sync_icon(size)
        images.append(img)
    
    # 保存为 .ico 文件
    images[0].save(
        filename,
        format='ICO',
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:]
    )
    print(f"图标已创建: {filename}")

if __name__ == "__main__":
    try:
        save_icon()
        print("✓ 图标创建成功！")
        print("现在可以运行: pyinstaller app.spec")
    except ImportError:
        print("错误: 需要安装 Pillow 库")
        print("请运行: pip install Pillow")
    except Exception as e:
        print(f"错误: {e}")
