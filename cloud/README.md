# cloud/ —— 云端多人版（全部新代码都在这里）

> **边界约定（重要）**
>
> | 路径 | 属于 | 运行方式 |
> | --- | --- | --- |
> | 仓库根：`index.html` `main.js` `touch-controls.js` `assets/` `music/` | **本地单机版** | 双击 `index.html`，`file://` 即可；零依赖、零请求 |
> | `cloud/**`（本目录） | **云端多人版** | `npm install` + 一条启动命令；需要 Node ≥ 22 |
>
> 两条线**互不引用**：单机版不会请求 `cloud/` 里的任何东西，`cloud/` 也不会改单机版的文件
> （只**只读**复用根目录的 `assets/scene.json` 与 `assets/bg_base.png`）。
> 台账里凡写 `server/`、`shared/`、`play/`、`cli/`、`skill/`，都指本目录下的同名子目录。

## 目录

```
cloud/
├── package.json          唯一依赖：ws（SQLite 用 Node 22 内置 node:sqlite）
├── server/               单进程服务：静态 + REST + WebSocket
│   ├── index.js          入口、路由、静态托管、tick 与优雅退出
│   ├── config.js         环境变量与默认值（PORT / REGISTER_CODE / DATA_DIR / …）
│   ├── store.js          node:sqlite 落盘（换 Postgres 只改这里）
│   ├── world.js          权威世界：意图 → tick → 位置；buildState 共用
│   ├── api.js            /api/v1 路由与鉴权
│   └── ws.js             WebSocket 广播（10Hz 快照）
├── shared/               服务端与 CLI 共用（浏览器不 require）
│   ├── const.js          世界尺寸 / 速度 / tick / 半径 / 方向 / 卡片规格
│   ├── grid.js           可行走格读取与 canStand（读根目录 assets/scene.json）
│   ├── png.js            极简 PNG 解码（node:zlib）
│   └── card.js           manifest 与卡片像素校验
├── play/                 多人前端（/play?t=token），无构建
├── cli/animalctl.js      Agent 用命令行：register / upload-card / move / state / play-url
├── skill/                给用户 Agent 的技能包（SKILL.md + convert_card.py）
└── data/                 运行时数据（SQLite + 上传的卡片），已 gitignore
```

## 运行

```bash
cd cloud
npm install
REGISTER_CODE=<口令> PORT=8090 npm start
```

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | 8090 | HTTP 端口 |
| `REGISTER_CODE` | `dev-code`（启动时告警） | 注册口令 |
| `DATA_DIR` | `cloud/data` | SQLite 与卡片目录，启动时探测可写 |
| `RATE_LIMIT_PER_MIN` | 30 | 每 IP 每分钟注册上限 |
| `RADIUS_MAX` | 400 | 状态接口可请求的最大半径 |

启动后：

- 本地单机版：`http://127.0.0.1:8090/`
- 多人前端：`http://127.0.0.1:8090/play?t=<token>`
- 健康检查：`http://127.0.0.1:8090/healthz`

## 手机端控件（与单机版一致）

多人前端不再使用 4 键 D-pad，改为单机版已验证的那套：

| 控件 | 规则 |
| --- | --- |
| 左半透明摇杆 | 132px 底座、58px 摇杆头、死区 10px、最大位移 44px、按主导轴四向 |
| 右 ABXY 菱形 | Y/X/B/A 四键**全部禁用占位**（多人版没有尺寸轮询，不为 A 编造功能） |
| 收起/显示开关 | 竖屏右上、横屏顶部居中（左右顶角已被 HUD 占用）；只藏摇杆与 ABXY，开关自身保留 |
| 竖屏操作带 | `--touch-band: 236px`，收起后归零（画布高度补回操作带） |
| 矮屏横屏 | `(max-height: 560px)` 时 ABXY 缩 0.78、摇杆缩 0.84 |
| 安全区 | 所有固定元素用 `env(safe-area-inset-*)` |

实现是 `play/touch.js`（从单机 `touch-controls.js` 泛化的 `createTouchControls()`），由 `play.js` 注入
`onIntent`（发服务端意图）与 `onCollapse`（重算画布）。验收脚本：`node tools/e2e_touch_ui.js`
（复用已开浏览器的 CDP 端口，四档视口断言，结果写 `evidence/touch_ui.json`）。

## 相机裁切视角（手机上看得清）

手机上不再把 960×540 整幅缩进屏幕（那样 48px 的角色只剩约 20px），而是用一块**和屏幕可玩区一样大的
相机窗口**按 1 逻辑像素 = 1 CSS 像素裁切世界：

| 项 | 规则 |
| --- | --- |
| 跟随 | 自己的动物居中，`camera = clamp(self - 视野/2, 0, 世界 - 视野)`，背景用子矩形 `drawImage`、其它动物按 `worldToScreen()` 平移 |
| 世界边界 | 相机停住、动物继续走到世界边界；两轴各自独立钳制 |
| 视野 ≥ 世界 | 可见范围取世界尺寸并在画布内居中（留白 `(画布-世界)/2`），相机固定 (0,0) |
| 可见性 | 视野内动物全部绘制，不按半径隐藏；半径判据只留给 Agent 的 `/state` |
| 快照 | WS 固定下发**世界内全部动物**（`world.scope="all"`），前端不再请求半径 |
| 手感 | 按两次快照之间插值渲染（见下），角色与镜头连续移动而不是每 100ms 跳 11px |

相机数学只有一个纯函数 `cameraTarget()`，绘制和验收共用同一份实现。验收脚本：
`node tools/e2e_camera.js`（三档视口 + 纯函数边界用例，14 项断言，结果写 `evidence/camera.json`）。

## 平滑插值（为什么不再一卡一卡）

服务端 20Hz 推进、10Hz 广播，并把位置取整到像素；直接画最近一条快照就会每 100ms 整块跳 11px
（110px/s ÷ 10Hz）。现在按主流做法（Unity Netcode / Photon Bolt 都推荐「缓冲一帧 + 插值」而非外推）：

| 项 | 规则 |
| --- | --- |
| 插值 | 每帧 `pos = from + (to − from) × alpha`，`from` 取上一帧渲染值（不跳变），`to` 取最新快照 |
| 计时 | `alpha = clamp((now − startAt) / interval, 0, 1)`，`interval` 用快照到达间隔的 EMA 钳到 [60,300]ms |
| 限幅 / 外推 | 单次追赶 ≤12px；不做外推（alpha 到 1 就保持，宁可能停一帧也不冲过头） |
| 相机 | 由插值后的自己位置驱动，因此镜头同样连续；绘制坐标统一取整保持像素对齐 |

实测（`node tools/probe_smooth.js` → `evidence/smooth.json`）：相邻帧渲染位移最大 **2.03px**（修复前 11px），
相机非零位移帧占比 93.4%，松手 300ms 后与快照真值差 **0px**，静止 5 帧画布像素完全一致。

## 连接自愈（切后台 / 旋屏不再卡死在「快照中断」）

手机切后台或旋屏时 WebSocket 常常既不派发 `close` 也不再送数据（半开连接）。只监听 `onclose` 会永久卡住：

| 机制 | 规则 |
| --- | --- |
| 快照看门狗 | 每 1 秒检查，超过 **2.5 秒**无快照即主动重连 |
| 可见性体检 | `visibilitychange` / `pageshow` / `online` / `focus` 各触发一次体检 |
| 显式重建 | `forceReconnect()` 幂等 + 1 秒节流，不依赖 `close` 事件 |
| 被接管 | `1008 replaced` 不自动重连，保持「已在别处被接管」 |

实测（`node tools/probe_smooth.js`）：挂起 5 秒后恢复可见立即健康、半开连接 **704ms** 内重连且只重建 1 次、
被第三个会话顶掉后 10 秒内不再连。

## 演示数据：把测试环境的生物都换成螃蟹

单机版的螃蟹图（`assets/crab_sheet.png`，192×192、4 行 × 4 帧、`footLine` 43、8fps）本来就满足多人版卡片规格，
可以直接当动作卡用。因为 token 只以哈希入库、拿不到别人的明文 token，所以这个工具**直接写卡片文件 + 更新
`animals` 表**，写完要重启服务（页面按 id 拉 `/cards/<id>.png`，`no-cache`，刷新即生效；`state` 里的卡片摘要要等重启）：

```bash
# 先看会改哪些（dry-run）
node tools/seed_crab_cards.js --data <DATA_DIR>
# 真的写入，然后重启服务
node tools/seed_crab_cards.js --apply --data <DATA_DIR>
```

它只动卡片文件与 `card_path/card_digest/card_w/card_h` 四列，不改名字、token、位置。

## 背景音乐（与单机版同一份素材，由服务端供给）

单机版的 40 秒无缝循环海岸 BGM 也接到了多人页：`music/seaside_lazy_loop_40s.wav`（4.88MB，
接缝跳变 0.0019）由服务端直接提供，前端在 `play/bgm.js` 里播放。

| 项 | 规则 |
| --- | --- |
| 加载 | 进入游戏后才建 `Audio`，上传页不拉音频；`loop=true`，音量常量 **0.42**（与单机版 TARGET 一致） |
| 播放 | 浏览器自动播放策略要求手势：首次按键/触摸或点按钮时同步 `play()`，被拦只记状态不报错 |
| 开关 | 按钮在左列第三个（自身 14/14 → 附近 14/56 → 音乐 14/92），`M` 键同效；静音即暂停，偏好存 `localStorage` |
| 可见性 | 切后台暂停、回前台按意愿继续 |
| 回落 | 音频加载失败只隐藏按钮，其它一切照常 |
| 不用 mp3 | 编码器 padding 会破坏无缝循环（`music/README.md` 有实测），所以用 WAV |

服务端为此加了 HTTP Range（移动端可靠取流/循环的前提）：纯函数 `server/range.js` 的 `parseRange()`，
`server/index.js` 的 `serveFile()` 返回 200 / 206 / 416，三者都带 `accept-ranges: bytes`。

```bash
node --test test/range.test.js                    # Range 解析 9 个纯函数单测
node tools/e2e_bgm.js                             # 端到端：Range + 播放/静音/布局/回落/可见性 + 单机版回归
node tools/check_deploy.js http://<host>:8090     # 部署断言：健康检查 + 静态资源指纹 + 音频 Range
```

## Agent 接入（三步）

```bash
# 1. 注册
node cli/animalctl.js register --server http://127.0.0.1:8090 --code <口令> --name 小海龟
# 2. 转换并上传动作卡
python skill/convert_card.py raw_sheet.png --out build/card
node cli/animalctl.js upload-card --server … --token … --animal … --dir build/card
# 3. 控制与观察
node cli/animalctl.js move --token … --animal … --dir right
node cli/animalctl.js state --token … --animal …
```

接口与验收条件的对应关系见仓库根的 `spec_multiplayer-world.md`。
