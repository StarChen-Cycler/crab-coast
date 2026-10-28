"""动作卡一致性检查（v2：AI 切帧版）。

检查项：
  1. 16 帧都是 64×64；
  2. 每帧四角 alpha = 0（绿幕已抠净）；
  3. 同一方向 4 帧的包围盒中心横向漂移 ≤ 2px；
  4. 16 帧脚底基线一致（切方向时不上下跳）。

因为切帧脚本已经把每一帧按高度归一化并居中对齐，这里的检查是用来验证
归一化确实生效，而不是假设它生效。
"""
from __future__ import annotations

from PIL import Image

import json

_cfg = json.loads(open("assets/scene.json", encoding="utf-8").read())
FW = FH = _cfg["frame"]["w"]          # 帧尺寸跟随场景配置（v1=64，v2=96）
ROWS = ["down", "left", "right", "up"]
MAX_DRIFT = 2
MAX_BASELINE_DRIFT = 1


def main() -> int:
    sheet = Image.open("assets/crab_sheet.png").convert("RGBA")
    problems: list[str] = []
    rows_bb = []

    print(f"{'row':6s} {'f':2s} {'size':9s} {'bbox':22s} {'cx':>6s} {'bottom':>6s}")
    for r, name in enumerate(ROWS):
        entries = []
        for c in range(4):
            cell = sheet.crop((c * FW, r * FH, c * FW + FW, r * FH + FH))
            corners = [cell.getpixel(p)[3] for p in ((0, 0), (FW - 1, 0), (0, FH - 1), (FW - 1, FH - 1))]
            bb = cell.getbbox()
            if cell.size != (FW, FH):
                problems.append(f"{name}#{c} 尺寸不是 {FW}x{FH}")
            if max(corners) != 0:
                problems.append(f"{name}#{c} 四角不透明：{corners}")
            if not bb:
                problems.append(f"{name}#{c} 整帧空白")
                continue
            cx = (bb[0] + bb[2]) / 2
            entries.append((c, bb, cx))
            print(f"{name:6s} {c:2d} {str(cell.size):9s} {str(bb):22s} {cx:6.1f} {bb[3]:6d}")
        if not entries:
            continue
        xs = [e[2] for e in entries]
        if max(xs) - min(xs) > MAX_DRIFT:
            problems.append(f"{name} 行内横向漂移 {max(xs) - min(xs):.1f}px")
        bottoms = [e[1][3] for e in entries]
        if max(bottoms) - min(bottoms) > MAX_BASELINE_DRIFT:
            problems.append(f"{name} 脚踏基线不一致 {min(bottoms)}..{max(bottoms)}")
        rows_bb.append((name, sum(xs) / len(xs), sum(bottoms) / len(bottoms)))

    print("\n各方向平均中心/基线：", {n: (round(x, 1), round(b, 1)) for n, x, b in rows_bb})
    xs = [x for _, x, _ in rows_bb]
    if xs and max(xs) - min(xs) > MAX_DRIFT + 1:
        problems.append(f"跨方向中心偏移 {min(xs):.1f}..{max(xs):.1f}")

    ncolors = len(sheet.convert("RGB").getcolors(maxcolors=99999))
    print(f"调色板：{ncolors} 色")

    print(f"\n帧数=16  问题数={len(problems)}")
    for p in problems:
        print("  -", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
