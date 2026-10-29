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
| 快照半径 | 客户端按 `ceil(视野半对角)+24` 走 `/ws?t=…&r=…`，服务端仍按 `RADIUS_MAX` 钳制并回显 |

相机数学只有一个纯函数 `cameraTarget()`，绘制和验收共用同一份实现。验收脚本：
`node tools/e2e_camera.js`（三档视口 + 纯函数边界用例，15 项断言，结果写 `evidence/camera.json`）。

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
