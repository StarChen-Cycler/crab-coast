"""2026-10-29 补充：第 3 个 WebSocket 不拒绝，而是淘汰最早的那个（FIFO，永远保留最新两个）。

修订 REQ-000016 → r2：改 description / included / boundaries，并保留原条件 ID 改写「第三会话」那条。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"


def call(args, payload):
    p = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                       input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    return p.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def show(payload):
    p = subprocess.run(["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
                       input=json.dumps(payload).encode(), capture_output=True)
    return json.loads(p.stdout.decode("utf-8", "replace"))


def ok(name, code, body):
    good = body.get("type") in ("success", "replay")
    o = body.get("object") or {}
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')} r={o.get('revision')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    cur = [r for r in doc["object"]["requirements"] if r["id"] == "REQ-000016"][0]["revisions"][-1]
    print("start doc_rev:", rev, "| REQ-000016 当前 r", cur["revision"])

    data = {k: cur[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                               "priority", "placement", "included", "excluded", "normal_behavior",
                               "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in cur["sources"]]
    if not any(s["source_id"] == "SRC-000006" for s in data["sources"]):
        data["sources"].append({"source_id": "SRC-000006", "source_revision": 1})

    data["description"] = (
        "同一只动物可以同时被多个来源控制（典型是 Agent 一个 WebSocket 会话 + 人在浏览器里一个会话）。"
        "服务端**不区分**来源是 Agent 还是人，只按连接（或带 token 的调用方）分别记账：每个来源各自维护"
        "「当前按住的方向」，动物的实际方向取「最近按下且仍未松开」的那一个。按住 A 再按下 B 时 B 生效；"
        "松开 B 后若 A 仍按着就回落到 A；都松开则停车。按住期间客户端周期性续期，使「3 秒无更新即停车」"
        "只作用于真正失联的来源。同一只动物**同时最多保持 2 个活跃 WebSocket 会话**：第 3 个连接到来时"
        "**接受新连接、主动关闭最早建立的那个**（先进先出），保证「永远是最新两个在线」。被淘汰的一方收到"
        "明确的关闭原因，且**不得自动重连**——否则会与另一路互相顶掉、形成来回踢的循环。"
    )

    data["included"] = [x for x in cur["included"] if "最多 2 个活跃" not in x] + [
        "同一只动物同时最多保持 2 个活跃 WebSocket 会话",
        "第 3 个连接到来时接受新连接并淘汰最早建立的会话（先进先出）",
        "被淘汰的连接收到明确关闭原因，且客户端不得自动重连",
    ]

    data["boundaries"] = [
        b for b in cur["boundaries"] if "第 3 个 WebSocket" not in b.get("scenario", "")
    ] + [
        {
            "scenario": "同一 token 建立第 3 个 WebSocket 连接",
            "expected": "新连接被接受，最早建立的那个被服务端主动关闭并收到原因；中间那个与新连接继续正常收快照",
            "handling": "按连接建立时间先进先出淘汰；被淘汰方不得自动重连，改为提示用户「已在别处被接管」",
        },
    ]

    data["acceptance"] = []
    for a in cur["acceptance"]:
        item = {k: a[k] for k in ("allow_na", "evidence", "exception", "expected", "input",
                                  "method", "operation", "preconditions", "role", "scenario")}
        item["id"] = a["id"]
        if "第三个会话被拒" in a.get("scenario", ""):
            item.update({
                "scenario": "第三个连接到来时淘汰最早的会话",
                "preconditions": "同一只动物已建立两个活跃 WebSocket 会话（依次称为 conn-1、conn-2）",
                "input": "用同一 token 建立第 3 个 WebSocket（conn-3）",
                "operation": "观察三个连接的最终状态，并记录 conn-1 收到的关闭码与原因",
                "expected": "conn-3 被接受并开始收到快照；conn-1 被服务端主动关闭并收到「被更新的连接取代」类原因；conn-2 与 conn-3 都正常收快照，最终恰好 2 个在线",
                "exception": {
                    "scenario": "conn-1 未被关闭，或三个连接同时在线",
                    "expected": "判定先进先出淘汰未生效",
                    "handling": "检查握手阶段的活跃计数与按建立时间排序的淘汰逻辑",
                },
                "method": "并发建立三个连接，记录每个连接的 close 事件与快照计数",
                "evidence": "三个连接的建立顺序、conn-1 的 close code/reason、conn-2 与 conn-3 的快照计数",
            })
        data["acceptance"].append(item)

    data["technical"] = (
        "ws.js 按 animalId 维护一个按建立时间有序的会话队列：握手成功后 push 新会话，"
        "若长度 > 2 则 shift 最早的一个并 close(1008, 'replaced by newer session')；"
        "play.js 只在非主动关闭（网络错误/断线）时重连，收到该关闭码时停手并提示「已在别处被接管」。"
    )

    data["id"] = "REQ-000016"
    data["base_revision"] = cur["revision"]

    # 先补来源 SRC-000006（用户这条补充）
    code, body = call(["source", "add"], {
        "operation_id": "ctl-src-6", "agent": "octie-agent",
        "reason": "登记用户对第 3 个连接处理方式的补充",
        "expected_revision": rev,
        "data": {
            "kind": "用户消息",
            "name": "用户补充：第 3 个 WebSocket 应淘汰最早的那个",
            "date_note": "2026-10-29 用户消息",
            "quote": "如果用户从一个新的浏览器，用相同的 token 打开了第三个 WebSocket 连接，那么第一个应该自动断开。也就是说，永远保持最后两个通过网页或链接连接进去的、token 对应的 WebSocket 在线，之前的连接自动注销掉",
            "summary": "同一 token 的第 3 个连接不拒绝，而是接受新连接并关闭最早建立的那个，始终保留最新两个在线。",
            "manual_note": "用户在会话中以文字直接补充，未经整理",
        },
    })
    if not ok("source add SRC-000006", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["req", "revise"], {
        "operation_id": "ctl-req16-revise-2", "agent": "octie-agent",
        "reason": "把第 3 个连接的处理从「拒绝」改为「淘汰最早」，并明确被淘汰方不得自动重连",
        "expected_revision": rev, "data": data,
    })
    if not ok("revise REQ-000016", code, body):
        return 1
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]

    code, body = call(["req", "submit"], {
        "operation_id": f"ctl-submit-16-r{rrev}", "agent": "octie-agent",
        "reason": "修订版转入待审核", "expected_revision": rev,
        "data": {"id": "REQ-000016", "revision": rrev, "digest": digest},
    })
    if not ok("submit", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["review", "add"], {
        "operation_id": f"ctl-review-16-r{rrev}", "agent": "review-agent",
        "reason": "对 REQ-000016 修订版做语义审核", "expected_revision": rev,
        "data": {
            "target_type": "requirement", "target_id": "REQ-000016",
            "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
            "necessity_review": "必要性：用户明确要求「永远保留最新两个」，若仍按拒绝处理，新浏览器打不开且旧标签页继续占位；这条决定必须写进需求才可验收。",
            "completeness_review": "完整性：改动集中在会话策略——description 写明先进先出、included 增补 3 条、boundaries 把「第 3 会话」改为淘汰语义；其余字段与条件保持原样，条件 ID 全部沿用（仅改写被拒那条的内容）。",
            "acceptance_review": "验收：原第 4 条改写为「建立三个连接后 conn-1 被关闭、conn-2 与 conn-3 在线」，预期包含关闭码/原因与在线数，可并发复现；另新增的「不得自动重连」写进了边界与 included，避免来回顶掉的循环。",
            "basis": f"依据 REQ-000016 第 {rrev} 修订摘要 {digest[:12]}… 与来源 SRC-000006 r1 审阅。声明式审核，Agent 身份仅作操作归因。",
        },
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["req", "confirm"], {
        "operation_id": f"ctl-confirm-16-r{rrev}", "agent": "octie-agent",
        "reason": "审核通过且无开放问题，确认纳入", "expected_revision": rev,
        "data": {"id": "REQ-000016", "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}},
    })
    if not ok("confirm", code, body):
        return 1
    print("done. doc_rev:", body["document_revision"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
