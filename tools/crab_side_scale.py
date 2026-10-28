"""按行给螃蟹做「侧视缩小」：正面/背面 100%，左侧/右侧 90%。

为什么不是全图缩，而是按行缩：
  侧身时螃蟹在画面上的投影更宽，视觉上比正视图"占地方"。
  只把侧视两行缩到 90%，转身时就不会突然变大。

实现（在已经归一化好的 96×96 表上做，保证脚底不漂）：
  - 正面/背面：整格 ×0.5  → 96 → 48，脚底 86 → 43
  - 左侧/右侧：整格 ×0.45 → 96 → 43，脚底 86 → 39，再整体下移 4 px 让脚底仍落在 43

用法：python tools/crab_side_scale.py [nearest|lancomp]   # 默认 nearest
产物：assets/crab_sheet.png（192×192）与 evidence/33_side_scale_preview.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "crab_sheet_v3_96.png"      # 归一化好的 96×96 表
OUT = ROOT / "assets" / "crab_sheet.png"
PREVIEW = ROOT / "evidence" / "33_side_scale_preview.png"

CELL = 96
OUT_CELL = 48
BASE_96 = 86          # 源表脚底行
BASE_OUT = 43         # 输出表脚底行
COLORS = 32
SIDE = 0.90           # 侧视缩小比例

ROWS = ["down", "left", "right", "up"]
SIDE_ROWS = {"left", "right"}


def main() -> None:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "nearest").lower()
    resample = Image.LANCZOS if mode.startswith("lan") else Image.NEAREST

    src = Image.open(SRC).convert("RGBA")
    out = Image.new("RGBA", (OUT_CELL * 4, OUT_CELL * 4), (0, 0, 0, 0))

    for r, name in enumerate(ROWS):
        f = (OUT_CELL / CELL) * (SIDE if name in SIDE_ROWS else 1.0)
        size = round(CELL * f)                       # 缩放后的整格边长
        foot_src = round(BASE_96 * f)                # 缩放后脚底所在行
        paste_y = BASE_OUT - foot_src                # 让脚底仍落在 BASE_OUT
        for c in range(4):
            cell = src.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))
            small = cell.resize((size, size), resample)
            dx = c * OUT_CELL + (OUT_CELL - size) // 2
            out.paste(small, (dx, r * OUT_CELL + paste_y), small)
        print(f"{name:6s} 缩放 {f:.2f} → 边长 {size}px  脚底 {foot_src} → 下移 {paste_y}px")

    rgb = out.convert("RGB")
    q = rgb.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(out.getchannel("A"))
    q.save(OUT, optimize=True)
    print(f"已写出 {OUT.relative_to(ROOT)}  {q.size}  色数 {len(q.convert('RGB').getcolors(99999))}")

    # 逐帧对照
    scale = 3
    cw = OUT_CELL * scale
    pv = Image.new("RGB", ((cw + 8) * 4 + 8, (cw + 8) * 4 + 8), (26, 34, 44))
    for r in range(4):
        for c in range(4):
            cell = q.crop((c * OUT_CELL, r * OUT_CELL, c * OUT_CELL + OUT_CELL, r * OUT_CELL + OUT_CELL))
            cell = cell.resize((cw, cw), Image.NEAREST)
            back = Image.new("RGB", cell.size, (44, 54, 64))
            back.paste(cell, (0, 0), cell)
            pv.paste(back, (8 + c * (cw + 8), 8 + r * (cw + 8)))
    pv.save(PREVIEW)
    print(f"已写出 {PREVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
