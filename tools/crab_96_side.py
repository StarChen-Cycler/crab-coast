"""为 96 尺寸也做「侧视缩 90%」，让三档尺寸的视觉比例一致。

48 版在 crab_side_scale.py 里做过同一件事；96 版如果直接沿用最初的表，
切到 96 时侧身会重新显得比正面大。这里用同样的按行缩放，只是倍率换成 1.0 / 0.9。

用法：python tools/crab_96_side.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "crab_sheet_v3_96.png"     # 原始 96 表（未做侧视缩放）
OUT = ROOT / "assets" / "crab_sheet_96.png"

CELL = 96
BASE = 86           # 源表脚底基线
SIDE = 0.90
COLORS = 48
ROWS = ["down", "left", "right", "up"]


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    out = Image.new("RGBA", (CELL * 4, CELL * 4), (0, 0, 0, 0))

    for r, name in enumerate(ROWS):
        f = SIDE if name in ("left", "right") else 1.0
        size = round(CELL * f)
        foot_src = round(BASE * f)
        paste_y = BASE - foot_src
        for c in range(4):
            cell = src.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))
            small = cell.resize((size, size), Image.LANCZOS) if f != 1.0 else cell
            out.paste(small, (c * CELL, r * CELL + paste_y), small)
        print(f"{name:6s} 倍率 {f:.2f} 边长 {size} 脚底 {foot_src} 下移 {paste_y}")

    q = out.convert("RGB").quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(out.getchannel("A"))
    q.save(OUT, optimize=True)
    print(f"已写出 {OUT.relative_to(ROOT)}  {q.size}  {len(q.convert('RGB').getcolors(99999))} 色")

    # 三档一起看：96 / 48 / 24 的第 0 列
    shots = []
    for path, cell in (("assets/crab_sheet_96.png", 96), ("assets/crab_sheet.png", 48), ("assets/crab_sheet_24.png", 24)):
        im = Image.open(ROOT / path).convert("RGBA")
        shots.append((im.crop((0, 0, cell, cell)), cell))
    S = 4
    maxw = max(c * S for _, c in shots)
    pv = Image.new("RGB", (maxw * 3 + 32, max(c * S for _, c in shots) + 16), (26, 34, 44))
    x = 8
    for img, c in shots:
        big = img.resize((c * S, c * S), Image.NEAREST)
        back = Image.new("RGB", big.size, (44, 54, 64))
        back.paste(big, (0, 0), big)
        pv.paste(back, (x, 8))
        x += maxw + 8
    pv.save(ROOT / "evidence" / "51_three_sizes.png")
    print("已写出 evidence/51_three_sizes.png")


if __name__ == "__main__":
    main()
