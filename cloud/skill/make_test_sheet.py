"""生成一张测试用的 4×4 动作卡母版（绿幕），供 skill 转换器与端到端验收使用。
   行序：下 / 左 / 右 / 上；每格画一个橙色小生物，四帧略有差异。
"""
import os
import sys
from PIL import Image, ImageDraw

CELL = 128
SIZE = CELL * 4
out = sys.argv[1] if len(sys.argv) > 1 else "build/raw_sheet.png"
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

img = Image.new("RGB", (SIZE, SIZE), (0, 255, 0))
d = ImageDraw.Draw(img)

for row in range(4):
    for col in range(4):
        ox, oy = col * CELL, row * CELL
        bob = [0, -3, 0, 3][col]           # 四帧轻微上下起伏
        cx, cy = ox + CELL // 2, oy + CELL - 26 + bob
        # 身体
        d.ellipse([cx - 26, cy - 30, cx + 26, cy + 6], fill=(214, 108, 54))
        # 头（朝向：上排朝下画脸，上方向行不画脸）
        if row in (0, 1, 2):
            hx = cx - 10 if row == 1 else cx + 10 if row == 2 else cx
            d.ellipse([hx - 11, cy - 42, hx + 11, cy - 20], fill=(240, 158, 92))
            if row == 0:
                d.ellipse([hx - 7, cy - 35, hx - 3, cy - 31], fill=(20, 20, 20))
                d.ellipse([hx + 3, cy - 35, hx + 7, cy - 31], fill=(20, 20, 20))
        # 腿
        for i, dx in enumerate((-16, -6, 6, 16)):
            lift = 4 if (col + i) % 2 == 0 else 0
            d.line([cx + dx, cy + 4, cx + dx, cy + 16 - lift], fill=(150, 70, 40), width=5)

img.save(out)
print("saved", out, img.size)
