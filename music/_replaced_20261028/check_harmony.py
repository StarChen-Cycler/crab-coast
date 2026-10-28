# -*- coding: utf-8 -*-
"""乐理自检：检查 coast_bgm 有没有"音符重合"和"撞音"

不依赖听觉，直接读 make_bgm 的音符表做静态分析：

  1. 单声部内相邻音符的重叠量（主旋律/琶音/贝斯）
  2. 铺底和弦是否跨小节（不同和弦同时响 → 半音/三全音撞音）
  3. 纵向撞音：每个旋律音与同时发声的贝斯/铺底/琶音音是否构成
     小二度(1) 或 三全音(6)，且该旋律音又不是和弦音
  4. 声部进行：相邻小节铺底每个声部移动了多少半音
  5. 循环处的终止式：末小节和弦 → 开头和弦

用法：
  python music/check_harmony.py
"""

import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('mb', os.path.join(HERE, 'make_bgm.py'))
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)

BEAT, BAR, BARS = mb.BEAT, mb.BAR, mb.BARS
CRASH = (1, 6, 11)          # 小二度 / 三全音 / 大七度（半音类撞音）
pc = lambda m: m % 12
ok_all = True


def mark(ok):
    global ok_all
    if not ok:
        ok_all = False
    return 'OK' if ok else '!!'


def overlaps(notes, tol=0.05):
    """单声部内相邻音符的重叠秒数列表"""
    out = []
    ns = sorted(notes, key=lambda x: x[0])
    for i in range(len(ns) - 1):
        ov = (ns[i][0] + ns[i][1]) - ns[i + 1][0]
        if ov > tol:
            out.append((ns[i], ns[i + 1], ov))
    return out


print('=' * 66)
print('coast_bgm 乐理自检   %g BPM / %d 小节 / 拍长 %.3fs' % (mb.BPM, BARS, BEAT))
print('=' * 66)

# ---------------------------------------------------------------- 1. 单声部重叠
print('\n[1] 单声部相邻音符重叠')
# 容差说明：≤30ms 属于人耳听不出的收尾交叉（正常释音），
# v1 那种 150ms 的小二度重叠才是问题；单声道音源本来就做不到"零交叉"
for name, notes, tol in (('主旋律', mb.lead_notes(), 0.05),
                         ('琶音', mb.arp_notes(), 0.02),
                         ('贝斯', mb.bass_notes(), 0.03)):
    bad = overlaps(notes, tol)
    worst = max((o for _, _, o in bad), default=0.0)
    print('  %-4s 共 %2d 音，重叠 %2d 处，最大 %.3fs   %s'
          % (name, len(notes), len(bad), worst, mark(not bad)))
    for a, b, ov in bad[:5]:
        print('       %.2fs(midi %d) → %.2fs(midi %d) 重叠 %.3fs' % (a[0], a[2], b[0], b[2], ov))

# ---------------------------------------------------------------- 2. 铺底跨小节
print('\n[2] 铺底和弦是否跨小节（会撞和弦）')
worst_pad = 0.0
for start, length, _ in mb.pad_notes():
    bar_end = (int(start / BAR) + 1) * BAR
    worst_pad = max(worst_pad, start + length - bar_end)
print('  最长越界 %.3fs（<=0 表示都在小节线内收尾）  %s' % (worst_pad, mark(worst_pad <= 0.001)))

print('  相邻小节和弦的半音冲突（若跨小节就会听到）：')
for i in range(BARS - 1):
    a = set(pc(p) for p in mb.CHORDS[i][2])
    b = set(pc(p) for p in mb.CHORDS[i + 1][2])
    clash = sorted((x - y) % 12 for x in a for y in b if (x - y) % 12 in CRASH)
    print('    %2d→%2d 小节：%s' % (i + 1, i + 2, ('冲突 %s（已按小节收尾，不会同时响）' % clash) if clash else '无'))

# ---------------------------------------------------------------- 3. 纵向撞音
print('\n[3] 纵向撞音（旋律音 vs 同时发声的贝斯/铺底/琶音）')
pad, arp, bass = mb.pad_notes(), mb.arp_notes(), mb.bass_notes()


def sounding(pool, t):
    return [n for n in pool if n[0] <= t < n[0] + n[1]]


def chord_pcs(bar):
    """该小节的和弦音集合（铺底 + 根音 + 五音 + 琶音）"""
    root = mb.CHORDS[bar][0]
    s = set(pc(p) for p in mb.CHORDS[bar][2])
    s |= set(pc(p) for p in mb.CHORDS[bar][1])
    s |= {pc(root), pc(root + 7)}
    return s


bad = []
for start, length, midi in mb.lead_notes():
    bar = min(int(start / BAR), BARS - 1)
    t = start + min(0.05, length * 0.5)
    others = [n[2] for n in sounding(pad, t) + sounding(bass, t) + sounding(arp, t)]
    cps = chord_pcs(bar)
    for o in others:
        iv = (midi - o) % 12
        if iv in CRASH and pc(midi) not in cps:
            bad.append((start, midi, o, iv, bar + 1))
print('  旋律音 %d 个，撞音 %d 处  %s' % (len(mb.lead_notes()), len(bad), mark(not bad)))
for s, m, o, iv, bar in bad[:12]:
    print('      第%d小节 %.2fs：旋律 midi %d 与 midi %d 构成 %s'
          % (bar, s, m, o, {1: '小二度', 6: '三全音', 11: '大七度'}[iv]))

# ---------------------------------------------------------------- 4. 声部进行
print('\n[4] 铺底的声部进行（相邻小节每个声部移动半音数）')
worst_move = 0
for i in range(BARS - 1):
    a = sorted(mb.CHORDS[i][2])
    b = sorted(mb.CHORDS[i + 1][2])
    mv = [abs(y - x) for x, y in zip(a, b)]
    worst_move = max(worst_move, max(mv))
    shared = sorted(set(pc(p) for p in a) & set(pc(p) for p in b))
    print('    %2d→%2d：移动 %-12s 共同音 %s' % (i + 1, i + 2, mv, shared if shared else '—'))
print('  最大移动 %d 半音（≤7 视为平滑）  %s' % (worst_move, mark(worst_move <= 7)))

# ---------------------------------------------------------------- 5. 终止式
print('\n[5] 循环处终止式')
last_root, first_root = mb.CHORDS[-1][0], mb.CHORDS[0][0]
print('  末小节根音 midi %d → 开头根音 midi %d，上行 %d 半音'
      % (last_root, first_root, (first_root - last_root) % 12))
print('  末小节 C7sus → 开头 Fmaj9 属-主进行  %s'
      % mark((first_root - last_root) % 12 == 5))
tail = mb.lead_notes()[-1]
print('  末个旋律音在 %.2fs 结束，循环长 %.2fs → 末尾休止 %.2fs  %s'
      % (tail[0] + tail[1], mb.LOOP, mb.LOOP - (tail[0] + tail[1]),
         mark(mb.LOOP - (tail[0] + tail[1]) > 0.2)))

print('\n' + '=' * 66)
print('结论：%s' % ('全部通过' if ok_all else '仍有问题，见上面 !! 标记'))
print('=' * 66)
