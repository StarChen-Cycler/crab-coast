# 海岸 BGM（当前版本）

40 秒无缝循环的海边休闲 BGM，用于 `index.html` 的背景音乐。

> **当前在用的是 `seaside_lazy_loop_40s.wav`**（用户提供，2026-10-28 16:43 放入）。
> 之前的两版（更早的 `coast_bgm.mp3`、以及我用 ChatGPT 乐谱合成的那版 `seaside_loop.wav`）
> 都整套归档在 `_replaced_20261028/`，页面不再引用。

## 文件

| 文件 | 说明 |
| --- | --- |
| `seaside_lazy_loop_40s.wav` | **正式音频**：40.000 s，32 kHz 立体声 16-bit，5.12 MB，接缝跳变 0.0019 |
| `seaside_lazy_loop_40s.mp3` | 同内容压缩版（962 KB），想省体积可以切换 |
| `bgm.js` | 网页播放器：自动播放兜底、右上角按钮、`M` 键、淡入淡出 |
| `README.md` | 本文件 |
| `_replaced_20261028/` | 被替换掉的两版音乐与合成脚本，仅存档 |

## 实测参数

| 项 | 值 |
| --- | --- |
| 时长 | 40.000 s（循环点可落在整秒） |
| 采样 | 32 000 Hz / 立体声 / 16-bit PCM |
| 峰值 / RMS | 0.830 / 0.114（比上一版留了更多动态余量，不易糊） |
| 接缝 | 首尾采样跳变 0.0019，而普通相邻差值 p99.9 = 0.413（比值 0.005）→ **无咔哒** |

## 播放器行为（`bgm.js`）

1. 先尝试自动播放；被浏览器拦截时等第一次**按键或点击**再开始（合规、不报错）；
2. 右上角「🔊 音乐」按钮，或键盘 `M` 切换静音；状态存 `localStorage["crab-coast:bgm-muted"]`；
3. 切换音量走 320 ms 淡入淡出，不会有"咔哒"；
4. 音频加载失败会自动隐藏按钮，不影响游戏本身。

`index.html` 只需一行：`<script src="music/bgm.js"></script>`。
换音乐只要改 `bgm.js` 里的文件名，或直接替换同名文件。

## 换成 mp3 版本

把 `bgm.js` 里两处 `seaside_lazy_loop_40s.wav` 改成 `seaside_lazy_loop_40s.mp3` 即可。
注意 mp3 编码器可能引入几十毫秒的 padding，若严格在意循环点，建议保留 wav。

## 历史上被替换掉的两版

| 版本 | 说明 | 现在在哪 |
| --- | --- | --- |
| `coast_bgm.mp3` | 最早的一版（F 大调、44.1 kHz 立体声，781 KB），听感不佳 | `_replaced_20261028/` |
| `seaside_loop.wav` | 我用 ChatGPT 给的乐谱（96 BPM、C–Am–F–G、608 事件）自己合成的版本 | `_replaced_20261028/`（含 `make_bgm.py` 与 `seaside_score.json`） |

如果想复用那套合成流程，`_replaced_20261028/make_bgm.py` 仍在，用法：
`python _replaced_20261028/make_bgm.py <score.json> <out.wav>`。
