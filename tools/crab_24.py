"""把当前 48×48 的精灵表再减半到 24×24（与 48 版共存）。

做法与「方案 B」一致：**最近邻 2:1 抽样**（48→24 是整数倍，等于两次 2:1 减半），
再把整表量化到 24 色，避免出现插值产生的过渡色。

64→48 时踩过的坑同样适用：减半后脚底会往上跑，必须重新对齐到新的基线。

用法：python tools/crab_24.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "crab_sheet.png"        # 当前 48×48 表
OUT = ROOT / "assets" / "crab_sheet_24.png"
PREVIEW = ROOT / "evidence" / "50_crab24_preview.png"

SRC_CELL = 48
OUT_CELL = 24
SRC_FOOT = 43          # 48 版脚底基线
COLORS = 24


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    sheet = src.resize((OUT_CELL * 4, OUT_CELL * 4), Image.NEAREST)

    # 量化（保留 alpha）
    q = sheet.convert("RGB").quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(sheet.getchannel("A"))

    # 找出各方向的 bbox 底边，确认脚底基线
    feet = []
    for r in range(4):
        cell = q.crop((0, r * OUT_CELL, OUT_CELL, r * OUT_CELL + OUT_CELL))
        bb = cell.getbbox()
        if bb:
            feet.append(bb[3])
    print("各方向 bbox 底边:", feet, " → 取 footLine =", max(feet) if feet else 0)

    q.save(OUT, optimize=True)
    print(f"已写出 {OUT.relative_to(ROOT)}  {q.size}  色数 {len(q.convert('RGB').getcolors(99999))}")

    # 预览：24 放大 8 倍 + 48 放大 4 倍并列
    S1, S2 = 8, 4
    w1 = OUT_CELL * S1
    w2 = SRC_CELL * S2
    pv = Image.new("RGB", ((w2 + 8) * 4 + 8, (w1 + 8) * 4 + 30), (26, 34, 44))
    from PIL import ImageDraw
    d = ImageDraw.Draw(pv)
    d.text((8, 6), "左：24×24（新，放大 8 倍）   右：48×48（现有，放大 4 倍）", fill=(235, 226, 208))
    for r in range(4):
        for c in range(4):
            small = q.crop((c * OUT_CELL, r * OUT_CELL, c * OUT_CELL + OUT_CELL, r * OUT_CELL + OUT_CELL)).resize((w1, w1), Image.NEAREST)
            big = src.crop((c * SRC_CELL, r * SRC_CELL, c * SRC_CELL + SRC_CELL, r * SRC_CELL + SRC_CELL)).resize((w2, w2), Image.NEAREST)
            for img, x in ((small, 8 + c * (w2 + 8)), (big, 8 + c * (w2 + 8))):
                pass
        # 简单起见：只显示第 0 行对比
    # 第 0 行：24 与 48 并排
    for i, (img, s) in enumerate(((q, S1), (src, S2))):
        for c in range(4):
            cell = img.crop((c * (OUT_CELL if i == 0 else SRC_CELL), 0,
                             c * (OUT_CELL if i == 0 else SRC_CELL) + (OUT_CELL if i == 0 else SRC_CELL),
                             (OUT_CELL if i == 0 else SRC_CELL)))
            cell = cell.resize((cell.width * s, cell.height * s), Image.NEAREST)
            back = Image.new("RGB", cell.size, (44, 54, 64))
            back.paste(cell, (0, 0), cell)
            pv.paste(back, (8 + c * (w2 + 8) + (w1 - w2) // 2 if i == 0 else 8 + c * (w2 + 8), 26))
    pv.save(PREVIEW)
    print(f"已写出 {PREVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
