"""把 AI 的 4×4 动作卡切分、抠绿、归一化到 64×64 的可用精灵。

处理链条（每一步都可复查）：
  1. 按 4×4 等分切格；
  2. 绿幕抠图：按「绿度 = G - max(R,B)」做软阈值，得到带抗锯齿边缘的 alpha；
  3. 取 alpha 包围盒，按高度归一到统一尺寸（消除各帧画得大一点小一点）；
  4. 水平居中、脚底对齐到固定基线（消除帧间漂移）；
  5. 整张表做统一调色板量化，保证 16 帧配色完全一致；
  6. 输出 assets/crab_sheet.png（256×256）与逐帧对照图。

用法：python tools/slice_crab.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "gpt" / "crab_sheet_ref.png"
OUT = ROOT / "assets" / "crab_sheet.png"
PREVIEW = ROOT / "evidence" / "13_crab_slice_preview.png"

FW = FH = 64
TARGET_H = 46          # 归一化后的角色高度（像素）
BASE_LINE = 58         # 脚底基线
ROWS = ["down", "left", "right", "up"]


def cut_green(cell: Image.Image) -> Image.Image:
    """绿幕抠图：绿度越高越透明。"""
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
                # 边缘过渡：越绿越淡，避免锯齿
                k = (green - 18) / 27.0
                px[x, y] = (r, g, b, int(a * (1 - k)))
    return cell


def normalize(cell: Image.Image) -> Image.Image:
    """按高度缩放 + 居中 + 对齐脚底。"""
    bb = cell.getbbox()
    if not bb:
        return Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    crop = cell.crop(bb)
    scale = TARGET_H / crop.height
    nw = max(1, round(crop.width * scale))
    nh = TARGET_H
    small = crop.resize((nw, nh), Image.LANCZOS)
    # 太宽时按宽度再收一次，保证不超出画格
    if nw > FW - 2:
        scale2 = (FW - 2) / nw
        small = small.resize((FW - 2, max(1, round(nh * scale2))), Image.LANCZOS)
        nw, nh = small.size

    out = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    x = (FW - nw) // 2
    y = BASE_LINE - nh
    out.paste(small, (x, y), small)
    return out


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    sheet = src.size[0] / 4.0

    cells: list[list[Image.Image]] = []
    meta = []
    for r, row_name in enumerate(ROWS):
        row = []
        for c in range(4):
            x0 = round(c * sheet)
            y0 = round(r * sheet)
            x1 = round((c + 1) * sheet)
            y1 = round((r + 1) * sheet)
            cell = cut_green(src.crop((x0, y0, x1, y1)))
            bb = cell.getbbox()
            norm = normalize(cell)
            row.append(norm)
            meta.append({
                "row": row_name, "col": c,
                "src_box": [x0, y0, x1, y1],
                "crab_box": list(bb) if bb else None,
                "src_size": [x1 - x0, y1 - y0],
            })
        cells.append(row)

    # 16 帧拼一起再做一次统一调色板量化（保留 alpha）
    flat = Image.new("RGBA", (FW * 4, FH * 4), (0, 0, 0, 0))
    for r in range(4):
        for c in range(4):
            flat.paste(cells[r][c], (c * FW, r * FH))

    # 量化：只在 RGB 上做，alpha 保留
    rgb = flat.convert("RGB")
    q = rgb.quantize(colors=40, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    alpha = flat.getchannel("A")
    q.putalpha(alpha)
    q.save(OUT, optimize=True)
    ncolors = len(q.convert("RGB").getcolors(maxcolors=99999))
    print(f"已写出 {OUT.relative_to(ROOT)}  调色板 {ncolors} 色")

    # 逐帧对照（左：原图格子；右：归一化结果）
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

    (ROOT / "assets" / "gpt" / "crab_slice_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
