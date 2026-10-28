from PIL import Image
src = r"C:\Users\LENOVO\.dsh\attachments\v1\objects\be\be5291c625697e889c8afd5b69fd477a01e0369df9b488137b53f7bc4a233c28"
im = Image.open(src).convert("RGB")
print("image", im.size)

centers = {"Y": (746.1, 232.4), "X": (697.7, 290.1), "B": (794.5, 290.1), "A": (746.1, 347.8)}
for name, (cx, cy) in centers.items():
    cx, cy = int(round(cx)), int(round(cy))
    inside = im.getpixel((cx, cy))
    outside = im.getpixel((cx - 45, cy))          # 按钮外 45px（半径 24 之外）
    dark = sum(inside) / 3 - sum(outside) / 3
    # 沿水平线找最亮/最暗，看描边是否留下一圈痕迹
    line = [im.getpixel((x, cy)) for x in range(cx - 30, cx + 31)]
    lum = [sum(p) / 3 for p in line]
    print(f"{name}: in={inside} out={outside} delta_lum={dark:+.0f} line_min={min(lum):.0f} line_max={max(lum):.0f} swing={max(lum)-min(lum):.0f}")