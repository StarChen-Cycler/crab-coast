import json, sys
from PIL import Image, ImageDraw

src = r"C:\Users\LENOVO\.dsh\attachments\v1\objects\c9\c9f2ab7dde1fd91dbe31d0024f811adb1694ac65d445148f80cd1cfd4b24cce9"
im = Image.open(src).convert("RGB")
W, H = im.size
SCALE = W / 844.0          # 截图宽度 / CSS 宽度（DPR 3）
print("image", im.size, "scale", round(SCALE, 3))

# 量出来的 CSS 盒子（左, 上, 宽, 高）
boxes = {
    "Y": (721.9, 208.2, 48.4, 48.4),
    "X": (673.6, 265.9, 48.4, 48.4),
    "B": (770.3, 265.9, 48.4, 48.4),
    "A": (717.2, 319.0, 57.7, 57.7),
}
PAD = 20
sheet = Image.new("RGB", (4 * 220, 220), (28, 34, 42))
d = ImageDraw.Draw(sheet)
for i, (name, (l, t, w, h)) in enumerate(boxes.items()):
    cx, cy = (l + w / 2) * SCALE, (t + h / 2) * SCALE
    half = (w / 2 + PAD) * SCALE
    crop = im.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    crop = crop.resize((200, 200), Image.LANCZOS)
    sheet.paste(crop, (i * 220 + 10, 20))
    d.text((i * 220 + 96, 6), name, fill=(243, 231, 207))
    # 在裁剪图上标出「按钮中心」十字，判断环是否居中
    d.line((i * 220 + 110 - 8, 120, i * 220 + 110 + 8, 120), fill=(255, 80, 80), width=1)
    d.line((i * 220 + 110, 120 - 8, i * 220 + 110, 120 + 8), fill=(255, 80, 80), width=1)
sheet.save("evidence/abxy_check.png")
print("saved evidence/abxy_check.png")