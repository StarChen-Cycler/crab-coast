"""关闭变更 CHG-000001：逐动作 + 逐重验义务关闭。"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
DELIVERY = "crab-coast-v2"
RELEASE = "REL-000002"


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
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:2000])
        raise SystemExit(1)
    print(f"   ✓ {what}")
    return obj


def main():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    r = o["current_document_revision"]
    obj = o["object"]

    # 评估后的实时摘要要从 type=change 取，不能用户 revisions 里的旧摘要
    rc, oc = call(["show"], {"type": "change", "id": "CHG-000001"})
    must(rc, oc, "读变更")
    cobj = oc["object"]
    cid, cnum, cdig = cobj["id"], cobj["revision"], cobj["digest"]
    actions = cobj["actions"]
    print(f"变更 {cid} r{cnum} actions={len(actions)}")

    # 本次交付的执行记录 → condition_id -> execution_id
    ex = {}
    for e in obj["executions"]:
        if e.get("delivery_id") == DELIVERY and e.get("result") == "通过":
            ex.setdefault(e["condition_id"], e["id"])
    print("可用执行记录:", len(ex))

    ev = cobj.get("evaluation") or {}
    retests = ev.get("retests") or []
    print("重验义务:", len(retests))

    obligations = []
    for rt in retests:
        cid_cond = rt["condition_id"]
        eid = ex.get(cid_cond)
        if not eid:
            print(f"!! 缺少 {cid_cond} 的执行记录")
            raise SystemExit(1)
        obligations.append({
            "obligation": {
                "change_id": cid, "change_revision": cnum,
                "requirement_id": rt["requirement_id"], "revision": rt["revision"],
                "condition_id": cid_cond,
            },
            "basis": {"type": "执行", "executions": [{"execution_id": eid, "delivery_id": DELIVERY}]},
        })

    action_closures = [
        {"action": {"type": a["type"], "requirement_id": a["requirement_id"],
                    "old_revision": a["old_revision"], "new_revision": a["new_revision"]},
         "basis": {"type": "发布", "release_id": RELEASE}}
        for a in actions
    ]

    rc, o = call(["change", "close"], {
        "operation_id": "chg-close-1", "agent": AGENT,
        "reason": "两个动作的成员均已随 crab-coast-v2 发布；7 条重验义务均有本交付的执行记录",
        "expected_revision": r,
        "data": {
            "id": cid, "revision": cnum, "digest": cdig,
            "action_closures": action_closures,
            "obligation_closures": obligations,
        },
    })
    must(rc, o, "change close")

    rc, o = call(["check"])
    must(rc, o, "结构自检")
    print("\n变更已关闭，台账自检通过。")


if __name__ == "__main__":
    main()
