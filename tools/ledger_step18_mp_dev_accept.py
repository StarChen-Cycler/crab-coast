"""多人世界重构：第 8 步 —— 开发与验收登记。

按台账顺序：dev start → dev complete → acceptance record（26 条）→ release add → change close。
所有 expected_revision 从响应递推；implemented_event_id 从 dev complete 的响应里取。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
BASELINE = "BASE-000007"
DELIVERY = "crab-coast-v7"
NEW_IDS = [f"REQ-{n:06d}" for n in range(8, 16)]


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def show(payload):
    p = subprocess.run(["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
                       input=json.dumps(payload).encode(), capture_output=True)
    return json.loads(p.stdout.decode("utf-8", "replace"))


def ok(name, code, body):
    good = body.get("type") in ("success", "replay")
    o = body.get("object") or {}
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


# 每条条件：实测值 / 方法 / 证据（数据来自 cloud/tools/e2e_multiplayer.js、浏览器实测、file:// 实测、e2e_env.js）
AC = {
    "AC-000032": ("朝上连续移动 3 秒，每 200ms 采样一次共 15 次，每次都调用 shared/grid.js 的 canStand 复核；15 次全部落在可行走格内，末点 (500,324)，没有一次进入海面或房屋。",
                  "通过 REST 提交意图，测试进程按 200ms 采样并用同一份可行走格校验。",
                  "evidence/e2e_multiplayer.json 中 AC-000032（末点 500,324，采样 15 次）"),
    "AC-000033": ("提交一次向右意图后不再提交，3.5 秒后连读两次位置：x 均为 683、moving=false，说明意图按 3 秒 TTL 过期并自动停车。",
                  "提交一次意图后静置，间隔采样位置与 moving 标记。",
                  "evidence/e2e_multiplayer.json 中 AC-000033（x 683→683，moving=false）"),
    "AC-000034": ("持续向右意图 1 秒，起点与终点欧氏距离 114.0 px，落在 99–121 区间内（110 ±10%）。",
                  "记录起点、1 秒后终点并计算距离。",
                  "evidence/e2e_multiplayer.json 中 AC-000034（dist=114.0）"),
    "AC-000035": ("无口令 401、错误口令 401、正确口令 200；返回 token 长度 40 字符。",
                  "三次 HTTP 调用并比对状态码与 token 长度。",
                  "evidence/e2e_multiplayer.json 中 AC-000035（401/401/200，len=40）"),
    "AC-000036": ("直接打开 world.db 查询：animals 表中该动物 token_hash 为 64 位十六进制，与明文 token 不同，全表无明文 token。",
                  "用 node:sqlite 打开数据库执行 SELECT。",
                  "evidence/e2e_multiplayer.json 中 AC-000036（hash 前缀 3956a6001a5a）"),
    "AC-000037": ("用 A 的 token 调用 B 的意图接口返回 403，随后读 B 的状态确认其位置与意图未变化。",
                  "跨动物调用一次意图接口并比对 B 的状态。",
                  "evidence/e2e_multiplayer.json 中 AC-000037（status=403）"),
    "AC-000038": ("上传 skill 生成的合法卡片返回 200，状态接口读到 card.width=192、height=192、digest 为 64 位十六进制。",
                  "用 convert_card.py 生成成品后经 CLI 上传，再读 state。",
                  "evidence/e2e_multiplayer.json 中 AC-000038 + CLI 实测（digest df02c0a9fe29…）"),
    "AC-000039": ("上传 3 行高的 PNG 返回 400，errors 含「行数必须是 4，收到 3」。",
                  "构造 192×144 的 PNG 上传并读 errors。",
                  "evidence/e2e_multiplayer.json 中 AC-000039"),
    "AC-000040": ("上传四角 alpha=255 的 PNG 返回 400，errors 指出「四角必须透明：(0,0) 的 alpha=255」。",
                  "构造左上角不透明的 PNG 上传并读 errors。",
                  "evidence/e2e_multiplayer.json 中 AC-000040"),
    "AC-000041": ("浏览器打开 /play?t=<token> 后 3 秒内收到 28 条快照（10Hz），首条 self.id 与注册返回的 A-0001 一致。",
                  "页面内统计 WebSocket 收到的 snapshot 条数与 self.id。",
                  "evidence/e2e_multiplayer.json 中 AC-000041（snaps=28）+ 浏览器实测"),
    "AC-000042": ("浏览器发向右意图 0.6 秒：x 由 614 增至 668（+54px）；再发 null 后 0.2 秒内只再走 7px，随后停住；服务端快照的 facing 变为 right。另在服务端侧测得 683→615（向左）且 facing=left。",
                  "页面调用 __play.sendIntent 并对比快照坐标；服务端侧用 WS 消息复测一次。",
                  "evidence/e2e_multiplayer.json 中 AC-000042（x 683→615 facing=left）+ 浏览器实测 614→668"),
    "AC-000043": ("A 的页面快照 nearby 含 A-0002（TestB），distance=74，且整段响应中搜不到任何 token；world.online=2。",
                  "两只动物同时在附近，读取 A 的 nearby 并检查字段与凭据。",
                  "浏览器实测 nearby=[{id:A-0002,distance:74}]；evidence/e2e_multiplayer.json 中 AC-000043"),
    "AC-000044": ("页面内主动 close WebSocket（__play._drop()）后 connected 立刻变 false，轮询下 ≤7.5 秒窗口内恢复为 true 并继续收到快照。",
                  "调用测试钩子断开连接，轮询 connected 直到恢复。",
                  "浏览器实测（afterDrop.connected=false → reconnect.recovered=true）"),
    "AC-000045": ("以 file:// 打开根目录 index.html：页面 ready，按 D 键 0.4 秒位移 44.6px，按 T 后尺寸由 48 变 24，画面正常。",
                  "file:// 打开后读取 __probe 状态并实际操作。",
                  "浏览器实测（movedDx=44.6，size 48→24）"),
    "AC-000046": ("同一 file:// 页面的 performance 资源列表为 0 条，没有任何 http(s) 请求（只有 file:// 与 data:）。",
                  "读取 performance.getEntriesByType('resource') 并过滤 http(s)。",
                  "浏览器实测（resources=0，httpRequests=[]）"),
    "AC-000047": ("刚注册、未上传卡片的 A-0002 打开 /play 后首屏是拖拽上传区（dropzoneVisible=true），没有渲染游戏画面，也没有建立 WebSocket。",
                  "读取页面 __play.dropzoneVisible 与连接状态。",
                  "浏览器实测（dropzoneVisible=true, connected=false）"),
    "AC-000048": ("在上传页拖入/传入合格卡片后：上传返回 200，1.5 秒内 dropzoneVisible=false、connected=true、收到快照且 self.id=A-0002、card 为 192×192。",
                  "调用页面上传逻辑并观察切换与快照。",
                  "浏览器实测（dropzone=false, connected=true, selfId=A-0002）"),
    "AC-000049": ("先投不合格卡片（192×144）：不切换画面，页面显示「上传被拒绝：card.png 必须是 192×192，实际 192×144」，仍停在上传页。",
                  "构造 3 行高画布上传并读取页面错误文本。",
                  "浏览器实测（errorText 含 192×144，dropzoneVisible 仍为 true）"),
    "AC-000050": ("已有卡片的 A-0001 打开 /play 后首屏直接是游戏：dropzoneVisible=false、connected=true、快照 self.id=A-0001、card 192×192。",
                  "打开已有卡片动物的链接并读取首屏状态。",
                  "浏览器实测（dropzoneVisible=false, connected=true）"),
    "AC-000051": ("未上传卡片时 self.card 为 null；上传后 self.card={width:192,height:192,digest:64 位十六进制}。",
                  "上传前后各读一次状态接口的 self.card。",
                  "evidence/e2e_multiplayer.json 中 AC-000051（null → 192×192）"),
    "AC-000052": ("同一对动物实际距离 203.1：radius=50 时 nearby 不含对方；radius=400 时含对方且 distance=203（四舍五入误差 ≤2）。",
                  "用两个不同半径查询同一对动物并比对距离。",
                  "evidence/e2e_multiplayer.json 中 AC-000052（实际距离 203.1，nearby(400) distance=203）"),
    "AC-000053": ("把状态响应原文序列化后搜索，两方的明文 token 都搜不到；nearby 项只有 id/name/x/y/facing/distance。",
                  "序列化响应并搜索 token 字符串与字段白名单。",
                  "evidence/e2e_multiplayer.json 中 AC-000053"),
    "AC-000054": ("请求 radius=10000 时响应回显 world.radius=400（服务端上限），nearby 按 400 返回。",
                  "带超大半径参数查询并读回显值。",
                  "evidence/e2e_multiplayer.json 中 AC-000054（radius=400）"),
    "AC-000055": ("一条命令启动后 /healthz 返回 200 且含 online 与 version（0.2.0）；根路径单机首页返回 200。",
                  "启动服务后分别请求 /healthz 与 /。",
                  "evidence/e2e_multiplayer.json 中 AC-000055"),
    "AC-000056": ("用 PORT=8123、DATA_DIR=<临时目录>、REGISTER_CODE=custom-code-xyz 启动：监听 8123；默认口令 dev-code 返回 401、自定义口令 200；world.db 与 cards/ 都出现在该临时目录；默认 cloud/data 的 world.db mtime 未变（本次没写进去）。",
                  "换三组环境变量启动一轮并用 e2e_env.js 断言。",
                  "evidence/e2e_env.json（listenOnCustomPort/customCodeWorks/dbInDataDir/defaultDataUntouched 全 true）"),
    "AC-000057": ("WS 未连时 /healthz 的 online=0；浏览器连上后 online=2（两只动物各一个连接）。",
                  "连接前后各请求一次 /healthz 比对 online。",
                  "evidence/e2e_multiplayer.json 中 AC-000057（online=2）"),
}


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    o = doc["object"]
    print("start doc_rev:", rev, "active:", o["active_baseline"])
    reqs = {r["id"]: r["revisions"][-1] for r in o["requirements"] if r["id"] in NEW_IDS}

    implemented = {}
    # ---- 开发：start + complete ----
    for rid in NEW_IDS:
        cur = reqs[rid]
        for args, act in ((["dev", "start"], "start"), (["dev", "complete"], "complete")):
            code, body = call(args, {
                "operation_id": f"mp-{act}-{rid}", "agent": "octie-agent",
                "reason": ("开始多人世界重构的实现轮次" if act == "start"
                           else "代码已实现并通过服务端/浏览器实测"),
                "expected_revision": rev,
                "data": {"baseline_id": BASELINE, "id": rid, "revision": cur["revision"],
                         "digest": cur["digest"]},
            })
            if not ok(f"{act} {rid}", code, body):
                return 1
            rev = body["document_revision"]
            if act == "complete":
                implemented[rid] = body["object"]["implemented_event_id"]
    print("implemented events:", implemented)

    # ---- 验收：26 条 ----
    for rid in NEW_IDS:
        cur = reqs[rid]
        for a in cur["acceptance"]:
            cid = a["id"]
            actual, method, evidence = AC[cid]
            code, body = call(["acceptance", "record"], {
                "operation_id": f"mp-acc-{cid}", "agent": "octie-agent",
                "reason": "按实测登记该条件结果",
                "expected_revision": rev,
                "data": {
                    "baseline_id": BASELINE, "requirement_id": rid,
                    "revision": cur["revision"], "cycle": 1, "condition_id": cid,
                    "delivery_id": DELIVERY,
                    "implemented_event_id": implemented[rid],
                    "evidence": evidence, "actual": actual, "method": method, "result": "通过",
                },
            })
            if not ok(f"acc {cid}", code, body):
                return 1
            rev = body["document_revision"]
            EXE[cid] = body["object"]["id"]

    # ---- 发布 ----
    code, body = call(["release", "add"], {
        "operation_id": "mp-release-v7", "agent": "octie-agent",
        "reason": "在基线 BASE-000007 下发布 crab-coast-v7（云端多人版 v1）",
        "expected_revision": rev,
        "data": {
            "baseline_id": BASELINE, "delivery_id": DELIVERY,
            "members": [{"id": rid, "revision": reqs[rid]["revision"], "cycle": 1} for rid in NEW_IDS],
        },
    })
    if not ok("release add", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    # ---- 关闭变更 ----
    chg = show({"type": "change", "id": "CHG-000006"})["object"]
    actions = chg["actions"]
    obligations = chg["evaluation"]["obligations"]

    code, body = call(["change", "close"], {
        "operation_id": "mp-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、已随发布采用全部重验执行，逐动作逐义务关闭",
        "expected_revision": rev,
        "data": {
            "id": "CHG-000006", "revision": chg["revision"], "digest": chg["digest"],
            "action_closures": [
                {"action": a, "basis": {"type": "发布", "release_id": rel}} for a in actions
            ],
            "obligation_closures": [
                {"obligation": {k: ob[k] for k in ("change_id", "change_revision", "requirement_id",
                                                   "revision", "condition_id")},
                 "basis": {"type": "执行", "executions": [{"execution_id": EXE[ob["condition_id"]],
                                                           "delivery_id": DELIVERY}]}}
                for ob in obligations
            ],
        },
    })
    if not ok("change close", code, body):
        return 1
    rev = body["document_revision"]

    print("done. doc_rev:", rev, "release:", rel)
    return 0


EXE = {}


if __name__ == "__main__":
    sys.exit(main())
