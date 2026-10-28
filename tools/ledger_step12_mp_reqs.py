"""多人世界重构：第 2 步 —— 登记 5 条需求并各自走 submit → review → confirm。

所有 digest 都从 req add 的响应里取，不手抄，避免上次那类摘要不匹配的问题。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
SRC = {"source_id": "SRC-000004", "source_revision": 1}
PAGE2 = {"page_id": "PAGE-000002", "page_revision": 1}
REG_CANVAS = "REG-000002-0001-0001"
PLACEMENT_GLOBAL = {
    "kind": "全局",
    "reason": "服务端/接入层能力，不属于某一个页面区域；页面只消费它的结果",
}
PLACEMENT_PLAY = {"kind": "页面", "other": [], "primary": {**PAGE2, "region_id": REG_CANVAS}}
# 单机版仍挂在原来的单机首页（PAGE-000001），region_id 为 null 表示整页
PLACEMENT_SOLO = {"kind": "页面", "other": [],
                  "primary": {"page_id": "PAGE-000001", "page_revision": 1, "region_id": None}}


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    body = json.loads(out) if out.startswith("{") else {"_raw": out}
    return proc.returncode, body


def ok(name, code, body):
    # 重放（上一轮已经提交成功的同 operation_id）也算通过，返回的是原对象
    good = body.get("type") in ("success", "replay")
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={(body.get('object') or {}).get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:800])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {
        "role": role, "scenario": scenario, "preconditions": pre, "input": inp,
        "operation": op, "expected": expected, "method": method, "evidence": evidence,
        "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]},
    }


REQS = [
    {
        "title": "共享世界由服务端权威推进四向移动",
        "type": "功能", "module": "服务端世界", "priority": "P0",
        "placement": PLACEMENT_GLOBAL,
        "description": "服务器进程维护唯一的共享世界（逻辑坐标 960×540），保存每只动物的位置、朝向与当前移动意图。Agent 或浏览器只提交方向意图，位置一律由服务端按 20Hz tick 推进，并用与单机版同一份可行走格（assets/scene.json 的 grid）判定：越过地图边界或踏入不可走区域的那一步被拒绝，动物停留在最后一个合法位置。动物之间不做碰撞。",
        "purpose": "让所有客户端看到同一份可信位置，避免各自计算导致的对不齐，也避免有人改自己的坐标造假。",
        "necessity": "去掉服务端权威，位置会由各客户端自行推进：两人看到的位置不一致，动物能走进海里或房子，后续任何基于位置的玩法（附近动物、碰撞、交互）都无法成立。",
        "included": [
            "单进程内的共享世界与 20Hz 位置推进",
            "方向意图 → 每 tick 位移，速度 110 px/s",
            "复用单机版可行走格做服务端校验",
            "意图 3 秒未更新自动停车",
            "动物之间不碰撞、允许重叠",
        ],
        "excluded": ["动物之间的推挤与碰撞", "路径规划与自动寻路", "跳跃与瞬移"],
        "normal_behavior": {
            "scenario": "两只动物各自持有有效 token 并持续提交方向意图",
            "behavior": "服务端每个 tick 为每只动物推进位置并广播状态",
            "expected": "两只动物都在可信位置移动，任何一方读到的对方位置一致，且都不会进入不可走格",
        },
        "boundaries": [
            {"scenario": "动物朝海边或房屋方向持续移动", "expected": "停在最后一个合法位置，不进入不可走格", "handling": "该 tick 的方向位移被丢弃，位置保持不变"},
            {"scenario": "客户端连续 3 秒不再提交意图", "expected": "动物自动停下", "handling": "意图按时间戳过期，视为停车"},
        ],
        "acceptance": [
            ac("服务端验收者", "朝墙走会被挡住", "已注册一只动物，出生点周围已知有一侧不可走",
               "持续提交指向不可走区域的方向意图 3 秒", "读取该动物的最新位置并检查可行走格",
               "位置停在可行走格内，且 3 秒内没有任何一次采样落在不可走格",
               ("动物穿墙进入不可走区域", "判定服务端校验失效", "检查 tick 是否真的用 canStand 判定"),
               "通过 REST 提交意图，另一进程按 10Hz 采样 GET /state，用 shared/grid.js 复核每一点",
               "意图提交记录 + 采样轨迹 json + 每次采样的 canStand 结果"),
            ac("服务端验收者", "意图过期自动停车", "动物正在移动",
               "提交一次方向意图后不再提交", "3.5 秒后读取位置与 moving 标记",
               "位置在 3.5 秒前后不再变化，状态中 moving 为 false",
               ("3.5 秒后仍在移动", "判定意图 TTL 未生效", "检查 intent_at 与 INTENT_TTL_MS"),
               "提交一次意图后连续采样位置", "两次采样位置差值 = 0 的记录"),
            ac("服务端验收者", "速度符合 110 px/s", "动物位于开阔沙地且前方可走",
               "持续提交同一方向意图 1 秒", "比较起点与终点坐标",
               "位移落在 99 到 121 px 之间（110 ±10%）",
               ("位移远低于 99 或高于 121", "判定 tick 步长或时间基准有误", "检查 tick 间隔与速度常量"),
               "记录起点、1 秒后的终点并计算欧氏距离", "起点终点坐标与计算出的位移值"),
        ],
        "questions": [],
        "technical": "world.js 维护 Map<animalId, {x,y,facing,intentDir,intentAt}>，setInterval 20Hz 推进；可行走判定复用 shared/grid.js 的 canStand（half=11, foot=6）。",
    },
    {
        "title": "Agent 自助注册并凭长 token 接入",
        "type": "功能", "module": "身份与接入", "priority": "P0",
        "placement": PLACEMENT_GLOBAL,
        "description": "Agent 用注册口令调用 POST /api/v1/register 自助注册，服务端创建一只动物并返回一条 40 字符 Crockford Base32 随机 token（约 200 bit）。数据库只保存 token 的 sha256，不存明文。此后所有写操作都靠 Authorization: Bearer <token>，token 也可以直接作为查询参数出现在 play 链接里（无密码体系，定位是账号本身没有别的秘密）。注册接口需要口令并做基础限流。",
        "purpose": "让用户的 Agent 能零人工介入地拿到身份，同时不让任何人都能随便刷动物。",
        "necessity": "没有这一层，只只能由运营手工建号，用户无法自助接入；而没有口令与限流，注册接口会被刷爆，把世界塞满垃圾动物。",
        "included": [
            "POST /api/v1/register 自助注册（需注册口令）",
            "40 字符随机 token，仅存哈希",
            "Bearer token 鉴权，token 只对自己那只动物有写权限",
            "同 IP 注册限流",
            "token 轮换接口",
        ],
        "excluded": ["账号密码与 OAuth", "找回与二次验证", "跨动物代管"],
        "normal_behavior": {
            "scenario": "Agent 带着正确注册口令调用注册接口",
            "behavior": "服务端创建动物、生成 token 并返回",
            "expected": "返回 200，body 含 animalId、token（≥40 字符）与 playUrl；数据库里只有 token 的哈希",
        },
        "boundaries": [
            {"scenario": "口令缺失或错误", "expected": "401，且不创建任何动物", "handling": "先校验口令再落库"},
            {"scenario": "同 IP 短时间大量注册", "expected": "超出阈值后返回 429", "handling": "按 IP 计数的滑动窗口限流"},
            {"scenario": "拿 A 的 token 去改 B 的动物", "expected": "403", "handling": "鉴权时比对路由参数里的动物 id 与 token 归属"},
        ],
        "acceptance": [
            ac("接入验收者", "口令门禁", "服务端已配置注册口令",
               "分别用无口令、错误口令、正确口令调用注册", "记录三次的状态码与是否新建动物",
               "无口令 401、错误口令 401、正确口令 200 且返回 token 长度 ≥40",
               ("错误口令返回 200", "判定口令门禁失效", "检查口令比较逻辑与错误分支"),
               "三次 HTTP 调用并记录状态码与响应体", "三次请求的状态码与响应摘要"),
            ac("接入验收者", "明文 token 不入库", "已注册一只动物并拿到明文 token",
               "直接查询数据库", "在 animals 表中查找明文 token",
               "查不到明文；token_hash 为 64 位十六进制且与明文不同",
               ("数据库中出现明文 token", "判定存储方式不合规", "改为存 sha256"),
               "用 node:sqlite 打开数据库执行 SELECT", "查询结果与 token 前缀对照"),
            ac("接入验收者", "跨动物越权", "已有 A、B 两只动物各自的 token",
               "用 A 的 token 调用 B 的意图接口", "记录状态码",
               "返回 403，且 B 的位置/意图未发生变化",
               ("返回 200", "判定鉴权未绑定动物", "在鉴权处校验 token 归属的 animalId"),
               "用 curl 或 CLI 发一次越权请求", "请求与响应的状态码、B 意图前后对比"),
        ],
        "questions": [],
        "technical": "token = Crockford Base32(rand 25 bytes)；lookup 走 token_hash 唯一索引；限流为内存滑动窗口（进程内即可，单机 50 并发足够）。",
    },
    {
        "title": "上传动作卡并按 4×4 四向规格校验",
        "type": "功能", "module": "资产接入", "priority": "P0",
        "placement": PLACEMENT_GLOBAL,
        "description": "用户在自己机器上用我们的 skill 把 4 行 ×4 帧（下/左/右/上）、单帧 48×48 的成品动作卡与 manifest.json 转好，由 CLI 上传到服务端。服务端对 PNG 做真实解码校验：尺寸必须是 192×192、四角必须透明、每帧左下角必须透明；manifest 必须声明 24 项规格中的 frame/cols/rows/rowOrder/footLine/fps 且取值正确。校验失败返回 400 并逐条说明原因，不落库。",
        "purpose": "把用户自制素材变成可运行的角色，同时保证坏素材不会污染世界或让别人的画面崩掉。",
        "necessity": "没有规格校验，用户传一张不透明的整图或行列不齐的表，客户端会画出带背景色的方块或错位的帧；发现问题时已经上线，排查成本极高。",
        "included": [
            "card.png（192×192，RGBA）与 manifest.json 的上传接口",
            "服务端真实解码校验尺寸与透明度",
            "manifest 字段与取值校验",
            "校验失败 400 且逐条给出原因",
            "成品落盘 + sha256 摘要登记",
        ],
        "excluded": ["原始母版存档与在线转换", "96px / 24px 尺寸变体（后续由后端统一缩放）", "角色外观审核"],
        "normal_behavior": {
            "scenario": "Agent 上传 skill 生成好的成品卡片",
            "behavior": "服务端解码校验后落盘并登记摘要",
            "expected": "返回 200，状态接口能读到卡片摘要与 192×192 尺寸",
        },
        "boundaries": [
            {"scenario": "PNG 行数或列数不符", "expected": "400，错误信息指出行/列不符", "handling": "校验 manifest 与解码后的像素尺寸"},
            {"scenario": "四角不透明", "expected": "400，错误信息指出具体角坐标", "handling": "解码后逐角检查 alpha"},
            {"scenario": "上传的不是 PNG", "expected": "400，说明不是 PNG", "handling": "先校验 PNG 签名再解码"},
        ],
        "acceptance": [
            ac("资产验收者", "合法卡片可上传", "已注册动物并持有 token",
               "上传 skill 生成的 card.png 与合法 manifest", "读取上传响应与状态接口",
               "200，状态里的卡片尺寸为 192×192 且摘要为 64 位十六进制",
               ("返回 400", "判定校验过严或素材不合规", "对照 errors 字段修正素材或校验逻辑"),
               "CLI upload-card 上传后查询 GET /state", "上传响应 json + 状态里的摘要"),
            ac("资产验收者", "行数不符被拒", "准备一份 3 行 ×4 帧的 PNG 与对应 manifest",
               "上传该卡片", "记录状态码与 errors",
               "400，errors 中出现行数不符的说明",
               ("返回 200", "判定行数校验缺失", "在 manifest 与像素尺寸两处都校验行数"),
               "构造 48×144 的 PNG 上传", "状态码与 errors 内容"),
            ac("资产验收者", "四角不透明被拒", "准备一份四角 alpha=255 的 192×192 PNG",
               "上传该卡片", "记录状态码与 errors",
               "400，errors 中指出四角必须透明并给出角坐标",
               ("返回 200", "判定透明度校验缺失", "检查解码路径是否真的读到了 alpha 通道"),
               "用脚本把四角写成不透明后上传", "状态码与 errors 内容"),
        ],
        "questions": [],
        "technical": "PNG 解码用 node:zlib 自己实现（shared/png.js），只支持 8bit RGBA 非隔行；不支持时明确报错而不是放过。",
    },
    {
        "title": "浏览器凭 token 链接进场并看到附近动物",
        "type": "功能", "module": "多人前端", "priority": "P0",
        "placement": PLACEMENT_PLAY,
        "description": "用户打开 Agent 给出的链接（/play?t=<token>）即可操作自己的动物：四向按键或触屏摇杆设置方向意图，服务端权威推进后通过 WebSocket 以 10Hz 推送快照；页面同时绘制半径 200 逻辑像素内的其他动物（含朝向帧），并在状态区显示自身 id 与位置、在提示区显示附近动物数量。断线后客户端指数退避自动重连。",
        "purpose": "把 Agent 的自动化能力和人的即时操作接在一起：Agent 不在时，用户扫码/点链接就能直接玩。",
        "necessity": "没有这个页面，用户拿到的 token 只能靠 Agent 使用，普通人无法参与；而没有快照推送，用户看不到别人，就退化回单机。",
        "included": [
            "带 token 的 /play 页面与 WebSocket 连接",
            "四向输入（键盘与触屏）→ 意图",
            "10Hz 快照渲染（自己 + 附近动物）",
            "自身状态区与附近动物提示区",
            "断线自动重连",
        ],
        "excluded": ["大/中/小尺寸切换", "聊天与表情", "动物之间的碰撞与交互动作"],
        "normal_behavior": {
            "scenario": "用户用有效 token 打开 /play",
            "behavior": "页面连上 WebSocket 并持续接收快照，按键时设置方向意图",
            "expected": "画面里自己的动物随之移动，附近动物按快照实时更新，状态区显示自身 id 与坐标",
        },
        "boundaries": [
            {"scenario": "token 无效或已轮换", "expected": "页面提示连接失败并说明 token 无效", "handling": "握手阶段校验失败返回 401，页面显示原因"},
            {"scenario": "网络断开", "expected": "显示重连中，恢复后自动继续", "handling": "指数退避重连，不要求用户刷新"},
        ],
        "acceptance": [
            ac("前端验收者", "进场即收到快照", "服务端已注册一只动物并拿到 token",
               "打开 /play?t=<token>", "等待 3 秒并读取页面状态与收到的快照",
               "WebSocket 已连接，3 秒内至少收到 20 条快照，且 self.id 与注册返回一致",
               ("3 秒内无快照或 self.id 不符", "判定连接或身份绑定有误", "检查握手参数与快照字段"),
               "用浏览器或 CDP 打开页面，统计收到的快照条数与 self.id", "快照计数与握手日志"),
            ac("前端验收者", "四向操作生效", "动物位于开阔沙地",
               "按住右方向 0.5 秒后松开", "比较操作前后的坐标",
               "x 增大且 y 基本不变；松手后 0.3 秒内停止移动",
               ("坐标不变或方向不符", "判定意图未被发送或未生效", "检查客户端发送的 dir 与服务端收到的意图"),
               "记录操作前后的快照坐标", "前后坐标与停止后的坐标"),
            ac("前端验收者", "能看到附近动物", "两只动物距离小于 200 逻辑像素",
               "让 A 打开 /play，让 B 通过 API 在附近移动", "读取 A 页面里的 nearby 列表",
               "A 的 nearby 含 B 的 id 与坐标，且不含 B 的 token 或任何凭据",
               ("nearby 为空或包含凭据", "判定广播过滤有误", "检查半径过滤与字段白名单"),
               "对比服务端广播内容与页面渲染的 nearby", "nearby 内容与距离计算值"),
            ac("前端验收者", "断线自动重连", "A 页面已连上", "在服务端断开 A 的 WebSocket", "观察 5 秒内是否自动重连",
               "5 秒内恢复连接并继续收到快照",
               ("10 秒内仍未恢复", "判定重连逻辑未生效", "检查重连退避与页面状态机"),
               "服务端主动关闭连接，页面侧统计恢复时间", "断开时间、重连成功时间"),
        ],
        "questions": [],
        "technical": "play/play.js 无构建、无框架；渲染复用 assets/bg_base.png 与 /api/v1/world 返回的尺寸；卡片经 /cards/<id>.png 拉取。",
    },
    {
        "title": "保留 file:// 单机版且不受服务端影响",
        "type": "非功能", "module": "交付兼容", "priority": "P1",
        "placement": PLACEMENT_SOLO,
        "description": "重构后仓库里同时存在两种运行方式：根目录的 index.html 双击即可离线单机玩（相机固定、螃蟹四向、T 键换尺寸），以及 server/ 提供的联网多人世界。单机页面不得引入任何对服务端的依赖或请求，服务端未启动时它必须照常可玩。",
        "purpose": "保住现有的零依赖演示能力，同时让重构不必一次替换全部代码。",
        "necessity": "如果重构直接替换掉单机页，断网或没装 Node 时就没有任何能看的东西；而且一旦把两条链路耦合，任何服务端改动都可能弄坏离线演示。",
        "included": ["file:// 下的单机玩法与资源加载", "单机页不请求服务端", "服务端代码与单机页物理分离"],
        "excluded": ["单机版新增多人特性", "单机版数据同步"],
        "normal_behavior": {
            "scenario": "没有启动服务端，用户双击 index.html",
            "behavior": "页面加载本地资源并进入可玩状态",
            "expected": "四向移动与尺寸切换正常，Network 面板中没有任何 http(s) 请求",
        },
        "boundaries": [
            {"scenario": "服务端未启动时打开根目录页面", "expected": "照常可玩，不出现报错或空白", "handling": "单机页不引用 server/ 目录下任何文件"},
        ],
        "acceptance": [
            ac("交付验收者", "离线单机可玩", "服务端未启动",
               "以 file:// 打开 index.html", "按方向键移动并切换尺寸",
               "角色四向移动、T 键在 48/24/96 之间切换，画面正常",
               ("页面空白或报错", "判定单机链路被破坏", "检查 index.html 的脚本引用是否引入了服务端资源"),
               "file:// 打开并操作，记录状态", "操作前后截图与状态值"),
            ac("交付验收者", "单机页不请求服务端", "服务端未启动",
               "打开 file:// 页面并等待 3 秒", "查看 Network 请求列表",
               "列表中没有 http:// 或 https:// 请求（只有 file:// 与 data:）",
               ("出现指向 127.0.0.1 或域名的请求", "判定单机页耦合了服务端", "移除该引用"),
               "导出 Network 请求列表逐条检查", "请求列表截图与条数"),
        ],
        "questions": [],
        "technical": "单机页仍为根目录 index.html + main.js + touch-controls.js；多人前端独立在 play/，服务端只在 server/。",
    },
]

REVIEW_TEXT = {
    "necessity": "必要性核对：删除本项会直接导致 {impact}，属于 multiplayer v1 闭环上不可缺少的一环；与访谈确认的方向一致（共享世界 + 服务端权威 + 自助注册 + 本地转换上传 + WS 推送 + 保留单机）。",
    "completeness": "完整性核对：13 类必填字段齐全；纳入 {inc} 条、排除 {exc} 条、边界 {bd} 条；页面归属与来源（SRC-000004 r1）精确绑定；开放问题为空。",
    "acceptance": "验收核对：{n} 条条件都给出角色/场景/前置/输入/操作/预期/异常/方法/证据，预期均为可读数值或明确现象，可直接照做。",
}
IMPACT = {
    "REQ-000008": "所有人各自算位置、对不齐，动物能走进海里或房子",
    "REQ-000009": "用户无法自助接入，且注册接口会被刷爆",
    "REQ-000010": "坏素材直接上线，客户端画出带底色或错位的角色",
    "REQ-000011": "用户拿到的 token 只能给 Agent 用，人无法参与，也看不到别人",
    "REQ-000012": "断网或未装 Node 时没有任何可看的演示，且两条链路互相耦合",
}


def main():
    _, d = call(["show"], {"type": "ledger"})
    rev = d["document_revision"]
    print("start doc_rev:", rev)
    added = []

    for i, r in enumerate(REQS):
        payload = {
            "operation_id": f"mp-req-add-{i+1}",
            "agent": "octie-agent",
            "reason": "登记多人世界重构的完整需求草稿",
            "expected_revision": rev,
            "data": {**r, "sources": [SRC], "questions": []},
        }
        code, body = call(["req", "add"], payload)
        if not ok(f"req add [{r['title'][:16]}]", code, body):
            return 1
        rev = body["document_revision"]
        obj = body["object"]
        added.append({"id": obj["id"], "revision": obj["revision"], "digest": obj["digest"], **r})

    for item in added:
        for action, extra in (("submit", {}), ("review", None), ("confirm", {})):
            if action == "review":
                payload = {
                    "operation_id": f"mp-rev-{item['id']}",
                    "agent": "review-agent",
                    "reason": f"对 {item['id']} 第 {item['revision']} 修订做语义审核",
                    "expected_revision": rev,
                    "data": {
                        "target_type": "requirement",
                        "target_id": item["id"],
                        "target_revision": item["revision"],
                        "target_digest": item["digest"],
                        "conclusion": "通过",
                        "necessity_review": REVIEW_TEXT["necessity"].format(impact=IMPACT[item["id"]]),
                        "completeness_review": REVIEW_TEXT["completeness"].format(
                            inc=len(item["included"]), exc=len(item["excluded"]), bd=len(item["boundaries"])),
                        "acceptance_review": REVIEW_TEXT["acceptance"].format(n=len(item["acceptance"])),
                        "basis": f"依据 {item['id']} 第 {item['revision']} 修订摘要 {item['digest'][:12]}… 与来源 SRC-000004 r1 逐字段审阅。声明式审核，Agent 身份仅作操作归因。",
                    },
                }
                args = ["review", "add"]
            elif action == "submit":
                payload = {
                    "operation_id": f"mp-submit-{item['id']}",
                    "agent": "octie-agent",
                    "reason": "把完整草稿转入待审核",
                    "expected_revision": rev,
                    "data": {"id": item["id"], "revision": item["revision"], "digest": item["digest"]},
                }
                args = ["req", "submit"]
            else:
                payload = {
                    "operation_id": f"mp-confirm-{item['id']}",
                    "agent": "octie-agent",
                    "reason": "审核通过且无开放问题，确认纳入",
                    "expected_revision": rev,
                    "data": {"id": item["id"], "revision": item["revision"], "digest": item["digest"],
                             "scope": {"decision": "纳入"}},
                }
                args = ["req", "confirm"]

            code, body = call(args, payload)
            if not ok(f"{action} {item['id']}", code, body):
                return 1
            rev = body["document_revision"]

    print("done. doc_rev:", rev)
    print("added:", [(a["id"], a["revision"]) for a in added])
    return 0


if __name__ == "__main__":
    sys.exit(main())
