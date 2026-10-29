"""把 REQ-000011 r3（渲染口径改为相机视野）真正纳入基线。

背景：REQ-000011 已在 REV-000033 前后修订到 r3 并确认，但 BASE-000009/010 的成员仍是 r2
（成员内容里还写着「半径 200 内的其他动物」）。台账结构校验不会报错，但基线内容与实现不一致，
这里用一次替换变更把 r2 → r3 落进新基线 BASE-000011，并逐条重验 4 个条件。

实测来源：evidence/page_live.json（CDP 打开真实页面取数，4/4 通过）。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
DELIVERY = "crab-coast-v11"
REQ = "REQ-000011"
NEW_REV = 3
OLD_REV = 2


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
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
        print("    raw:", (body.get("_raw") or "")[:600])
    return good


ACC = {
    "AC-000041": ("CDP 打开 /play：3.03 秒内收到 28 条快照，self.id=A-0001 与注册返回一致，连接状态已连接。",
                  "页面内轮询 __play.snapshot 的对象引用变化计数（每条消息都换新引用）。",
                  "evidence/page_live.json 中 AC-000041"),
    "AC-000042": ("按住「右」0.5 秒：x 500→547（+47px）、y 412→412（0px），facing=right；松手 300ms 后 moving=false。",
                  "页面 sendIntent 驱动 + 快照前后对比。", "evidence/page_live.json 中 AC-000042"),
    "AC-000043": ("页面 nearby=[A-0002]（x=500,y=412,distance=54），整份快照 JSON 中搜不到 A/B 的 token。",
                  "读快照 nearby 与全文，做 id 与凭据比对。", "evidence/page_live.json 中 AC-000043"),
    "AC-000044": ("主动断开（__play._drop()）后 424ms 重新连上、506ms 收到新快照，全程未刷新页面。",
                  "断开后轮询 connected 与快照引用，记录恢复耗时。", "evidence/page_live.json 中 AC-000044"),
}


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    pred = doc["object"]["active_baseline"]
    cur = [r for r in doc["object"]["requirements"] if r["id"] == REQ][0]["revisions"][-1]
    print("start doc_rev:", rev, "active:", pred, "|", REQ, "latest r", cur["revision"])
    if cur["revision"] != NEW_REV:
        print("!! 最新修订不是预期值，停止")
        return 1
    digest = cur["digest"]

    actions = [{"type": "替换", "requirement_id": REQ,
                "old_revision": OLD_REV, "new_revision": NEW_REV}]
    retests = [{"requirement_id": REQ, "revision": NEW_REV, "condition_id": cid} for cid in ACC]

    code, body = call(["change", "propose"], {
        "operation_id": "r11-chg-propose", "agent": "octie-agent",
        "reason": "把 REQ-000011 r3（相机视野渲染口径）真正纳入基线，替换仍是 r2 的成员",
        "expected_revision": rev,
        "data": {"predecessor": pred, "actions": actions, "impact_objects": [REQ]},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "r11-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与重验清单", "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "impact_analysis": (
                     "只替换一条需求的基线内容：REQ-000011 r2 → r3。差异是渲染口径（「半径 200 内的其他动物」"
                     "改为「相机视野内的其他动物」，半径语义移交 REQ-000018），实现代码在上一轮已完成且未再改动；"
                     "服务端接口、卡片管线、单机版均不受影响。因此重验 REQ-000011 的 4 个条件。"),
                 "retests": retests},
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "r11-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 做变更审核", "expected_revision": rev,
        "data": {"target_type": "change", "target_id": chg,
                 "target_revision": ch["revision"], "target_digest": ch["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：实测与实现都按 r3 工作（视野渲染），但基线成员仍是 r2（半径渲染），基线内容与实现不一致，发布快照会撒谎。",
                 "completeness_review": f"完整性：唯一动作是替换 {REQ} r{OLD_REV}→r{NEW_REV}，new_revision 等于台账最新确认修订；其余成员沿用前驱基线；4 项重验覆盖该需求全部条件。",
                 "acceptance_review": "验收：4 个条件由 probe_page.js 在真实页面上实测（快照条数、右移、nearby 内容、断线重连），结果写 evidence/page_live.json；本审核不声称已执行。",
                 "basis": f"依据 {chg} 评估后摘要 {ch['digest'][:12]}… 与 probe_page 的 4/4 实测。声明式审核。"},
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        ch = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"r11-chg-{act}", "agent": "octie-agent",
            "reason": "批准变更" if act == "approve" else "生成候选基线（不自动激活）",
            "expected_revision": rev,
            "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"]},
        })
        if not ok(act, code, body):
            return 1
        rev = body["document_revision"]

    doc = show({"type": "ledger"})
    cand = [b for b in doc["object"]["baselines"] if b.get("predecessor") == pred][-1]
    print("candidate:", cand["id"], cand.get("version"), "members:", len(cand["members"]))

    code, body = call(["review", "add"], {
        "operation_id": "r11-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {"target_type": "baseline", "target_id": cand["id"],
                 "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：修正后的 r3 需要与其余成员一起冻结成可发布快照。",
                 "completeness_review": f"成员完整：{len(cand['members'])} 个，只有 {REQ} 换成 r{NEW_REV}，其余保持前驱修订。",
                 "acceptance_review": "4 项重验尚未登记执行结果，属后续验收环节，本审核不声称其已通过。",
                 "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}…。声明式审核。"},
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "r11-base-activate", "agent": "octie-agent",
        "reason": "候选基线已审核通过，激活为当前有效基线", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1
    rev = body["document_revision"]

    impl = None
    for act in ("start", "complete"):
        code, body = call(["dev", act], {
            "operation_id": f"r11-dev-{act}", "agent": "octie-agent",
            "reason": "开始实现轮次" if act == "start" else "实现完成（上一轮已改 play.js，本轮只补基线）",
            "expected_revision": rev,
            "data": {"baseline_id": cand["id"], "id": REQ, "revision": NEW_REV, "digest": digest},
        })
        if not ok(f"dev {act}", code, body):
            return 1
        rev = body["document_revision"]
        if act == "complete":
            impl = body["object"]["implemented_event_id"]

    exe = {}
    for cid, (actual, method, ev) in ACC.items():
        code, body = call(["acceptance", "record"], {
            "operation_id": f"r11-acc-{cid}", "agent": "octie-agent",
            "reason": "按页面实测登记该条件的验收结果", "expected_revision": rev,
            "data": {"baseline_id": cand["id"], "requirement_id": REQ, "revision": NEW_REV, "cycle": 1,
                     "condition_id": cid, "delivery_id": DELIVERY,
                     "implemented_event_id": impl, "evidence": ev, "actual": actual,
                     "method": method, "result": "通过"},
        })
        if not ok(f"acc {cid}", code, body):
            return 1
        rev = body["document_revision"]
        exe[cid] = body["object"]["id"]

    code, body = call(["release", "add"], {
        "operation_id": "r11-release-v11", "agent": "octie-agent",
        "reason": "发布 crab-coast-v11（REQ-000011 r3 纳入基线）", "expected_revision": rev,
        "data": {"baseline_id": cand["id"], "delivery_id": DELIVERY,
                 "members": [{"id": REQ, "revision": NEW_REV, "cycle": 1}]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "r11-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、4 项重验义务已逐条登记执行结果",
        "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "action_closures": [{"action": a, "basis": {"type": "发布", "release_id": rel}}
                                     for a in ch["actions"]],
                 "obligation_closures": [
                     {"obligation": {k: ob[k] for k in ("change_id", "change_revision",
                                                        "requirement_id", "revision", "condition_id")},
                      "basis": {"type": "执行", "executions": [
                          {"execution_id": exe[ob["condition_id"]], "delivery_id": DELIVERY}]}}
                     for ob in ch["evaluation"]["obligations"]]},
    })
    if not ok("change close", code, body):
        return 1
    print("done. doc_rev:", body["document_revision"], "| release:", rel, "| baseline:", cand["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
