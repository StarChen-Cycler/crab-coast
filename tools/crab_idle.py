"""给螃蟹做「静息动作」：身体轻轻浮起 1px，腿不动；偶尔眼睛偷瞄一下。

分割（纯形态学，不手标）：
  1. alpha → MinFilter(5) 腐蚀掉细腿 → MaxFilter(5) 膨胀回身体，得到 body_mask；
  2. alpha − body_mask = 腿。

静息 4 帧：
  f0 基准
  f1 身体整体上移 1px（腿不动；同时把身体原来底边那行补回去，避免出现 1px 透明缝）
  f2 基准
  f3 眼睛横移 1px（眼睛 = 小的深色连通块，且位于上半身；不是所有深色像素）

身体用「整块平移」而不是缩放重采样——平移不改变任何颜色，放大后不会发虚。

输出：assets/crab_idle.png（192×192，4 行 × 4 帧）
      evidence/34_idle_preview.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "crab_sheet.png"
OUT = ROOT / "assets" / "crab_idle.png"
PREVIEW = ROOT / "evidence" / "34_idle_preview.png"

C = 48
ROWS = ["down", "left", "right", "up"]
COLORS = 32
DARK = 92          # 深色阈值
EYE_MIN, EYE_MAX = 3, 45   # 眼睛连通块的面积范围


def split_body_legs(cell: Image.Image) -> tuple[Image.Image, Image.Image]:
    alpha = cell.getchannel("A")
    core = alpha.filter(ImageFilter.MinFilter(5))
    body_mask = core.filter(ImageFilter.MaxFilter(5))

    w, h = cell.size
    body = Image.new("RGBA", cell.size, (0, 0, 0, 0))
    legs = Image.new("RGBA", cell.size, (0, 0, 0, 0))
    src, bm, bp, lp = cell.load(), body_mask.load(), body.load(), legs.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            if a == 0:
                continue
            if bm[x, y] > 0:
                bp[x, y] = (r, g, b, a)
            else:
                lp[x, y] = (r, g, b, a)
    return body, legs


def lift_body(body: Image.Image, dy: int = -1) -> Image.Image:
    """整体平移身体 dy 像素（不平移腿）。"""
    out = Image.new("RGBA", body.size, (0, 0, 0, 0))
    out.paste(body, (0, dy), body)
    return out


def stretch_legs_top(legs: Image.Image) -> Image.Image:
    """把腿层每一列最上面的那个像素向上补 1 px。

    身体上浮 1px 后，腿的顶端会与身体脱开；这里让腿"长 1px"接上去，
    脚底不动，颜色全部来自原有像素，不产生新颜色。
    """
    w, h = legs.size
    lp = legs.load()
    out = legs.copy()
    op = out.load()
    for x in range(w):
        for y in range(h):
            r, g, b, a = lp[x, y]
            if a > 0:
                if y - 1 >= 0 and lp[x, y - 1][3] == 0:
                    op[x, y - 1] = (r, g, b, a)
                break
    return out


def find_eyes(body: Image.Image) -> list[tuple[int, int]]:
    """找眼睛：深色 + 内部（8 邻域不透明）+ 面积落在 EYE_MIN..EYE_MAX 的连通块。"""
    px = body.load()
    w, h = body.size
    seen = [[False] * w for _ in range(h)]
    eyes: list[tuple[int, int]] = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if seen[y][x]:
                continue
            r, g, b, a = px[x, y]
            if a == 0 or max(r, g, b) > DARK:
                continue
            if not all(px[x + dx, y + dy][3] > 0 for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue
            # 连通块
            stack, comp = [(x, y)], []
            seen[y][x] = True
            while stack:
                cx, cy = stack.pop()
                comp.append((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if not (0 <= nx < w and 0 <= ny < h) or seen[ny][nx]:
                            continue
                        rr, gg, bb2, aa = px[nx, ny]
                        if aa == 0 or max(rr, gg, bb2) > DARK:
                            continue
                        if not all(px[nx + ddx, ny + ddy][3] > 0
                                   for ddx in (-1, 0, 1) for ddy in (-1, 0, 1)):
                            continue
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if EYE_MIN <= len(comp) <= EYE_MAX:
                cy = sum(p[1] for p in comp) / len(comp)
                if cy < h * 0.62:          # 只要上半身的深色小团
                    eyes.extend(comp)
    return eyes


def shift_eyes(body: Image.Image, dx: int = 1) -> Image.Image:
    pts = find_eyes(body)
    if not pts:
        return body
    out = body.copy()
    op, src = out.load(), body.load()
    colors = {}
    for x, y in pts:
        colors[(x, y)] = src[x, y]
        op[x, y] = (0, 0, 0, 0)
    for (x, y), c in colors.items():
        nx = x + dx
        if 0 <= nx < body.size[0] and op[nx, y][3] == 0:
            op[nx, y] = c
    return out


def main() -> None:
    sheet = Image.open(SHEET).convert("RGBA")
    out = Image.new("RGBA", (C * 4, C * 4), (0, 0, 0, 0))

    for r, name in enumerate(ROWS):
        base = sheet.crop((0, r * C, C, r * C + C))
        body, legs = split_body_legs(base)

        variants = [
            base,                                                        # f0
            Image.alpha_composite(stretch_legs_top(legs), lift_body(body, -1)),  # f1 身体浮起 + 腿接上
            base,                                                        # f2
            Image.alpha_composite(legs, shift_eyes(body, 1)),             # f3 眼睛瞄一下
        ]
        for c in range(4):
            out.paste(variants[c], (c * C, r * C))

    rgb = out.convert("RGB")
    q = rgb.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(out.getchannel("A"))
    q.save(OUT, optimize=True)
    print(f"已写出 {OUT.relative_to(ROOT)}  {q.size}  色数 {len(q.convert('RGB').getcolors(99999))}")

    S = 4
    from PIL import ImageDraw
    pv = Image.new("RGB", ((C * S + 8) * 5 + 8, C * S + 40), (26, 34, 44))
    d = ImageDraw.Draw(pv)
    d.text((8, 6), "左=基准  右=静息 4 帧（f1 身体浮起 1px，f3 眼睛 +1px）", fill=(235, 226, 208))
    base = sheet.crop((0, 0, C, C)).resize((C * S, C * S), Image.NEAREST)
    back = Image.new("RGB", base.size, (44, 54, 64)); back.paste(base, (0, 0), base)
    pv.paste(back, (8, 26))
    for i in range(4):
        cell = q.crop((i * C, 0, i * C + C, C)).resize((C * S, C * S), Image.NEAREST)
        back = Image.new("RGB", cell.size, (44, 54, 64)); back.paste(cell, (0, 0), cell)
        pv.paste(back, (8 + (i + 1) * (C * S + 8), 26))
    pv.save(PREVIEW)
    print(f"已写出 {PREVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
