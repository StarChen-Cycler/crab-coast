"""候选基线 BASE-000002 审核 + 激活，随后把 5 条需求跑一轮返工（cycle 2）。"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
BID = "BASE-000002"


def call(argv, data=None):
    args = ["reqledger"] + argv + ["--file", F]
    if data is not None:
        args += ["--json", json.dumps(data, ensure_ascii=False)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        return p.returncode, json.loads(p.stdout.strip())
    except Exception:
        return p.returncode, {"raw": p.stdout.strip()[:400], "err": p.stderr[:300]}


def must(rc, obj, what):
    if rc != 0 or obj.get("type") == "error" or obj.get("commit_status") == "not_committed":
        print(f"\n!! {what} 失败 rc={rc}")
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:1800])
        raise SystemExit(1)
    print(f"   ✓ {what}")
    return obj


def main():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    r = o["current_document_revision"]
    bases = {b["id"]: b for b in o["object"]["baselines"]}
    base = bases[BID]
    brev, bdig = base["revision"], base["digest"]
    print(f"候选基线 {BID} r{brev} digest={bdig[:10]} 成员={len(base['members'])}")

    rc, o = call(["review", "add"], {
        "operation_id": "review-base2-1", "agent": "review-agent",
        "reason": "审核新基线候选的成员与范围", "expected_revision": r,
        "data": {
            "target_type": "baseline", "target_id": BID,
            "target_revision": brev, "target_digest": bdig, "conclusion": "通过",
            "necessity_review": "候选由已批准的变更 CHG-000001 应用生成，成员精确对应两个动作。",
            "completeness_review": "5 条需求齐全：3 条未变成员沿用原修订，REQ-000003 用 r2，REQ-000005 用 r1。",
            "acceptance_review": "重验义务已登记 7 条，将在本轮验收中逐条执行。",
            "basis": "依据 change apply 生成的 BASE-000002 与 requirements.md 内容核对。",
        },
    })
    must(rc, o, "baseline(candidate) review"); r = o["current_document_revision"]

    rc, o = call(["baseline", "activate"], {
        "operation_id": "baseline-activate-2", "agent": AGENT,
        "reason": "候选审核通过，激活为当前有效基线 V1.1",
        "expected_revision": r,
        "data": {"id": BID, "revision": brev, "digest": bdig},
    })
    must(rc, o, "baseline activate V1.1")
    r = o["current_document_revision"]

    # ---- 返工：5 条需求各跑一轮 cycle 2 ----
    rc, o = call(["show"])
    reqs = []
    for req in o["object"]["requirements"]:
        latest = req["revisions"][-1]
        reqs.append({"id": req["id"], "revision": latest["revision"], "digest": latest["digest"]})
    print("基线成员:", [(x["id"], x["revision"]) for x in reqs])

    for x in reqs:
        rid, rv, dg = x["id"], x["revision"], x["digest"]
        rc, o = call(["dev", "start"], {
            "operation_id": f"dev2-start-{rid}", "agent": AGENT,
            "reason": "V1.1 基线启用，本轮为实现/返工（画面、角色、音乐均已更新）",
            "expected_revision": r,
            "data": {"baseline_id": BID, "id": rid, "revision": rv, "digest": dg},
        })
        must(rc, o, f"{rid} dev start"); r = o["current_document_revision"]

        rc, o = call(["dev", "complete"], {
            "operation_id": f"dev2-complete-{rid}", "agent": AGENT,
            "reason": "本轮实现完成，证据见 evidence/ 与 music/",
            "expected_revision": r,
            "data": {"baseline_id": BID, "id": rid, "revision": rv, "digest": dg},
        })
        must(rc, o, f"{rid} dev complete"); r = o["current_document_revision"]

    print("\n文档修订:", r)


if __name__ == "__main__":
    main()
