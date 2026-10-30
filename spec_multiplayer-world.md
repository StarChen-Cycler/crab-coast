# spec_multiplayer-world —— 云服务器多人小世界（v1）

> 依据：2026-10-28 会话访谈（3 轮）+ 台账 `requirements.md` 中的 REQ-000008 … REQ-000015。
> **本文件与台账必须一致**：改这里要同步台账（反之亦然）。与代码冲突时以台账为准。

## 0. 需求映射（审计用）

| 需求 | 内容 | 本文件章节 |
| --- | --- | --- |
| REQ-000008 | 共享世界由服务端权威推进四向移动 | §6 |
| REQ-000009 | Agent 自助注册并凭长 token 接入 | §4 |
| REQ-000010 | 上传动作卡并按 4×4 四向规格校验 | §7 |
| REQ-000011 | 浏览器凭 token 链接进场并看到附近动物 | §3、§8.3 |
| REQ-000012 | 保留 file:// 单机版且不受服务端影响 | §2、§5、§12 |
| REQ-000013 | 无动作卡时先进拖拽上传页 | §3、§8.4 |
| REQ-000014 | Agent 可读取自身与附近动物的动态状态 | §8.2 |
| REQ-000015 | 一条命令在服务器上跑起来且关键参数可配置 | §11、§12 |
| REQ-000016 | 多来源指令按最近按下优先合成 + 每动物最多两个活跃会话（FIFO 淘汰） | §6.1 |
| REQ-000017 | 多人版手机端沿用单机版的摇杆与 ABXY，页面布局一致 | §6.2 |
| REQ-000018 | 手机端相机裁切视角：自己居中跟随、世界边界处相机停住、视野内动物全部绘制 | §6.3、§8.3 |
| REQ-000019 | 后台/旋屏/网络抖动后自动恢复实时连接（快照看门狗 + 可见性体检） | §6.4、§8.3 |
| REQ-000020 | 角色与相机按快照插值平滑渲染（消除 10Hz 整块跳步） | §6.3 |
| REQ-000021 | WebSocket 快照下发世界内全部动物（取消半径裁切） | §6.3、§8.3 |

## 1. 目标

把「双击 index.html 就能玩」的静态单机页面，扩成**部署在云服务器上的共享小世界**：

1. 每个用户（通过自己的 Agent）自助注册，得到一只专属动物和一条唯一 token。
2. Agent 用我们的 skill + CLI 把自制动动作卡转换成成品帧包并上传。
3. Agent 通过 API 控制自己的动物、读取身边状态；也能把**带 token 的链接**交给用户。
4. 用户打开链接后，在网页里四向操作自己的动物，并看到附近的其它动物。

## 2. 非目标（v1 明确不做）

| 不做 | 原因 |
| --- | --- |
| 账号 / 密码 / OAuth | 用户身份就是 token 本身，没有别的秘密 |
| 多人版的大 / 中 / 小尺寸切换 | 需要用户提供多份尺寸素材；将来由后端统一缩放。**单机版仍保留 T 键切换**（见 REQ-000012） |
| 二维码与会话签发层 | token 直接进 URL 即可；用户在自己电脑上打开，不怕看 |
| 环境层（潮汐 / 天气 / 时间）状态 | 字段未定，v1 只给最小集 |
| 可交互物（捡贝壳 / 道具） | 留到下一版 |
| 多世界 / 房间 / 排行榜 | 数据模型预留 `world_id`，但只跑一张图 |
| 容器化与 HTTPS 终止 | 交给外部工具 / 反向代理（REQ-000015 明确排除） |

## 3. 用户旅程

```
用户 → 请自己的 Agent「帮我注册并上传我的动作卡」
Agent → POST /api/v1/register（带注册口令）→ {animalId, token, playUrl}
Agent → 本地跑 skill/convert_card.py：4×4 母版 → 成品帧包 + manifest.json
Agent → POST /api/v1/animals/:id/card（Bearer token）
Agent → 把 playUrl 交给用户；自己用 intent / state 接口控制与观察

用户 → 打开 playUrl
   ├─ 已有可用卡片 → 直接进入游戏（REQ-000011）
   └─ 还没有卡片   → 先进拖拽上传页；上传通过后立即进入游戏（REQ-000013）
```

## 4. 身份与 token（REQ-000009）

- **自助注册**：`POST /api/v1/register`，必须带注册口令（环境变量 `REGISTER_CODE`），并按 IP 限流。
- **token**：40 字符 Crockford Base32（约 200 bit 熵），一次性明文返回；库里只存 `sha256(token)`。
- **token 进 URL**：`https://<host>/play?t=<token>`。没有密码、没有会话层；定位是「账号本身没有别的秘密」。
- **轮换**：`POST /api/v1/animals/:id/rotate-token`。
- **权限**：token 只对自己那只动物有写权限（跨动物访问 403）；读附近状态对所有有效 token 开放。

## 5. 角色朝向（与单机版的差异，REQ-000012 明确并存）

| 版本 | 朝向行为 |
| --- | --- |
| 单机版（根目录 `index.html`） | **保持现状**：螃蟹按角度圆弧转身，同轴移动不翻面 |
| 多人版（`play/` 与之后上传的角色） | **四向各自固定朝向**：`down / left / right / up` 直接对应动作卡四行；不存 `bodyDeg` / `heading` |

服务端只保存一个 `facing`（四值枚举）与位置，客户端按 `facing` 取帧。

## 6. 世界与移动（REQ-000008）

- 逻辑坐标 **960 × 540**，单一共享世界。
- **服务端权威**：可行走格来自现有 `assets/scene.json` 的 `grid`（8px 格，120×67）；客户端与 Agent 只发「方向意图」，服务端按 tick 推进并在越界/入墙时拒绝该步。
- 速度 **110 px/s**；tick **20 Hz**；广播 **10 Hz**。
- 意图 **3 秒** 未更新自动停车。
- 动物之间不做碰撞（允许重叠）。

### 6.1 多来源指令合成与会话上限（REQ-000016）

同一只动物可以被多个来源同时控制（典型：Agent 一个 WebSocket + 人在浏览器一个 WebSocket）。
**服务端不区分来源是 Agent 还是人**，只按连接分别记账：

- 每个来源各自维护「当前按住的方向」。
- 动物的**实际方向 = 最近按下且仍未松开**的那一个。
- 按住 A 再按 B → B 生效；**松开 B 后若 A 仍按着，立即回落到 A**（不会停车）。
- 按住期间客户端周期性续期，使「3 秒无更新即停车」只作用于**真正失联**的来源。
  **续期只续命、不抬高优先级**：每个来源记两个时间戳 —— `pressedAt`（只在方向变化时更新，决定优先级）
  与 `aliveAt`（收到该来源的消息就刷新，决定是否失联）。否则持续续期的一方会永久霸占方向，
  后按的那一方永远抢不过来（这是实现时踩到并修正的坑）。
- **同时最多保持 2 个活跃 WebSocket 会话**：第 3 个连接到来时**接受新连接、主动关闭最早建立的那个（FIFO）**，
  保证「永远是最新两个在线」。被淘汰的一方收到明确关闭原因，且**不得自动重连**——
  否则会与另一路互相顶掉，形成来回踢的循环。

> 这是对 §6「单一 `intentDir`」的扩展；单来源场景是它的退化情形。


### 6.2 多人版手机控件与布局（REQ-000017）

多人前端在手机上**沿用单机版已验证的控件与版式**，不再使用 4 键方 D-pad：

| 项 | 规则（与单机版一致） |
| --- | --- |
| 摇杆 | 左下 132px 半透明圆；摇杆头 58px；死区 **10px**；最大位移 **44px**；按**主导轴**四向（`|dx| >= |dy|` 取水平） |
| ABXY | 右下菱形：Y 74/0、X 12/74、B 136/74、A 68/142（74px）；**四键全部为禁用占位**——多人版没有尺寸轮询（§2），不得为 A 临时编造功能 |
| 收起开关 | 右上（竖屏）/ **顶部居中**（横屏：左右顶角已被 HUD 占用，实测压字后改）；只隐藏摇杆与 ABXY，开关自身保留 |
| 操作带 | 竖屏 `--touch-band: 236px`，收起后归零（画布高度补回操作带）；横屏 0（控件叠加在场景上） |
| 矮屏 | `(orientation: landscape) and (max-height: 560px)` 时 ABXY 缩 **0.78**、摇杆缩 **0.84** |
| 安全区 | 所有固定元素用 `env(safe-area-inset-*)` |
| 桌面 | 不显示控件，键盘 WASD / 方向键保持可用 |

实现方式：`cloud/play/touch.js` 是从单机版 `touch-controls.js` 泛化出的 `createTouchControls()`，
由 `play.js` 注入 `onIntent`（发服务端意图）与 `onCollapse`（重算画布）；**单机版文件一行不改**（REQ-000012）。

### 6.3 相机裁切视角（REQ-000018）

整幅渲染在手机上会把 48px 的角色压到约 20px；按半径裁剪又会在全图上留下「凭空出现/消失」的可见边界。
两条一起用相机裁切解决：

| 项 | 规则 |
| --- | --- |
| 相机窗口 | = 画布 CSS 尺寸；画布位图 1 像素 = 1 CSS 像素（放大交给 `image-rendering: pixelated`），画布贴可用视口左上角（底部扣掉操作带） |
| 跟随 | 自己居中：`camera = clamp(self - 视野/2, 0, 世界 - 视野)`；背景用 `drawImage` 子矩形绘制，其他动物按 `worldToScreen()` 平移 |
| 世界边界 | 相机停住不再跟随，动物继续走到世界边界（屏幕上贴边）；两轴独立钳制 |
| 视野 ≥ 世界 | 可见范围取世界尺寸、在画布内居中（留白 `(画布-世界)/2`），相机固定 (0,0) |
| 可见性 | 视野内的其他动物**全部绘制**，不再按半径 200 隐藏；半径判据只留给 Agent 的 `/state`（§8.2） || 快照半径 | **已取消**（REQ-000021）：WS 固定下发世界内全部动物，前端不再请求半径 |
| 绘制裁剪 | 完全在画布外的动物跳过绘制（纯性能优化，不是可见性规则：能不能看见由快照决定） |

插值渲染（REQ-000020，消除 10Hz 整块跳步）：

| 项 | 规则 |
| --- | --- |
| 位置 | 每帧渲染位置 = `from + (to − from) × alpha`；`from` 取上一帧的渲染值（不跳变），`to` 取最新快照 |
| 计时 | `alpha = clamp((now − startAt) / interval, 0, 1)`；`interval` 取快照到达间隔的 EMA 并钳到 [60, 300]ms |
| 限幅 | 单次追赶距离上限 12px（丢包/瞬移时不会一帧跨很远） |
| 外推 | **不做**：alpha 到 1 后保持目标值（宁可能停一帧，也不要冲过头） |
| 自己的动物 | 同样插值（不做客户端预测，服务端仍是唯一权威） |
| 相机 | 由插值后的自己位置驱动，因此镜头也是连续的 |
| 像素对齐 | 所有绘制坐标取整；背景与角色共用同一份取整，保证「人不会比地面快一像素」 |

参考做法：Unity Netcode for Entities 的 Interpolation 与 Photon Bolt 的 Interpolation vs Extrapolation
都推荐「缓冲一帧 + 在两次快照之间插值」，而不是外推。

相机数学集中在一个纯函数 `cameraTarget(self, view)` 里，绘制与验收共用同一份实现，
所以边界/居中这类断言不会「测试自己另写的一份公式」。

### 6.4 连接的及时恢复（REQ-000019）

手机浏览器切后台或旋屏时，WebSocket 常常既不派发 `close` 也不再送数据（半开连接）。
只监听 `onclose` 会让页面永久停在「快照中断」，只能刷新。规则：

| 机制 | 规则 |
| --- | --- |
| 快照看门狗 | 每 1 秒检查一次，超过 **2.5 秒**没有任何快照即判定失联 → 主动关闭并重连 |
| 可见性体检 | `visibilitychange`（恢复可见）、`pageshow`（bfcache）、`online`、`focus` 各触发一次体检 |
| 显式重建 | `forceReconnect()` 幂等 + 1 秒节流；不依赖 `close` 事件（半开连接往往没有 close） |
| 状态复位 | 恢复后 HUD 立刻回「已连接」并清掉错误样式 |
| 被接管 | `1008 replaced` 不自动重连，保持「已在别处被接管」，避免两个标签页互踢 |
| 尺寸变化 | 旋屏/收起控件只重算相机，不再重新握手（快照是全量的，没有要重谈的半径） |

## 7. 动作卡规格与校验（REQ-000010）

| 项 | 值 |
| --- | --- |
| 网格 | 4 行 × 4 帧（行序：下 / 左 / 右 / 上） |
| 单帧 | 48 × 48，RGBA 透明背景 |
| 整图 | 192 × 192 |
| 脚底基线 | `footLine` 43 |
| 行走帧率 | 8 fps |
| 上传内容 | `card.png` + `manifest.json`（六个字段：frame / cols / rows / rowOrder / footLine / fps） |
| 服务端校验 | 真实解码 PNG：尺寸 192×192、四角 alpha=0、每帧左下角 alpha=0；manifest 字段与取值 |
| 尺寸变体 | v1 只收 48px；96/24 留给将来的后端缩放 |

## 8. 接口

### 8.1 REST（前缀 `/api/v1`）

| 方法 | 路径 | 鉴权 | 用途 |
| --- | --- | --- | --- |
| POST | `/register` | 注册口令 | 注册动物，返回 `{animalId, token, playUrl}` |
| POST | `/animals/:id/card` | Bearer | 上传动作卡（CLI 与浏览器共用） |
| GET | `/animals/:id/card-status` | Bearer | 是否已有可用卡片（REQ-000013 首屏分支用） |
| POST | `/animals/:id/intent` | Bearer | 设置移动意图 `{dir: up|down|left|right|null}` |
| POST | `/animals/:id/rotate-token` | Bearer | 轮换 token |
| GET | `/animals/:id/state` | Bearer | 自身 + 附近 + 世界（REQ-000014） |
| GET | `/world` | 无 | 世界静态信息（宽高、在线数、半径） |
| GET | `/cards/:id.png` | 无 | 卡片图片（公开素材，不含任何凭据） |
| GET | `/healthz` | 无 | 健康检查（含 online） |

### 8.2 状态响应（REQ-000014，Agent 与 WS 快照共用同一构造）

```json
{
  "self": {
    "id": "A-0001", "name": "小螃蟹", "x": 470, "y": 424,
    "facing": "down", "moving": true,
    "card": { "width": 192, "height": 192, "digest": "<64 hex>" }
  },
  "nearby": [
    { "id": "A-0002", "name": "小海龟", "x": 512, "y": 430, "facing": "left", "distance": 42 }
  ],
  "world": { "w": 960, "h": 540, "online": 3, "radius": 200 }
}
```

- `nearby` 按距离升序，只含半径内其他动物；**永不含 token / token_hash / 任何凭据**。
- `radius` 可用查询参数调整，服务端钳到上限并在响应里回显实际值。
- 未上传卡片时 `self.card` 为 `null`，接口照常可用。

### 8.3 WebSocket（浏览器，REQ-000011 / 000019 / 000021）

- 连接 `/ws?t=<token>`；握手校验失败返回 401。**没有半径参数**：WS 固定下发世界内全部动物。
- 服务端 → 客户端（10 Hz）：`{type:"snapshot", t:<服务器毫秒>, self:{...}, nearby:[全部其它动物], world:{w,h,online,radius:null,scope:"all"}}`
  - `t` 是发出时刻，供前端做插值计时（REQ-000020）；
  - `scope:"all"` 表示这次 nearpy 没有做距离裁切；`/state` 仍返回 `scope:"radius"` 与 `radius:200/400`。
- 客户端 → 服务端：`{type:"intent", dir:"up"|"down"|"left"|"right"|null}`
- 重连：`onclose` 指数退避；另有快照看门狗与可见性体检兜住半开连接（§6.4）；视野尺寸变化不再重连。

验收脚本：

| 脚本 | 覆盖 |
| --- | --- |
| `node tools/probe_page.js` | 进场快照、右移、nearby 内容与凭据、断线重连（写 `evidence/page_live.json`） |
| `node tools/probe_smooth.js` | 挂起恢复、旋屏、半开看门狗、接管不重连、逐帧平滑与像素稳定（写 `evidence/smooth.json`） |
| `node tools/probe_visible.js` | 远距离互见、绘制集合、`/state` 半径语义（写 `evidence/visible.json`） |


### 8.4 无卡片时的上传页（REQ-000013）

`/play?t=<token>` 首屏先查 `card-status`：

| 结果 | 首屏 |
| --- | --- |
| 有卡片 | 直接渲染游戏画面并开始收快照 |
| 无卡片 | 渲染拖拽上传区（拖拽 + 点击选择文件），**不渲染游戏画布** |
| token 无效 | 提示 token 无效，不显示上传区 |

上传成功 → 不刷新页面直接切到游戏；上传失败 → 留在上传页并逐条显示服务端返回的 errors。

## 9. 数据模型（SQLite，`node:sqlite`）

```sql
CREATE TABLE animals (
  id            TEXT PRIMARY KEY,      -- A-0001
  name          TEXT NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,  -- sha256(token)
  card_path     TEXT,
  card_digest   TEXT,
  card_w        INTEGER,
  card_h        INTEGER,
  x             REAL NOT NULL,
  y             REAL NOT NULL,
  facing        TEXT NOT NULL DEFAULT 'down',
  intent_dir    TEXT,
  intent_at     INTEGER,
  world_id      TEXT NOT NULL DEFAULT 'w1',
  created_at    INTEGER NOT NULL,
  token_rotated_at INTEGER
);
```

运行时数据（SQLite、上传的卡片）只写 `DATA_DIR`（默认 `data/`，已进 `.gitignore`）。

## 10. 目录结构（两个版本按路径彻底分开）

仓库根 = **本地单机版**；`cloud/` = **云端多人版**。两者互不引用，单机版不请求 `cloud/` 里任何东西，
`cloud/` 只**只读**复用根目录的 `assets/scene.json`（可行走格）与 `assets/bg_base.png`。

> 下文中 `server/`、`shared/`、`play/`、`cli/`、`skill/` 一律指 `cloud/` 下的同名子目录。

```
crab-coast/
├── index.html, main.js, touch-controls.js, assets/, music/   # 本地单机版（file:// 可玩，零依赖零请求）
├── cloud/                                                    # 云端多人版（Node ≥22，唯一依赖 ws）
│   ├── package.json
│   ├── README.md                    # 两个版本的边界与运行方式
│   ├── server/                      # 单进程服务：静态 + REST + WebSocket
│   │   ├── index.js                 # 入口、路由、静态托管、20Hz tick、优雅退出
│   │   ├── config.js                # 环境变量与默认值
│   │   ├── store.js                 # node:sqlite 落盘
│   │   ├── world.js                 # 权威世界：意图 → tick → 位置；buildState 共用
│   │   ├── api.js                   # /api/v1 路由与鉴权（含 me 别名）
│   │   └── ws.js                    # WebSocket 广播（10Hz 快照）
│   ├── shared/                      # 服务端与 CLI 共用（浏览器不 require，改由 /api/v1/world 取配置）
│   │   ├── const.js                 # 世界尺寸 / 速度 / tick / 半径 / 方向 / 卡片规格
│   │   ├── grid.js                  # 可行走格读取与 canStand（读根目录 assets/scene.json）
│   │   ├── png.js                   # 极简 PNG 解码（node:zlib，8bit RGBA 非隔行）
│   │   └── card.js                  # manifest 与卡片像素校验
│   ├── play/                        # 多人前端（/play?t=token），无构建
│   │   ├── index.html
│   │   └── play.js
│   ├── cli/animalctl.js             # register / upload-card / move / state / play-url / rotate-token
│   ├── skill/                       # 给用户 Agent 的技能包
│   │   ├── SKILL.md
│   │   ├── convert_card.py          # 4×4 母版 → 成品帧包 + manifest
│   │   └── make_test_sheet.py       # 生成测试母版（验收用）
│   ├── tools/                       # 端到端验收脚本（e2e_multiplayer.js / e2e_env.js）
│   └── data/                        # 运行时（SQLite + 卡片），已 gitignore
├── tools/                           # 需求台账脚本 + 审计脚本（dev 侧，不属于任一运行版本）
├── docs/ evidence/                  # 截图与实测数据
├── requirements.md                  # 需求台账（reqledger）
└── spec_multiplayer-world.md        # 本文件
```

## 11. 部署与运行（REQ-000015）

```bash
npm install          # 唯一依赖：ws
PORT=8080 REGISTER_CODE=<口令> DATA_DIR=/srv/crab/data npm start
```

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | 8090 | HTTP 端口 |
| `REGISTER_CODE` | `dev-code`（并打印警告） | 注册口令 |
| `DATA_DIR` | `./data` | SQLite 与卡片存放目录，启动时探测可写 |
| `RATE_LIMIT_PER_MIN` | 30 | 每 IP 每分钟注册上限 |

- `/healthz` 返回 `{ok, online, version}`。
- 启动失败（端口占用、目录不可写）打印可读原因并以非零码退出。

## 12. 容量与扩展

- 目标 **50 只同时在线**；单进程 + SQLite + 内存广播足够。
- 为「以后少改」做的三件事：世界状态在内存模型、落盘走 `store.js` 接口（换 Postgres 只改它）；广播按半径订阅（将来分频/分片不改协议）；API 前缀 `/api/v1` 且表里有 `world_id`。

## 13. 验收标准（v1，与台账条件一一对应）

每个条件 ID 都是台账里的真实编号，可直接 `reqledger show` 核对。

| 需求 | 条件 | 验收内容 |
| --- | --- | --- |
| REQ-000008 | AC-000032 | 朝墙走被挡住，3 秒内采样都不落在不可走格 |
| REQ-000008 | AC-000033 | 意图 3 秒过期后自动停车 |
| REQ-000008 | AC-000034 | 1 秒位移落在 99–121 px（110 ±10%） |
| REQ-000009 | AC-000035 | 无口令 401 / 错口令 401 / 正确口令 200 且 token ≥40 字符 |
| REQ-000009 | AC-000036 | 库里查不到明文 token，只有 64 位哈希 |
| REQ-000009 | AC-000037 | 拿 A 的 token 改 B 的动物返回 403 |
| REQ-000010 | AC-000038 | 合法卡片 200，状态里能读到 192×192 与摘要 |
| REQ-000010 | AC-000039 | 3 行卡片被拒，errors 指出行数不符 |
| REQ-000010 | AC-000040 | 四角不透明被拒，errors 指出角坐标 |
| REQ-000010 | AC-000063 | manifest 取值错误（fps=7 / footLine=40）被拒，errors 指出字段且不落库 |
| REQ-000011 | AC-000041 | 进场 3 秒内收到 ≥20 条快照且 self.id 正确 |
| REQ-000011 | AC-000042 | 按右方向 0.5 秒后 x 增大，松手 0.3 秒内停 |
| REQ-000011 | AC-000043 | nearby 含对方 id 与坐标，不含任何凭据 |
| REQ-000011 | AC-000044 | 断线后 5 秒内自动重连并恢复快照 |
| REQ-000012 | AC-000045 | file:// 下四向移动与尺寸切换正常 |
| REQ-000012 | AC-000046 | 单机页 Network 中没有 http(s) 请求 |
| REQ-000013 | AC-000047 | 无卡时首屏是拖拽上传区，不渲染游戏画布 |
| REQ-000013 | AC-000048 | 上传合格卡片 2 秒内切到游戏并收到快照 |
| REQ-000013 | AC-000049 | 不合格卡片停在上传页并显示服务端 errors |
| REQ-000013 | AC-000050 | 已有卡时首屏直接是游戏，不出现上传区 |
| REQ-000014 | AC-000051 | self 含卡片尺寸与摘要 |
| REQ-000014 | AC-000052 | 相距 120 可见、相距 400 不可见 |
| REQ-000014 | AC-000053 | 响应里搜不到任何 token 与哈希 |
| REQ-000014 | AC-000054 | radius=10000 被钳制并回显实际半径 |
| REQ-000015 | AC-000055 | 一条命令启动后 /healthz 与首页均 200 |
| REQ-000015 | AC-000056 | 换 PORT/DATA_DIR/REGISTER_CODE 后生效且数据只写 DATA_DIR |
| REQ-000015 | AC-000057 | /healthz 的 online 随连接变化 |
| REQ-000016 | AC-000058 | 两路同时操作时后按的优先 |
| REQ-000016 | AC-000059 | 松开后回落到仍按住的方向（不停车） |
| REQ-000016 | AC-000060 | 按住超过 3 秒不失效（续期生效） |
| REQ-000016 | AC-000061 | 建立第 3 个连接后最早的被关闭，仍保留最新两个 |
| REQ-000016 | AC-000062 | 服务端不区分来源身份，行为只取决于按下顺序 |
| REQ-000017 | AC-000064 | 摇杆四向各 400ms：方向正确、位移 ≥30px、松手 300ms 内停 |
| REQ-000017 | AC-000065 | 推 (4,3)（<10px 死区）不产生位移 |
| REQ-000017 | AC-000066 | ABXY 四键按下无任何状态变化且带 disabled 类 |
| REQ-000017 | AC-000067 | 收起只藏摇杆与 ABXY、开关保留、--touch-band 归零、画布重算 |
| REQ-000017 | AC-000068 | 390×844 竖屏：控件不越界不重叠、画布不压操作带、收起后居中 |
| REQ-000017 | AC-000069 | 844×390 / 844×260 横屏与桌面均正确（开关在顶部居中且不压 HUD/按键、矮屏缩小、桌面不显示但键盘可用） |
| REQ-000018 | AC-000070 | 390×844：画布位图 = 相机窗口 = CSS 尺寸；自己在可跟随的轴上居中（≤2px）；走 1 秒后相机位移 = 世界位移且屏幕坐标不变 |
| REQ-000018 | AC-000071 | 持续向左/向上：相机停在 (0,0)，动物屏幕坐标继续减小到贴边（世界上边界不可走，用同一份纯函数验证） |
| REQ-000018 | AC-000072 | 持续向右/向下：相机停在 (worldW-w, worldH-h)，动物屏幕坐标继续增大到贴边 |
| REQ-000018 | AC-000073 | 视野内的动物必在快照 nearby 内并被绘制；绘制集合 ⊆ nearby（缺失 0）；握手半径 = 半对角+24 且服务端回显一致 |
| REQ-000018 | AC-000074 | Agent 侧 /state 半径语义不变：默认 200、传 10000 回显 400 |
| REQ-000018 | AC-000075 | 视野大于世界：相机固定 (0,0)、可见范围取世界尺寸、留白按整幅居中，走动画面不动 |
| REQ-000019 | AC-000076 | 挂起 5 秒后恢复可见：2 秒内快照恢复、HUD 回「已连接」 |
| REQ-000019 | AC-000077 | 旋屏（390×844 → 844×390）：2 秒内快照继续到达，不出现「快照中断」 |
| REQ-000019 | AC-000078 | 半开连接（不派发 close、数据停止）：4 秒内重连，且只重建 1 次 |
| REQ-000019 | AC-000079 | 被第三个会话顶掉：10 秒内不重连，HUD 保持「已在别处被接管」 |
| REQ-000020 | AC-000080 | 逐帧采样：相邻帧渲染位移最大 ≤3px（修复前 11px），稳态累计位移与 110px/s 误差 ≤5% |
| REQ-000020 | AC-000081 | 相机相邻帧位移 ≤3px，非零位移帧占比 ≥90% |
| REQ-000020 | AC-000082 | 松手 300ms 后渲染位置与快照真值差 ≤1px，此后不再变化 |
| REQ-000020 | AC-000083 | 静止时连续 5 帧画布像素完全一致（像素对齐、不闪烁） |
| REQ-000021 | AC-000084 | 相距 >RADIUS_MAX 时双方 WS 快照互见，`world.scope="all"` |
| REQ-000021 | AC-000085 | 绘制集合 ⊆ 快照集合（缺失 0）；视野内的都画，远方那只仍在快照里 |
| REQ-000021 | AC-000086 | `/state` 仍按半径过滤：默认 200、传 10000 回显 400；近的在内、远的在外 |
| REQ-000014 | AC-000051…054 | （v2 起补记：nearby 只含其它动物、不含环境层，用户已确认） |

> 自动核对：`python tools/audit_spec_vs_ledger.py`（要求 0 差异）。
