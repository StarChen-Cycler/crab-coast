# 深圳海岸小世界 · 红树林与螃蟹

一个本地运行的 2.5D 像素小场景：固定不滚动的深圳海岸（海水、沙滩、海藻床、红树林、珊瑚礁、台阶、房屋），
加一只可以用 WASD / 方向键四向走动的螃蟹，走路动作由 4 组连续帧（动作卡）循环播放。

![游戏画面](docs/gameplay.png)

> 想加新角色 / 换新场景？完整方法、参数与踩坑记录都在 **[ASSET-PIPELINE.md](ASSET-PIPELINE.md)**（永久备份，照着做即可复用）。

## 在线试玩

直接打开就能玩（无需安装）：

**https://starchen-cycler.github.io/crab-coast/**

> 浏览器自动播放策略：第一次按方向键或点击页面后才会出声（背景音乐）。

## 操作

| 键 | 作用 |
| --- | --- |
| `W` `A` `S` `D` / `↑` `←` `→` `↓` | 四向移动 |
| `T` | 切换角色尺寸（中 48 ↔ 小 24 ↔ 大 96，到两端会反弹） |
| `M` | 静音 / 恢复背景音乐 |

左上角「尺寸」按钮与右上角「音乐」按钮也能做同样的事。

## 怎么运行

三种方式，任选其一（都不需要联网、不需要安装依赖）：

| 方式 | 操作 | 说明 |
| --- | --- | --- |
| 直接双击 | 双击 `index.html` | 纯静态，`file://` 下即可运行 |
| 本地服务器 | 双击 `serve.cmd` | 启动 `http://127.0.0.1:8099/` 并自动打开浏览器 |
| 手动 | `python -m http.server 8099` | 然后访问 `http://127.0.0.1:8099/` |

## 怎么玩

- `W` `A` `S` `D` 或 `↑` `←` `↓` `→`：上下左右移动，松开即停。
- 同时按两个方向时，以**最后按下**的方向为准，不会走出斜线。
- 螃蟹被房屋与边界挡住，走不过去。
- `M` 或右上角「♪ 音乐」按钮：开关背景音乐（状态会记住）。
  浏览器通常不允许自动播放，按任意键或点一下画面后音乐就会起。

## 目录结构

```
crab-coast/
├── index.html              页面骨架（画布 + HUD + 加载提示）
├── main.js                 渲染与输入逻辑
├── serve.cmd               一键本地启动
├── requirements.md         需求台账（reqledger 生成，勿手改）
├── assets/
│   ├── bg_base.png         960×540 固定背景（海水/沙滩/海藻床/红树林/珊瑚礁/台阶/房屋）
│   ├── crab_sheet.png      256×256 动作卡：4 行 × 4 帧，单帧 64×64
│   ├── kelp_strip.png      144×64 海藻摆动 3 帧
│   ├── scene.js            场景元数据（给页面用，file:// 可直接读）
│   ├── scene.json          同上，JSON 版本（给工具/校验用）
│   └── source/
│       └── gpt_crab_reference.png   AI 生成的螃蟹角色母版（设计来源，不参与运行时）
├── music/
│   ├── coast_bgm.mp3       40 秒无缝循环的海边电子 BGM（160 kbps，781 KB）
│   ├── make_bgm.py         BGM 合成器（numpy 程序化生成，可重复、可改谱）
│   ├── bgm.js              网页播放器：自动播放 + 开关按钮 + M 键 + 淡入淡出
│   └── README.md           音乐规格、改谱方式与接入说明
├── tools/
│   ├── build_assets.py     资产生成器：重建上面所有 PNG 与场景数据
│   ├── crab_art.py         螃蟹 16 帧的绘制逻辑（按母版的比例与配色）
│   ├── check_sheet.py      动作卡一致性检查（尺寸/透明角/身体锚点）
│   ├── probe_*.js          浏览器内验收探针（位移、边界、帧序、帧率、背景固定性）
│   ├── make_preview.py     生成 evidence/07_actioncard.png 预览图
│   └── ledger_lifecycle.py 把需求台账推进到已发布（提交→审核→基线→开发→验收→发布）
└── evidence/               验收截图、实测数据与对照说明
```

## 角色与背景是怎么来的

| 部分 | 来源 |
| --- | --- |
| 螃蟹的**设计** | 图片生成模型产出的母版 `assets/source/gpt_crab_reference.png`（见该目录 README） |
| 螃蟹的**16 帧** | `tools/crab_art.py` 按母版的比例与配色用代码重建，保证逐帧一致、无抖动 |
| 海岸**背景** | `tools/build_assets.py` 程序化绘制（Pillow），可重复生成，零外部图片依赖 |
| 海藻摆动 | `kelp_strip.png` 3 帧 + 页面按相位错开播放 |
| 海浪 / 水面闪光 | 运行时用 Canvas 曲线与随机点实时绘制 |
| **背景音乐** | `music/make_bgm.py` 用 numpy 逐个振荡器合成（无任何外部音频素材） |

## 背景音乐

海边悠闲向的电子/芯片音乐：F 大调、96 BPM、16 小节 40 秒**无缝循环**，
配器是脉冲波主旋律 + 木琴琶音 + 三角波贝斯 + 轻打击 + 海浪噪底，走的是老休闲小游戏那种循环感。

重新生成（改谱/改配器见 `music/README.md`）：

```powershell
python music/make_bgm.py
```

不需要音乐时，删掉 `index.html` 末尾的 `<script src="music/bgm.js"></script>` 即可。

没有直接裁切 AI 出的网格图，是因为同一张图里各格的比例与腿部姿态对不齐，
切片后会抖；用代码按母版重建才能得到真正稳定的走路循环。


## 技术规格

| 项 | 值 |
| --- | --- |
| 逻辑画布 | 960 × 540，等比缩放到窗口 |
| 单帧尺寸 | 64 × 64 |
| 动作卡 | 4 行（下/左/右/上）× 4 帧 = 16 帧 |
| 行走帧率 | 8 fps |
| 移动速度 | 110 px/s，按时间增量计算 |
| 渲染 | `requestAnimationFrame`，像素用最近邻放大（`image-rendering: pixelated`） |

## 重新生成资产

```powershell
python tools/build_assets.py     # 重建全部 PNG 与 scene.js / scene.json
python tools/check_sheet.py      # 检查 16 帧的尺寸、透明角与居中偏差
```

资产全部由 `tools/build_assets.py` 程序化绘制（Pillow），因此每次重建结果完全一致，
没有外部图片依赖，整站不向任何域名发请求。

## 验收探针

页面暴露了 `window.__probe`，可在控制台或自动化脚本里直接验证行为：

```js
__probe.state()        // {x, y, dir, frame, moving, pressed}
__probe.press('ArrowRight'); __probe.release('ArrowRight');
__probe.log(true)      // 开始记录帧序号
__probe.frames()       // [{t, dir, idx}, ...]
__probe.fps()          // 实时帧率
```

`evidence/probe_game.json` 是一次完整探针跑出来的结果。
