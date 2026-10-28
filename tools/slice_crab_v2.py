"""切「高分辨率版」螃蟹动作卡：4×4 → 96×96 单帧。

与 v1（slice_crab.py）的区别：
  - 单帧 96×96（不是 64×64），角色高度归一化到 68 px，脚底基线 86
  - 调色板 48 色（帧更大，能容纳更多层次）

其余逻辑（软阈值抠绿、包围盒归一化、整表量化）与 v1 完全一致。

用法：
  python tools/slice_crab_v2.py                       # 默认切 v2 原图
  python tools/slice_crab_v2.py <src.png> [out.png]   # 切任意同布局的 4×4 卡片
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "gpt" / "crab_sheet_ref_v2.png"
OUT = ROOT / "assets" / "crab_sheet.png"
PREVIEW = ROOT / "evidence" / "30_crab_v2_slice_preview.png"

if len(sys.argv) > 1:
    SRC = Path(sys.argv[1]).resolve()
if len(sys.argv) > 2:
    OUT = Path(sys.argv[2]).resolve()

FW = FH = 96          # v2：更大的单帧
TARGET_H = 68         # 角色归一化高度
BASE_LINE = 86        # 脚底基线
COLORS = 48
ROWS = ["down", "left", "right", "up"]


def cut_green(cell: Image.Image) -> Image.Image:
    cell = cell.convert("RGBA")
    px = cell.load()
    w, h = cell.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            green = g - max(r, b)
            if green >= 45:
                px[x, y] = (r, g, b, 0)
            elif green >= 18:
                k = (green - 18) / 27.0
                px[x, y] = (r, g, b, int(a * (1 - k)))
    return cell


def normalize(cell: Image.Image) -> Image.Image:
    bb = cell.getbbox()
    if not bb:
        return Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    crop = cell.crop(bb)
    scale = TARGET_H / crop.height
    nw = max(1, round(crop.width * scale))
    nh = TARGET_H
    small = crop.resize((nw, nh), Image.LANCZOS)
    if nw > FW - 2:
        scale2 = (FW - 2) / nw
        small = small.resize((FW - 2, max(1, round(nh * scale2))), Image.LANCZOS)
        nw, nh = small.size

    out = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    out.paste(small, ((FW - nw) // 2, BASE_LINE - nh), small)
    return out


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    step = src.size[0] / 4.0

    cells: list[list[Image.Image]] = []
    meta = []
    for r, row_name in enumerate(ROWS):
        row = []
        for c in range(4):
            x0, y0 = round(c * step), round(r * step)
            x1, y1 = round((c + 1) * step), round((r + 1) * step)
            cell = cut_green(src.crop((x0, y0, x1, y1)))
            bb = cell.getbbox()
            row.append(normalize(cell))
            meta.append({"row": row_name, "col": c, "src_box": [x0, y0, x1, y1],
                         "crab_box": list(bb) if bb else None, "src_size": [x1 - x0, y1 - y0]})
        cells.append(row)

    flat = Image.new("RGBA", (FW * 4, FH * 4), (0, 0, 0, 0))
    for r in range(4):
        for c in range(4):
            flat.paste(cells[r][c], (c * FW, r * FH))

    rgb = flat.convert("RGB")
    q = rgb.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(flat.getchannel("A"))
    q.save(OUT, optimize=True)
    ncolors = len(q.convert("RGB").getcolors(maxcolors=99999))
    print(f"已写出 {OUT.relative_to(ROOT)}  {q.size}  调色板 {ncolors} 色")

    # 逐帧对照图
    PREVIEW.parent.mkdir(exist_ok=True)
    scale = 2
    pw = (FW * scale + 8) * 4 + 8
    ph = (FH * scale + 8) * 4 + 8
    pv = Image.new("RGB", (pw, ph), (26, 34, 44))
    for r in range(4):
        for c in range(4):
            cell = q.crop((c * FW, r * FH, c * FW + FW, r * FH + FH))
            cell = cell.resize((FW * scale, FH * scale), Image.NEAREST)
            back = Image.new("RGB", cell.size, (28, 36, 46))
            back.paste(cell, (0, 0), cell)
            pv.paste(back, (8 + c * (FW * scale + 8), 8 + r * (FH * scale + 8)))
    pv.save(PREVIEW)
    print(f"已写出 {PREVIEW.relative_to(ROOT)}")

    (ROOT / "assets" / "gpt" / "crab_slice_meta_v2.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
