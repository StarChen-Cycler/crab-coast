---
name: crab-coast-card
description: 把用户自制的 4×4 动作卡母版转换成深圳海岸小世界（云端版）可运行的角色，并完成注册与上传。当用户说「把我的小动物放进那个海岸小世界」「上传我的动作卡」「领一个 token 让我能在手机上控我的角色」时使用。
---

# 把小动物放进小世界（云端版）

本技能做三件事：**注册拿到 token → 转换动作卡 → 上传并给出可玩链接**。

一切命令都在仓库的 `cloud/` 目录下执行（`cd cloud`）。

## 前提

- Node ≥ 22（服务端用内置 `node:sqlite`），`npm install` 过一个依赖 `ws`
- Python 3 + Pillow（只用于转换动作卡）
- 你手上有注册口令 `REGISTER_CODE`（服务端的环境变量；本地开发默认 `dev-code`）

## 第 1 步 · 注册

```bash
node cli/animalctl.js register --server http://127.0.0.1:8090 --code <口令> --name 小海龟
```

返回：

```json
{ "animalId": "A-0001", "token": "<40 字符>", "playUrl": "http://…/play?t=<token>" }
```

把它记进环境变量，后面都靠它：

```bash
export CRAB_SERVER=http://127.0.0.1:8090
export CRAB_TOKEN=<token>
export CRAB_ANIMAL=A-0001
```

> token 就是账号本身（没有密码）。它足够长、不好记，**可以直接出现在给用户的链接里**。
> 丢了就用 `rotate-token` 换一个，旧链接随即失效。

## 第 2 步 · 准备母版

需要一张 **4 行 × 4 帧**的网格图，行序固定：

| 行 | 方向 |
| --- | --- |
| 1 | 下（朝向观众） |
| 2 | 左 |
| 3 | 右 |
| 4 | 上（背对观众） |

要求：

- 每格画同一角色的连续 4 帧；**不要**让不同的帧互相重叠或留别人的像素
- 背景用纯绿（`#00FF00` 一类）最省事；`--key auto` 可以按四角取色，适合纯任意色底
- 四角留空、每格左下角留空（转换脚本会自检，服务端也会再校验一次）

## 第 3 步 · 转换

```bash
python skill/convert_card.py raw_sheet.png --out build/card
```

可选参数：`--frame 48`（单帧尺寸）、`--foot 43`（脚底基线）、`--key green|auto`、`--fps 8`。

产出：

```
build/card/card.png        192×192，RGBA，4×4 帧
build/card/manifest.json    frame/cols/rows/rowOrder/footLine/fps
```

脚本会自己检查「四角透明」「每帧左下角透明」「每帧非空」，不合格会直接报错并说明是哪一帧——
这时要回去修母版，**不要**改脚本绕过。

## 第 4 步 · 上传

```bash
node cli/animalctl.js upload-card --dir build/card
```

失败时服务端会逐条列出原因（行数不符、四角不透明、尺寸不对…）。照原因修母版再传。

## 第 5 步 · 交给用户

```bash
node cli/animalctl.js play-url
# → http://127.0.0.1:8090/play?t=<token>
```

把这条链接发给用户：打开就能四向操作自己的小动物、看到附近的其它动物。
**如果这只动物还没上传过动作卡，页面不会显示游戏画面，而是一个拖拽上传页**——用户可以直接把
`card.png` 拖进去（也可以顺便拖入 `manifest.json`），上传通过后立刻进入游戏。

## 第 6 步 · 你自己控制与观察

```bash
node cli/animalctl.js move --dir right      # 也支持 up/down/left/stop
node cli/animalctl.js state                 # 自己 + 附近 + 世界
node cli/animalctl.js state --radius 400 --json
```

- 位置由**服务端**权威推进：你只提交方向意图，碰到海面/房屋/边界会被挡住
- 意图 **3 秒**没有更新会自动停车，所以持续移动要反复提交
- `state` 给的是至少字段：自己、附近（半径内按距离升序）、世界（含在线数）
- 响应里不会有任何人的 token —— 这条是服务端硬保证

## 排错

| 现象 | 原因与处理 |
| --- | --- |
| `401 token 缺失或无效` | token 被轮换过，或复制时少了字符 |
| `401 注册口令缺失或错误` | `--code` 与服务端 `REGISTER_CODE` 不一致 |
| `429 RATE_LIMITED` | 同 IP 注册太频繁，等一分钟 |
| `403 token 不属于这只动物` | `--animal` 填了别人的 id；用 `me` 或自己的 id |
| 上传返回 `四角必须透明` | 母版四角有底色；用 `--key auto` 或手工补透明 |
| 上传返回 `行数必须是 4` | 母版不是 4 行，或行高切错了 |
| 页面一直是上传页 | 该动物还没有卡片；让用户拖一张卡进去，或自己 `upload-card` |
| 页面显示 `token 无效` | 链接里的 token 已失效（轮换过） |
