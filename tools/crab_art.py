"""螃蟹动作卡的绘制核心。

设计来自图片生成模型产出的角色母版（assets/source/gpt_crab_reference.png）：
宽圆蟹壳、奶油色腹甲、两只大而高举的钳子、四对短腿、黑眼白高光、深色描边。
这里用程序按同一套比例与配色重建 16 帧，保证帧间完全一致（64×64，锚点在底部中央）。
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

CW = CH = 64

P = {
    "outline": (58, 26, 10),
    "shell": (240, 106, 32),
    "shell_hi": (250, 141, 66),
    "shell_sh": (196, 74, 20),
    "belly": (250, 214, 168),
    "belly_sh": (232, 178, 128),
    "eye": (26, 20, 18),
    "eye_hi": (255, 255, 255),
    "blush": (247, 158, 143),
    "claw": (243, 116, 40),
    "claw_hi": (252, 159, 90),
    "claw_sh": (198, 78, 22),
    "leg": (226, 92, 28),
    "leg_sh": (186, 66, 18),
}


def _mirror_box(x0, x1):
    return [min(x0, x1), 0, max(x0, x1), 0]


def rrect(d, x0, y0, x1, y1, fill, outline=None, r=0):
    if r:
        d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline)
    else:
        d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)],
                    fill=fill, outline=outline)


def draw_legs(d, cx, cy, phase, side):
    """每侧 4 条短腿；四帧交错抬腿。"""
    lifts = [(0, 3, 0, 3), (1, 1, 3, 1), (3, 0, 3, 0), (1, 3, 1, 3)][phase]
    for i in range(4):
        lift = lifts[i]
        y0 = cy + 4 + i * 3
        x0 = cx + side * 15
        hw = 6 - (i // 2)
        # 大腿（水平）
        rrect(d, x0, y0, x0 + side * hw, y0 + 3, P["leg"])
        # 小腿（垂直向下）
        vx = x0 + side * hw
        rrect(d, vx, y0, vx + side * 3, y0 + 7 - lift, P["leg_sh"])
        # 脚尖
        rrect(d, vx, y0 + 5 - lift, vx + side * 5, y0 + 7 - lift, P["outline"])


def _finger(d, bx, by, angle_deg, length, s):
    """一根钳指：先画深色描边，再叠亮色内芯。"""
    a = math.radians(angle_deg)
    ex = bx + s * math.cos(a) * length
    ey = by - math.sin(a) * length
    d.line([(bx, by), (ex, ey)], fill=P["outline"], width=7)
    d.line([(bx, by), (ex, ey)], fill=P["claw"], width=4)
    d.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=P["outline"])
    d.ellipse([ex - 1, ey - 1, ex + 1, ey + 1], fill=P["claw_hi"])
    return ex, ey


def draw_claw(d, x, y, open_amt, flip, raise_amt=0):
    """举起的大钳：手臂 + 上下两根张开的手指。"""
    s = 1 if flip else -1
    bx = x + s * 7
    by = y - raise_amt
    # 手臂
    d.line([(x, y + 10), (bx, by + 3)], fill=P["outline"], width=7)
    d.line([(x, y + 10), (bx, by + 3)], fill=P["claw"], width=4)
    # 上指 / 下指：张口由 open_amt 控制
    _finger(d, bx, by, 62 + open_amt * 4, 12, s)
    _finger(d, bx, by, 10 - open_amt * 3, 12, s)
    # 掌心高光
    rrect(d, bx - 2, by - 2, bx + 3, by + 2, P["claw_hi"])


def draw_shell(d, cx, cy, rx, ry, back=False, bob=0):
    # 外描边
    d.rounded_rectangle([cx - rx - 2, cy - ry - 2, cx + rx + 2, cy + ry + 2],
                        radius=ry, fill=P["outline"])
    # 壳主体
    d.rounded_rectangle([cx - rx, cy - ry, cx + rx, cy + ry], radius=ry - 1, fill=P["shell"])
    # 顶部高光
    d.rounded_rectangle([cx - rx + 4, cy - ry + 1, cx + rx - 7, cy - ry + 5],
                        radius=2, fill=P["shell_hi"])
    # 腹甲（奶油色）
    d.rounded_rectangle([cx - rx + 6, cy + ry - 7, cx + rx - 6, cy + ry - 1],
                        radius=3, fill=P["belly"])
    rrect(d, cx - rx + 9, cy + ry - 4, cx + rx - 9, cy + ry - 2, P["belly_sh"])
    # 壳边阴影
    d.arc([cx - rx, cy - ry, cx + rx, cy + ry], 200, 340, fill=P["shell_sh"], width=2)
    if back:
        for dx, dy, r in ((-8, -3, 3), (6, -5, 2), (0, 3, 2)):
            d.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r], fill=P["shell_sh"])


def draw_face(d, cx, cy, look=(0, 0), both=True):
    eyes = [(cx - 7, cy - 1), (cx + 7, cy - 1)] if both else [(cx + 7, cy - 3)]
    for (ex, ey) in eyes:
        d.ellipse([ex - 4, ey - 4, ex + 4, ey + 4], fill=P["eye"])
        rrect(d, ex - 3 + look[0], ey - 3 + look[1], ex - 1 + look[0], ey - 2 + look[1], P["eye_hi"])
    if both:
        rrect(d, cx - 2, cy + 4, cx + 2, cy + 6, P["eye"])      # 嘴
        rrect(d, cx - 12, cy + 3, cx - 9, cy + 5, P["blush"])   # 腮红
        rrect(d, cx + 9, cy + 3, cx + 12, cy + 5, P["blush"])


def draw_under_legs(d, cx, cy, phase):
    """侧视时画在壳下方的四条腿（需在壳之后调用）。"""
    lifts = [(0, 2, 0, 2), (1, 1, 2, 1), (2, 0, 2, 0), (1, 2, 1, 2)][phase]
    for i in range(4):
        lift = lifts[i]
        x = cx - 10 + i * 7
        y0 = cy + 9
        rrect(d, x, y0, x + 3, y0 + 6 - lift, P["leg"])
        rrect(d, x - 1, y0 + 4 - lift, x + 4, y0 + 6 - lift, P["leg_sh"])


def crab_frame(direction: str, frame: int) -> Image.Image:
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = [0, -1, 0, 1][frame]
    cx, cy = 32, 40 + bob
    open_amt = [0, 3, 0, 2][frame]
    raise_amt = [0, 1, 0, 1][frame]

    if direction == "down":
        draw_legs(d, cx, cy, frame, -1)
        draw_legs(d, cx, cy, frame, +1)
        draw_claw(d, cx - 16, cy - 8, open_amt, False, raise_amt)
        draw_claw(d, cx + 16, cy - 8, open_amt, True, raise_amt)
        draw_shell(d, cx, cy, 17, 12)
        draw_face(d, cx, cy - 4, look=(0, 1))
    elif direction == "up":
        draw_legs(d, cx, cy, frame, -1)
        draw_legs(d, cx, cy, frame, +1)
        draw_claw(d, cx - 16, cy - 9, open_amt, False, raise_amt)
        draw_claw(d, cx + 16, cy - 9, open_amt, True, raise_amt)
        draw_shell(d, cx, cy, 17, 12, back=True)
    else:  # right 侧视；left 整帧镜像
        draw_claw(d, cx + 7, cy - 9, open_amt, True, raise_amt)
        d.line([(cx - 10, cy - 3), (cx + 1, cy - 5)], fill=P["claw_sh"], width=4)
        draw_shell(d, cx, cy, 14, 12)
        draw_under_legs(d, cx, cy, frame)
        draw_face(d, cx, cy - 6, look=(1, 0), both=False)

    if direction == "left":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img
