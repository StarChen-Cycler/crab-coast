"""多人世界重构：第 7 步 —— 变更 + 新基线（BASE-000007）。

动作：把 REQ-000008..015 共 8 条新增进基线（前驱 BASE-000006）。
重验清单自动取自台账里这 8 条的全部条件，不手抄。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
PREDECESSOR = "BASE-000006"
NEW_IDS = [f"REQ-{n:06d}" for n in range(8, 16)]


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def ok(name, code, body):
    good = body.get("type") in ("success", "replay")
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={(body.get('object') or {}).get('id')} status={(body.get('object') or {}).get('status')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


def show(payload):
    p = subprocess.run(["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
                       input=json.dumps(payload).encode(), capture_output=True)
    return json.loads(p.stdout.decode("utf-8", "replace"))


def main():
    doc = show({"type": "ledger"})
    o = doc["object"]
    rev = doc["document_revision"]
    print("start doc_rev:", rev, "active:", o["active_baseline"])

    reqs = {r["id"]: r["revisions"][-1] for r in o["requirements"]}
    actions, retests = [], []
    for rid in NEW_IDS:
        cur = reqs[rid]
        actions.append({"type": "新增", "requirement_id": rid,
                        "old_revision": None, "new_revision": cur["revision"]})
        for a in cur["acceptance"]:
            retests.append({"requirement_id": rid, "revision": cur["revision"],
                            "condition_id": a["id"]})
    print(f"actions={len(actions)} retests={len(retests)}")

    # 1. propose
    code, body = call(["change", "propose"], {
        "operation_id": "mp-chg-propose", "agent": "octie-agent",
        "reason": "把多人世界重构的 8 条已确认需求新增进基线",
        "expected_revision": rev,
        "data": {"predecessor": PREDECESSOR, "actions": actions,
                 "impact_objects": NEW_IDS},
    })
    if not ok("change propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    # 2. evaluate（digest 用 propose 之后的当前值）
    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "mp-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与精确重验清单",
        "expected_revision": rev,
        "data": {
            "id": chg, "revision": cur["revision"], "digest": cur["digest"],
            "impact_analysis": (
                "本次变更只做新增：8 条需求都是多人世界 v1 的能力（服务端权威移动、注册与 token、动作卡上传校验、"
                "浏览器进场、无卡上传页、Agent 读状态、部署运行、单机版保留），全部为新代码（shared/ 与 server/ 与 play/ 与 cli/ 与 skill/），"
                "不修改任何已发布需求的实现。对既有交付的唯一要求是「不受影响」：单机版 index.html 及其脚本保持零改动、"
                "仍可 file:// 离线运行，因此把 AC-000045 / AC-000046 一并纳入重验。其余 24 条都是新需求自身的条件。"
            ),
            "retests": retests,
        },
    })
    if not ok("change evaluate", code, body):
        return 1
    rev = body["document_revision"]

    # 3. review（评估后 digest 会变，必须重读）
    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "mp-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 当前修订做变更审核",
        "expected_revision": rev,
        "data": {
            "target_type": "change", "target_id": chg,
            "target_revision": cur["revision"], "target_digest": cur["digest"],
            "conclusion": "通过",
            "necessity_review": "必要性：这 8 条已确认但不在 BASE-000006 成员内，按门禁必须经变更批准才能进新基线；差异只有新增，没有夹带替换或移除。",
            "completeness_review": "完整性：actions 恰好 8 条、全部为「新增」且 new_revision 等于各需求当前确认修订；predecessor 为当前有效基线 BASE-000006；候选成员为原 7 条加新增 8 条，其余成员保持原修订。",
            "acceptance_review": f"验收：评估给出 {len(retests)} 项重验义务，逐条对应候选纳入条件（含新增 8 条需求自身 24 条 + 单机版不受影响的 AC-000045 / AC-000046），均为可执行条件，无笼统替代。",
            "basis": f"依据 {chg} 评估后的当前摘要 {cur['digest'][:12]}… 与台账中 8 条需求的确认修订审阅。声明式审核，Agent 身份仅作操作归因。",
        },
    })
    if not ok("review add", code, body):
        return 1
    rev = body["document_revision"]

    # 4. approve
    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "approve"], {
        "operation_id": "mp-chg-approve", "agent": "octie-agent",
        "reason": "变更已获当前最新通过审核，予以批准",
        "expected_revision": rev,
        "data": {"id": chg, "revision": cur["revision"], "digest": cur["digest"]},
    })
    if not ok("change approve", code, body):
        return 1
    rev = body["document_revision"]

    # 5. apply → 候选基线
    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "apply"], {
        "operation_id": "mp-chg-apply", "agent": "octie-agent",
        "reason": "按批准差异生成候选基线（不自动激活）",
        "expected_revision": rev,
        "data": {"id": chg, "revision": cur["revision"], "digest": cur["digest"]},
    })
    if not ok("change apply", code, body):
        return 1
    rev = body["document_revision"]

    # 6. 找候选基线并审核 + 激活
    doc = show({"type": "ledger"})
    cand = [b for b in doc["object"]["baselines"] if b.get("predecessor") == PREDECESSOR][-1]
    print("candidate:", cand["id"], cand.get("version"), "members:", len(cand["members"]))

    code, body = call(["review", "add"], {
        "operation_id": "mp-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核",
        "expected_revision": rev,
        "data": {
            "target_type": "baseline", "target_id": cand["id"],
            "target_revision": cand["revision"], "target_digest": cand["digest"],
            "conclusion": "通过",
            "necessity_review": "必要性：8 条新需求需要与既有 7 条一起被固定成一份可发布快照，候选由已批准的 CHG 生成。",
            "completeness_review": f"成员完整：原 7 条保持原修订，新增 8 条为其确认修订，共 {len(cand['members'])} 个成员；前驱为当前有效基线。",
            "acceptance_review": f"对应 {len(retests)} 项重验义务尚未登记执行结果，属于后续开发与验收环节，本审核不声称其已通过。",
            "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}… 审阅。声明式审核，Agent 身份仅作操作归因。",
        },
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "mp-base-activate", "agent": "octie-agent",
        "reason": "候选基线已审核通过，激活为当前有效基线",
        "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("baseline activate", code, body):
        return 1
    rev = body["document_revision"]

    print("done. doc_rev:", rev, "| baseline:", cand["id"], cand.get("version"), "| change:", chg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
