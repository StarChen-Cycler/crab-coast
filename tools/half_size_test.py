"""把螃蟹卡片缩到 1/2（96 → 48）的三种像素方案对比。

思路：单纯降采样一定会产生中间色（看起来发虚）。真正让它重新"硬"起来的办法是
**降采样之后再做一次调色板量化**——中间色被吸附到有限色板上，边缘就恢复成硬像素块。

三种方案：
  A. 从当前 96×96 表 → BOX(面积平均) 缩到 48 → 再量化 32 色
  B. 从当前 96×96 表 → NEAREST 抽样到 48 → 再量化 32 色
  C. 从 1254 原图 → 直接 LANCZOS 到 48（只重采样一次）→ 再量化 32 色

输出：assets/gpt/half_test/{A,B,C}.png 与一张对比图 evidence/31_half_compare.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEET96 = ROOT / "assets" / "crab_sheet.png"        # 当前在用的 v3（96×96）
SRC_REF = ROOT / "assets" / "gpt" / "crab_sheet_ref_v3.png"
OUTDIR = ROOT / "assets" / "gpt" / "half_test"
OUTDIR.mkdir(parents=True, exist_ok=True)

HALF = 48
TARGET_H = 34      # 48 画格里的角色高度（96 版是 68，等比一半）
BASE_LINE = 43     # 48 画格里的基线（96 版是 86，等比一半）
COLORS = 32

ROWS = ["down", "left", "right", "up"]


def quantize(img: Image.Image, colors: int = COLORS) -> Image.Image:
    rgb = img.convert("RGB")
    q = rgb.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    q.putalpha(img.getchannel("A"))
    return q


def from_sheet_96(method: Image.Resampling) -> Image.Image:
    sheet = Image.open(SHEET96).convert("RGBA")
    small = sheet.resize((HALF * 4, HALF * 4), method)
    return quantize(small)


def from_ref() -> Image.Image:
    """从原图直接切到 48：只做一次重采样，细节损失最小。"""
    src = Image.open(SRC_REF).convert("RGBA")
    step = src.size[0] / 4.0
    sheet = Image.new("RGBA", (HALF * 4, HALF * 4), (0, 0, 0, 0))

    for r in range(4):
        for c in range(4):
            x0, y0 = round(c * step), round(r * step)
            x1, y1 = round((c + 1) * step), round((r + 1) * step)
            cell = src.crop((x0, y0, x1, y1)).convert("RGBA")
            px = cell.load()
            w, h = cell.size
            for y in range(h):
                for x in range(w):
                    rr, gg, bb, aa = px[x, y]
                    green = gg - max(rr, bb)
                    if green >= 45:
                        px[x, y] = (rr, gg, bb, 0)
                    elif green >= 18:
                        k = (green - 18) / 27.0
                        px[x, y] = (rr, gg, bb, int(aa * (1 - k)))
            bb_ = cell.getbbox()
            if not bb_:
                continue
            crop = cell.crop(bb_)
            scale = TARGET_H / crop.height
            nw = max(1, round(crop.width * scale))
            small = crop.resize((nw, TARGET_H), Image.LANCZOS)
            if nw > HALF - 1:
                small = small.resize((HALF - 1, max(1, round(TARGET_H * (HALF - 1) / nw))), Image.LANCZOS)
                nw = small.size[0]
            layer = Image.new("RGBA", (HALF, HALF), (0, 0, 0, 0))
            layer.paste(small, ((HALF - small.size[0]) // 2, BASE_LINE - small.size[1]), small)
            sheet.paste(layer, (c * HALF, r * HALF))
    return quantize(sheet)


def preview(sheets: dict[str, Image.Image]) -> Image.Image:
    names = list(sheets)
    scale = 3
    cellw = HALF * scale
    gap = 8
    label_h = 22
    W = gap + len(names) * (cellw + gap)
    H = label_h + 4 * (cellw + gap) + gap
    out = Image.new("RGB", (W, H), (26, 34, 44))
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    for i, n in enumerate(names):
        d.text((gap + i * (cellw + gap) + 4, 6), n, fill=(235, 226, 208))
        sh = sheets[n]
        for r in range(4):
            for c in range(4):
                cell = sh.crop((c * HALF, r * HALF, c * HALF + HALF, r * HALF + HALF))
                cell = cell.resize((cellw, cellw), Image.NEAREST)
                back = Image.new("RGB", cell.size, (44, 54, 64))
                back.paste(cell, (0, 0), cell)
                out.paste(back, (gap + i * (cellw + gap), label_h + r * (cellw + gap)))
    return out


def main() -> None:
    variants = {
        "A_96→BOX→32色": from_sheet_96(Image.BOX),
        "B_96→NEAREST→32色": from_sheet_96(Image.NEAREST),
        "C_原图→48→32色": from_ref(),
    }
    for name, img in variants.items():
        key = name.split("_")[0]
        path = OUTDIR / f"{key}.png"
        img.save(path)
        print(f"{name:22s} -> {path.name}  {img.size}  色数 {len(img.convert('RGB').getcolors(99999))}")

    pv = preview(variants)
    (ROOT / "evidence").mkdir(exist_ok=True)
    pv.save(ROOT / "evidence" / "31_half_compare.png")
    print("对比图: evidence/31_half_compare.png")


if __name__ == "__main__":
    main()
