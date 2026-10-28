from PIL import Image, ImageDraw
sheet = Image.open("assets/crab_sheet.png").convert("RGBA")
FW = FH = 64
scale = 3
rows = ["down (下)", "left (左)", "right (右)", "up (上)"]
pad_l, pad_t = 92, 30
W = FW*4*scale + pad_l + 12
H = FH*4*scale + pad_t + 12
img = Image.new("RGBA", (W, H), (24, 34, 44, 255))
d = ImageDraw.Draw(img)
for r in range(4):
    for c in range(4):
        cell = sheet.crop((c*FW, r*FH, c*FW+FW, r*FH+FH))
        cell = cell.resize((FW*scale, FH*scale), Image.NEAREST)
        x = pad_l + c*FW*scale
        y = pad_t + r*FH*scale
        # 棋盘格底，便于看透明区
        for by in range(0, FH*scale, 16):
            for bx in range(0, FW*scale, 16):
                col = (58, 68, 78, 255) if ((bx//16 + by//16) % 2 == 0) else (44, 54, 64, 255)
                d.rectangle([x+bx, y+by, x+bx+15, y+by+15], fill=col)
        img.alpha_composite(cell, (x, y))
        d.rectangle([x, y, x+FW*scale-1, y+FH*scale-1], outline=(120, 132, 144, 255))
    d.text((6, pad_t + r*FH*scale + FH*scale//2 - 6), rows[r], fill=(235, 226, 208, 255))
for c in range(4):
    d.text((pad_l + c*FW*scale + FW*scale//2 - 4, 8), f"frame {c}", fill=(200, 210, 220, 255))
img.convert("RGB").save("evidence/07_actioncard.png", optimize=True)
print("saved evidence/07_actioncard.png", img.size)
