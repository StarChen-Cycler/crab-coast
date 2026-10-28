"""把 AI 参考图变成可运行的游戏背景 + 可走网格。

流程（对应需求里「像素与颜色逼近」这一步）：
  1. assets/gpt/scene_ref.png（AI 生成）→ 降采样到 960×540 → 64 色量化 → assets/bg_base.png
  2. 按沙地颜色从背景里提取可走区域，切成 8×8 的网格
  3. 对网格做一次腐蚀，避免角色贴到礁石/树干里
  4. 从水面颜色里采样出水波闪光点
  5. 输出 assets/scene.js / scene.json

用法：python tools/build_scene.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
GPT = ROOT / "assets" / "gpt"
ASSETS = ROOT / "assets"

W, H = 960, 540
CELL = 8
COLS, ROWS = W // CELL, H // CELL
SAND_RATIO = 0.6


def is_sand(c: tuple[int, int, int]) -> bool:
    r, g, b = c
    return r >= 185 and g >= 135 and b <= 195 and (r - b) >= 55 and g >= b - 5


def is_water(c: tuple[int, int, int]) -> bool:
    r, g, b = c
    return b >= 110 and b > r + 30 and g >= r


def main() -> None:
    src = Image.open(GPT / "scene_ref.png").convert("RGB")
    small = src.resize((W, H), Image.LANCZOS)
    bg = small.quantize(colors=64, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    bg.save(ASSETS / "bg_base.png", optimize=True)
    print(f"背景：{src.size} → {bg.size}，调色板 {len(bg.getcolors(maxcolors=999))} 色")

    px = bg.load()

    # --- 单元格级沙地判定 ---
    raw = [[False] * COLS for _ in range(ROWS)]
    for cy in range(ROWS):
        for cx in range(COLS):
            n = 0
            for y in range(cy * CELL, (cy + 1) * CELL):
                for x in range(cx * CELL, (cx + 1) * CELL):
                    if is_sand(px[x, y]):
                        n += 1
            raw[cy][cx] = n / (CELL * CELL) >= SAND_RATIO

    # --- 腐蚀一圈：可走格必须自己与上下左右都是沙地 ---
    walk = [[False] * COLS for _ in range(ROWS)]
    for cy in range(ROWS):
        for cx in range(COLS):
            if not raw[cy][cx]:
                continue
            ok = True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = cx + dx, cy + dy
                    if nx < 0 or ny < 0 or nx >= COLS or ny >= ROWS or not raw[ny][nx]:
                        ok = False
                        break
                if not ok:
                    break
            walk[cy][cx] = ok

    walkable = sum(sum(1 for v in row if v) for row in walk)
    print(f"网格 {COLS}×{ROWS}，可走 {walkable} 格（{walkable / (COLS * ROWS) * 100:.1f}%）")

    # --- 出生点：可走区域里离障碍最远的「最开阔」点 ---
    from collections import deque
    dist = [[-1] * COLS for _ in range(ROWS)]
    q = deque()
    for cy in range(ROWS):
        for cx in range(COLS):
            if not walk[cy][cx]:
                dist[cy][cx] = 0
                q.append((cx, cy))
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS and dist[ny][nx] < 0:
                dist[ny][nx] = dist[cy][cx] + 1
                q.append((nx, ny))
    best, bestd = (COLS // 2, ROWS // 2), -1
    for cy in range(ROWS):
        for cx in range(COLS):
            if walk[cy][cx] and dist[cy][cx] > bestd:
                best, bestd = (cx, cy), dist[cy][cx]
    spawn = {"x": best[0] * CELL + CELL // 2, "y": best[1] * CELL + CELL // 2}
    print(f"出生点：{spawn}（离障碍 {bestd} 格）")

    # --- 水面闪光点 ---
    water = []
    seed = 20261028
    for _ in range(1100):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = int((seed / 0x7FFFFFFF) * (W - 40)) + 20
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = int((seed / 0x7FFFFFFF) * (H * 0.55)) + 8
        if is_water(px[x, y]):
            water.append({
                "x": x, "y": y,
                "phase": round((seed % 628) / 100, 2),
                "speed": round(1.1 + (seed % 90) / 100, 2),
                "len": 2 + (seed % 4),
            })
    print(f"水面闪光点：{len(water)} 个")

    # --- 岸线碎浪：贴着可走沙地的边界外侧，取含水的格子 ---
    def wet_ratio(cx: int, cy: int) -> float:
        wet = total = 0
        for yy in range(cy * CELL, min(cy * CELL + CELL, H)):
            for xx in range(cx * CELL, min(cx * CELL + CELL, W)):
                r_, g_, b_ = px[xx, yy]
                total += 1
                if is_water((r_, g_, b_)) or (r_ > 215 and g_ > 228 and b_ > 228):
                    wet += 1
        return wet / total if total else 0.0

    surf = []
    seed = 777
    for cy in range(ROWS):
        for cx in range(COLS):
            if walk[cy][cx]:
                continue
            if wet_ratio(cx, cy) < 0.40:
                continue
            # 只要挨着可走沙地的那一圈水面（含岸边白沫带）
            near_sand = False
            for ny in range(max(0, cy - 5), min(ROWS, cy + 6)):
                for nx in range(max(0, cx - 5), min(COLS, cx + 6)):
                    if walk[ny][nx]:
                        near_sand = True
                        break
                if near_sand:
                    break
            if not near_sand:
                continue
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            surf.append({
                "x": cx * CELL + CELL // 2,
                "y": cy * CELL + CELL // 2,
                "phase": round((seed % 628) / 100, 2),
                "speed": round(0.7 + (seed % 60) / 100, 2),
                "len": 6 + (seed % 9),
            })
    print(f"岸线碎浪点：{len(surf)} 个")

    scene = {
        "w": W, "h": H,
        "grid": {"cell": CELL, "cols": COLS, "rows": ROWS,
                 "walk": ["".join("1" if v else "0" for v in row) for row in walk]},
        "spawn": spawn,
        "speed": 110,
        "animFps": 8,
        "frame": {"w": 48, "h": 48, "cols": 4, "rows": 4, "footLine": 43,
                  "order": ["down", "left", "right", "up"]},
        "water": water,
        "surf": surf,
    }
    (ASSETS / "scene.json").write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    (ASSETS / "scene.js").write_text(
        "window.SCENE = " + json.dumps(scene, ensure_ascii=False) + ";\n", encoding="utf-8"
    )
    print("已写出 assets/scene.js / scene.json")


if __name__ == "__main__":
    main()
