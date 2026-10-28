"""生成「深圳海岸小世界」的全部游戏资产（像素风）。

产物（全部写入 ../assets/）：
  bg_base.png     960x540  静态固定背景：海水、沙滩、海藻床、红树林、珊瑚礁、台阶、房屋
  kelp_strip.png  3x48x64  海藻摆动动画条（透明背景）
  crab_sheet.png  4x4x64   四向走路动作卡：行=下/左/右/上，列=4 帧
  scene.json      场景元数据：海岸线采样、海藻锚点、障碍矩形、出生点

用法：python tools/build_assets.py
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

W, H = 960, 540
HORIZON = 186
SHORE_BASE = 268

PAL = {
    "deep": (18, 74, 96),
    "deep2": (22, 92, 116),
    "sea": (31, 122, 148),
    "shallow": (63, 176, 196),
    "shallow2": (96, 201, 214),
    "foam": (226, 245, 246),
    "sand": (230, 205, 155),
    "sand2": (214, 184, 128),
    "sand3": (196, 163, 108),
    "wet": (206, 178, 124),
    "kelp": (43, 96, 58),
    "kelp2": (58, 124, 70),
    "kelp3": (86, 158, 88),
    "trunk": (104, 72, 44),
    "trunk2": (78, 52, 32),
    "canopy": (40, 86, 50),
    "canopy2": (54, 110, 62),
    "canopy3": (74, 138, 76),
    "coral": (222, 92, 106),
    "coral2": (240, 132, 132),
    "coral3": (168, 74, 120),
    "coral4": (250, 176, 130),
    "wall": (216, 184, 140),
    "wall2": (192, 158, 116),
    "roof": (150, 66, 56),
    "roof2": (116, 48, 42),
    "win": (255, 214, 122),
    "wood": (166, 124, 78),
    "wood2": (124, 90, 56),
    "outline": (40, 26, 18),
    "rock": (96, 104, 112),
    "rock2": (124, 132, 140),
}


def shore_y(x: float) -> float:
    """海岸线 y 坐标：三段正弦叠加，JS 端读取 scene.json 的采样值。"""
    return (
        SHORE_BASE
        + 26 * math.sin(x / 150.0 + 0.4)
        + 12 * math.sin(x / 61.0 + 1.7)
        + 5 * math.sin(x / 23.0 + 2.9)
    )


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build_background(rng: random.Random) -> Image.Image:
    img = Image.new("RGBA", (W, H), PAL["deep"] + (255,))
    d = ImageDraw.Draw(img)

    # ---- 1. 海水：由远及近的横向色带 ----
    for y in range(0, HORIZON):
        t = y / HORIZON
        c = lerp(PAL["deep"], PAL["sea"], t)
        d.line([(0, y), (W, y)], fill=c)
    for y in range(HORIZON, SHORE_BASE + 40):
        t = (y - HORIZON) / (SHORE_BASE + 40 - HORIZON)
        c = lerp(PAL["sea"], PAL["shallow"], t)
        d.line([(0, y), (W, y)], fill=c)

    # 远处海面波带
    for i in range(26):
        y = 14 + i * 7 + rng.randint(-2, 2)
        x0 = rng.randint(-40, W - 120)
        seg = rng.randint(50, 150)
        d.line([(x0, y), (x0 + seg, y)], fill=PAL["deep2"])

    # ---- 2. 浅水区与珊瑚礁 ----
    shore = [(x, shore_y(x)) for x in range(0, W + 1, 2)]
    reef_band = [(x, y - 30) for x, y in shore]
    d.polygon(reef_band + list(reversed(shore)), fill=PAL["shallow2"])

    # 礁石与珊瑚丛（浅水带）
    for _ in range(42):
        cx = rng.randint(30, W - 30)
        cy = int(shore_y(cx)) - rng.randint(12, 40)
        kind = rng.random()
        if kind < 0.45:
            # 珊瑚头（扇形）
            r = rng.randint(6, 12)
            for i in range(r):
                d.ellipse([cx - r + i, cy - r // 2 + i // 2, cx + r - i, cy + r // 2],
                          outline=PAL["coral2"], width=1)
            d.ellipse([cx - 3, cy - 2, cx + 3, cy + 2], fill=PAL["coral"])
        elif kind < 0.72:
            # 鹿角珊瑚
            d.line([(cx, cy), (cx - 4, cy - 9)], fill=PAL["coral4"], width=2)
            d.line([(cx, cy), (cx + 5, cy - 7)], fill=PAL["coral4"], width=2)
            d.line([(cx + 5, cy - 7), (cx + 8, cy - 11)], fill=PAL["coral4"], width=2)
        else:
            # 紫色软珊瑚
            for i in range(4):
                d.line([(cx + i * 2 - 3, cy), (cx + i * 2 - 3, cy - rng.randint(4, 10))],
                       fill=PAL["coral3"], width=1)

    # ---- 3. 海藻床（浅水带，静态底层） ----
    def kelp_strand(sx, base_y, height, width, color, sway=3.0):
        pts = []
        for k in range(8):
            t = k / 7
            pts.append((sx + math.sin(t * 2.6 + sx * 0.05) * sway * t, base_y - t * height))
        d.line(pts, fill=color, width=width)
        return pts

    # 三处密集海藻丛，保证在画面上明确可辨
    for gx, gy, count, hmin, hmax in (
        (188, 254, 7, 22, 38), (246, 260, 5, 20, 32), (712, 270, 6, 20, 34),
    ):
        for s in range(count):
            sx = gx + rng.randint(-26, 26)
            by = gy + rng.randint(-4, 8)
            kelp_strand(sx, by, rng.randint(hmin, hmax), 2,
                        PAL["kelp"] if s % 3 else PAL["kelp3"])
    # 零散小海藻
    for _ in range(16):
        cx = rng.randint(20, W - 20)
        cy = int(shore_y(cx)) - rng.randint(4, 22)
        for s in range(rng.randint(2, 4)):
            kelp_strand(cx + rng.randint(-12, 12), cy, rng.randint(12, 26), 2,
                        PAL["kelp"] if s % 2 else PAL["kelp2"])

    # ---- 4. 沙滩 ----
    sand_poly = shore + [(W, H), (0, H)]
    d.polygon(sand_poly, fill=PAL["sand"])
    # 湿沙带贴着海岸线
    wet = [(x, y + 2) for x, y in shore] + [(x, y - 10) for x, y in reversed(shore)]
    d.polygon(wet, fill=PAL["wet"])
    # 沙粒噪点
    for _ in range(2600):
        x = rng.randint(0, W - 1)
        y = rng.randint(int(shore_y(x)) + 8, H - 1)
        d.point((x, y), fill=rng.choice([PAL["sand2"], PAL["sand3"]]))

    # ---- 5. 台阶（沙滩中部偏左，自右下向左上通行） ----
    n_steps = 6
    for i in range(n_steps):
        x0 = 286 + i * 13
        y0 = 470 - i * 14
        w = 132 - i * 13
        h = 14
        d.rectangle([x0, y0, x0 + w, y0 + h], fill=PAL["wood"])          # 踏面
        d.line([(x0, y0), (x0 + w, y0)], fill=PAL["sand"])               # 受光边
        d.rectangle([x0, y0 + h - 4, x0 + w, y0 + h], fill=PAL["wood2"])  # 立面阴影
    # 台阶两侧扶手柱
    for i in range(n_steps):
        px = 286 + i * 13
        py = 470 - i * 14
        d.line([(px, py - 10), (px, py)], fill=PAL["wood2"], width=2)
        d.line([(px + 132 - i * 13, py - 10), (px + 132 - i * 13, py)], fill=PAL["wood2"], width=2)
    # 顶部栈道平台
    d.rectangle([286, 372, 452, 396], fill=PAL["wood"])
    for x in range(290, 452, 13):
        d.line([(x, 374), (x, 394)], fill=PAL["wood2"])

    # ---- 6. 房屋（右侧高脚屋） ----
    def house(x, y, w, h, roof_rise):
        d.rectangle([x, y, x + w, y + h], fill=PAL["wall"])
        d.rectangle([x, y, x + 6, y + h], fill=PAL["wall2"])
        d.rectangle([x + w - 6, y, x + w, y + h], fill=PAL["wall2"])
        # 屋顶
        d.polygon([(x - 8, y), (x + w + 8, y), (x + w // 2, y - roof_rise)], fill=PAL["roof"])
        d.polygon([(x - 8, y), (x + w // 2, y - roof_rise), (x + w // 2, y - roof_rise + 6), (x - 8, y + 2)],
                  fill=PAL["roof2"])
        # 窗与门
        d.rectangle([x + 12, y + 16, x + 30, y + 32], fill=PAL["win"])
        d.rectangle([x + 12, y + 16, x + 30, y + 32], outline=PAL["outline"])
        d.rectangle([x + w - 32, y + 16, x + w - 14, y + 32], fill=PAL["win"])
        d.rectangle([x + w - 32, y + 16, x + w - 14, y + 32], outline=PAL["outline"])
        d.rectangle([x + w // 2 - 9, y + h - 26, x + w // 2 + 9, y + h], fill=PAL["wood2"])
        # 高脚
        for px in (x + 8, x + w // 2, x + w - 8):
            d.line([(px, y + h), (px, y + h + 16)], fill=PAL["trunk2"], width=3)

    house(690, 330, 96, 62, 34)
    house(816, 360, 74, 50, 26)

    # ---- 7. 红树林（左右两侧，气生根插入沙/水交界） ----
    def mangrove(cx, cy, scale, rng_):
        # 气生根
        for i in range(rng_.randint(6, 9)):
            ang = math.radians(rng_.uniform(200, 340))
            ln = rng_.uniform(18, 34) * scale
            ex = cx + math.cos(ang) * ln
            ey = cy + abs(math.sin(ang)) * ln * 0.9 + 6
            d.line([(cx + rng_.randint(-10, 10), cy), (ex, ey)], fill=PAL["trunk2"], width=2)
        # 主干
        d.rectangle([cx - 5 * scale, cy - 44 * scale, cx + 5 * scale, cy], fill=PAL["trunk"])
        d.rectangle([cx - 5 * scale, cy - 44 * scale, cx - 2 * scale, cy], fill=PAL["trunk2"])
        # 树冠（三层色，簇状）
        blobs = [
            (0, -58, 34), (-26, -48, 22), (26, -48, 22), (-14, -70, 20), (16, -68, 20),
        ]
        for bx, by, br in blobs:
            r = br * scale
            d.ellipse([cx + bx * scale - r, cy + by * scale - r * 0.8,
                       cx + bx * scale + r, cy + by * scale + r * 0.8], fill=PAL["canopy"])
        for bx, by, br in blobs:
            r = br * scale * 0.72
            d.ellipse([cx + bx * scale - r, cy + by * scale - r * 0.8 - 3 * scale,
                       cx + bx * scale + r, cy + by * scale + r * 0.8 - 3 * scale], fill=PAL["canopy2"])
        for bx, by, br in blobs[:3]:
            r = br * scale * 0.42
            d.ellipse([cx + bx * scale - r, cy + by * scale - r * 0.8 - 6 * scale,
                       cx + bx * scale + r, cy + by * scale + r * 0.8 - 6 * scale], fill=PAL["canopy3"])

    mangrove(64, 306, 1.15, rng)
    mangrove(150, 292, 0.85, rng)
    mangrove(880, 320, 1.0, rng)
    mangrove(806, 300, 0.7, rng)

    # ---- 8. 前景草丛 / 沙滩杂物 ----
    for _ in range(46):
        x = rng.randint(0, W - 1)
        y = rng.randint(470, H - 4)
        for i in range(3):
            d.line([(x + i * 3, y), (x + i * 3 + rng.randint(-2, 2), y - rng.randint(5, 12))],
                   fill=PAL["kelp2"])
    for _ in range(18):
        x = rng.randint(0, W - 1)
        y = rng.randint(int(shore_y(x)) + 20, H - 6)
        d.ellipse([x, y, x + 5, y + 3], fill=PAL["sand3"])

    # ---- 9. 沙滩纹理：沙纹、潮池、礁石、贝壳 ----
    for i in range(9):
        yy = int(SHORE_BASE + 30 + i * 26)
        x = 20
        while x < W - 20:
            seg = rng.randint(50, 130)
            gap = rng.randint(30, 80)
            if yy < H - 12:
                d.line([(x, yy + rng.randint(-3, 3)), (x + seg, yy + rng.randint(-3, 3))],
                       fill=PAL["sand2"])
            x += seg + gap

    # 潮池
    for cx, cy, rw, rh in ((560, 300, 54, 16), (250, 336, 40, 12), (620, 452, 62, 18)):
        d.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=PAL["shallow"])
        d.ellipse([cx - rw + 4, cy - rh + 3, cx + rw - 10, cy + rh - 6], fill=PAL["shallow2"])
        d.arc([cx - rw, cy - rh, cx + rw, cy + rh], 200, 340, fill=PAL["foam"])

    # 礁石
    for cx, cy, s in ((96, 430, 1.0), (452, 300, 0.7), (884, 476, 0.9), (300, 232, 0.6)):
        d.ellipse([cx - 16 * s, cy - 9 * s, cx + 16 * s, cy + 9 * s], fill=PAL["rock"])
        d.ellipse([cx - 13 * s, cy - 8 * s, cx + 6 * s, cy + 1 * s], fill=PAL["rock2"])

    # 贝壳
    for _ in range(14):
        cx = rng.randint(20, W - 20)
        cy = rng.randint(int(shore_y(cx)) + 26, H - 10)
        if rng.random() < 0.5:
            d.arc([cx, cy, cx + 7, cy + 6], 180, 360, fill=PAL["coral4"])
        else:
            d.ellipse([cx, cy, cx + 5, cy + 4], fill=PAL["sand3"])

    # ---- 10. 木栈道：自台阶平台向右延伸至房屋 ----
    for x in range(452, 700, 16):
        d.rectangle([x, 380, x + 15, 404], fill=PAL["wood"])
        d.line([(x, 380), (x, 404)], fill=PAL["wood2"])
    d.rectangle([452, 378, 700, 382], fill=PAL["wood2"])
    d.rectangle([452, 402, 700, 406], fill=PAL["wood2"])
    for px in (456, 560, 660, 696):
        d.line([(px, 404), (px, 424)], fill=PAL["trunk2"], width=3)

    return img


def build_kelp_strip() -> Image.Image:
    """3 帧海藻摆动：48x64，锚点在底部，向上长出带状叶片。"""
    fw, fh, frames = 48, 64, 3
    img = Image.new("RGBA", (fw * frames, fh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for f in range(frames):
        ox = f * fw
        sway = (f - 1) * 2.6
        for s, (bx, top, wdt) in enumerate(((14, 6, 4), (24, 14, 5), (34, 20, 3))):
            pts = []
            for k in range(11):
                t = k / 10
                pts.append((ox + bx + math.sin(t * 2.0 + f * 0.8 + s) * (1.4 + t * sway),
                            62 - t * (62 - top)))
            d.line(pts, fill=(46, 104, 62, 255), width=wdt)
            d.line([(p[0] + 1, p[1]) for p in pts], fill=(72, 140, 78, 255), width=1)
            # 沿茎的叶片
            for k in range(2, 10, 2):
                px, py = pts[k]
                lw = 3 + (k % 3)
                d.ellipse([px - lw, py - 2, px + lw, py + 2], fill=(88, 158, 92, 210))
        d.ellipse([ox + 9, 58, ox + 39, 63], fill=(38, 86, 50, 255))
    return img


# ---------------------------------------------------------------- 螃蟹动作卡
# 螃蟹绘制逻辑在 crab_art.py（按 AI 母版的设计与配色重建 16 帧）
from crab_art import CW, CH, crab_frame  # noqa: E402


def build_crab_sheet() -> Image.Image:
    order = ["down", "left", "right", "up"]
    cells = [[crab_frame(direction, col) for col in range(4)] for direction in order]

    # 统一对齐：用 16 帧并集的包围盒把整体水平居中、脚底落到固定基线，
    # 这样切换方向时角色不会横向漂移或上下跳（帧间 bob 仍然保留）。
    union = None
    for row in cells:
        for c in row:
            bb = c.getbbox()
            if not bb:
                continue
            union = bb if union is None else (
                min(union[0], bb[0]), min(union[1], bb[1]),
                max(union[2], bb[2]), max(union[3], bb[3]),
            )
    dx = round(CW / 2 - (union[0] + union[2]) / 2)
    dy = 58 - union[3]

    sheet = Image.new("RGBA", (CW * 4, CH * 4), (0, 0, 0, 0))
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            layer.paste(cell, (dx, dy))
            sheet.paste(layer, (c * CW, r * CH))
    return sheet


def build_scene_json(rng: random.Random) -> dict:
    kelp = []
    for _ in range(12):
        x = rng.randint(30, W - 30)
        y = int(shore_y(x)) - rng.randint(8, 24)
        kelp.append({"x": x, "y": y, "phase": round(rng.uniform(0, 3), 2),
                     "scale": round(rng.uniform(0.55, 0.82), 2)})
    return {
        "w": W,
        "h": H,
        "horizon": HORIZON,
        "shore": [round(shore_y(x), 1) for x in range(0, W + 1, 4)],
        "shoreStep": 4,
        "kelp": kelp,
        "frame": {"w": CW, "h": CH, "cols": 4, "rows": 4,
                  "order": ["down", "left", "right", "up"]},
        "obstacles": [
            {"x": 690, "y": 392, "w": 96, "h": 62},
            {"x": 816, "y": 410, "w": 74, "h": 50},
            {"x": 30, "y": 262, "w": 70, "h": 60},
            {"x": 858, "y": 276, "w": 60, "h": 56},
        ],
        "spawn": {"x": 470, "y": 430},
        "speed": 110,
        "animFps": 8,
    }


def main() -> None:
    rng = random.Random(20261028)
    bg = build_background(rng)
    bg.convert("RGB").save(ASSETS / "bg_base.png", optimize=True)

    kelp = build_kelp_strip()
    kelp.save(ASSETS / "kelp_strip.png", optimize=True)

    sheet = build_crab_sheet()
    sheet.save(ASSETS / "crab_sheet.png", optimize=True)

    scene = build_scene_json(rng)
    (ASSETS / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=1), encoding="utf-8")
    # 同时输出 JS 版本：file:// 直接双击打开时 fetch 会被 CORS 拦，用 script 引入即可
    (ASSETS / "scene.js").write_text(
        "window.SCENE = " + json.dumps(scene, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )

    for p in ("bg_base.png", "kelp_strip.png", "crab_sheet.png", "scene.json", "scene.js"):
        f = ASSETS / p
        print(f"{p:16s} {f.stat().st_size:7d} bytes")


if __name__ == "__main__":
    main()
