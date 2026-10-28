#!/usr/bin/env python
"""把用户自制的 4 行 × 4 帧动作卡母版，转换成云端版能直接运行的成品帧包。

输入：一张 4×4 等分网格图，行序 下/左/右/上，背景可以是纯绿幕或纯任一种颜色
输出：<out>/card.png（192×192，RGBA）+ <out>/manifest.json

用法：
    python skill/convert_card.py raw_sheet.png --out build/card
    python skill/convert_card.py raw.png --out build/card --key green --frame 48 --foot 43

做了什么：
  1. 按 4×4 切格（每格取原图 1/4 宽高，不要求原图正好 192×192）
  2. 色键抠背景（默认按绿色程度，对纯色底也有效）
  3. 每帧按内容包围盒裁切，横向居中，脚底统一对齐到 footLine
  4. 缩放到统一单帧尺寸（默认 48）后拼成 192×192
  5. 整表量化到 48 色调色板（无抖动），保证不同帧颜色一致
  6. 校验：四角透明、每帧左下角透明（与服务端校验一致），不通过就报错退出
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image

ORDER = ["down", "left", "right", "up"]
FRAME = 48
COLS = ROWS = 4
FOOT_LINE = 43
FPS = 8
PALETTE = 48


def chroma_key(img: Image.Image, mode: str, tol: int) -> Image.Image:
    """把背景变成透明。mode=green 用绿色程度；mode=auto 取四角主色。"""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size

    if mode == "auto":
        samples = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        key = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
    else:
        key = None

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if key is not None:
                d = max(abs(r - key[0]), abs(g - key[1]), abs(b - key[2]))
                if d <= tol:
                    px[x, y] = (r, g, b, 0)
                continue
            # 绿色程度：G 明显高于 R/B 视为背景
            greenness = g - max(r, b)
            if greenness >= 45:
                px[x, y] = (r, g, b, 0)
            elif greenness >= 18:
                # 软阈值，避免留下一圈绿边
                px[x, y] = (r, g, b, int(a * (1 - (greenness - 18) / 27)))
    return img


def slice_cells(sheet: Image.Image) -> list[list[Image.Image]]:
    w, h = sheet.size
    cw, ch = w // COLS, h // ROWS
    cells = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            row.append(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
        cells.append(row)
    return cells


def fit_frame(cell: Image.Image, frame: int, foot: int) -> Image.Image:
    """按内容包围盒缩放并贴到统一大小的透明格子里，脚底落在 foot 行。"""
    bbox = cell.getbbox()
    out = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
    if not bbox:
        return out
    body = cell.crop(bbox)
    # 让缩放后的高度最多到 foot 行（脚底基线以上）
    max_h = foot
    max_w = frame - 2
    scale = min(max_w / body.width, max_h / body.height, 1.0)
    if scale < 1.0:
        body = body.resize((max(1, round(body.width * scale)), max(1, round(body.height * scale))),
                           Image.LANCZOS)
    if body.width > frame:
        body = body.resize((frame, body.height), Image.LANCZOS)
    x = (frame - body.width) // 2
    y = foot - body.height
    out.paste(body, (x, max(0, y)), body)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default="build/card")
    ap.add_argument("--frame", type=int, default=FRAME)
    ap.add_argument("--foot", type=int, default=FOOT_LINE)
    ap.add_argument("--key", choices=["green", "auto"], default="green")
    ap.add_argument("--tol", type=int, default=28)
    ap.add_argument("--fps", type=int, default=FPS)
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print(f"找不到输入图：{args.src}", file=sys.stderr)
        return 2

    sheet = Image.open(args.src)
    sheet = chroma_key(sheet, args.key, args.tol)
    cells = slice_cells(sheet)

    size = args.frame * COLS
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for r in range(ROWS):
        for c in range(COLS):
            cell = cells[r][c]
            box = cell.getbbox()
            if not box:
                print(f"第 {r + 1} 行第 {c + 1} 帧是空的（抠背景后没有内容）", file=sys.stderr)
                return 3
            canvas.paste(fit_frame(cell, args.frame, args.foot), (c * args.frame, r * args.frame))

    # 统一调色板（无抖动），保证帧间颜色一致
    flat = canvas.convert("RGBA")
    rgb = Image.new("RGB", flat.size, (0, 0, 0))
    rgb.paste(flat, (0, 0), flat)
    q = rgb.quantize(colors=PALETTE, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    out = Image.new("RGBA", flat.size, (0, 0, 0, 0))
    out.paste(q, (0, 0), flat.split()[3])

    # 自检：四角与每帧左下角必须透明（与服务端校验一致）
    px = out.load()
    corners = [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]
    for x, y in corners:
        if px[x, y][3] != 0:
            print(f"自检失败：四角必须透明，({x},{y}) alpha={px[x, y][3]}", file=sys.stderr)
            return 4
    for r in range(ROWS):
        for c in range(COLS):
            if px[c * args.frame, r * args.frame + args.frame - 1][3] != 0:
                print(f"自检失败：第 {r + 1} 行第 {c + 1} 帧左下角不透明", file=sys.stderr)
                return 4

    os.makedirs(args.out, exist_ok=True)
    png_path = os.path.join(args.out, "card.png")
    out.save(png_path, optimize=True)
    manifest = {
        "frame": args.frame, "cols": COLS, "rows": ROWS,
        "rowOrder": ORDER, "footLine": args.foot, "fps": args.fps,
        "source": os.path.basename(args.src),
        "generator": "cloud/skill/convert_card.py",
    }
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✓ {png_path} {out.size}  ({len(flat.split()[3].getcolors() or [])} 段 alpha)")
    print(f"✓ {os.path.join(args.out, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
