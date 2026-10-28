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
