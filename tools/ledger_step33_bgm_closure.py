"""背景音乐的台账闭环（CHG-000012）：dev → 8 项验收 → 发布 crab-coast-v13 → 关闭变更。

验收结果直接从 evidence/bgm.json 读取实测值，不手抄。
AC-000045 / AC-000046 属于 REQ-000012（本轮只是回归，没有改它），
所以它们的 implemented_event_id 取 REQ-000012 自己的实现事件，而不是本轮的。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
DELIVERY = "crab-coast-v13"
IDS = "tools/_bgm_ids.json"
EVIDENCE = "evidence/bgm.json"
REGRESSED = "REQ-000012"          # 被回归验证、但本轮未改动的需求
REGRESSED_CONDITIONS = ("AC-000045", "AC-000046")


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
        print("    raw:", (body.get("_raw") or "")[:400])
    return good


def main():
    with open(IDS, encoding="utf-8") as f:
        ids = json.load(f)
    chg, base = ids["change"], ids["baseline"]
    rid, rrev = next(iter(ids["requirements"].items()))

    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    o = doc["object"]
    cur = {r["id"]: r["revisions"][-1] for r in o["requirements"]}
    prod = [d for d in o.get("development") or [] if d["requirement_id"] == REGRESSED and d.get("implemented_event_id")]
    if not prod:
        print("!! 找不到 REQ-000012 的实现事件")
        return 1
    impl_regressed = prod[-1]["implemented_event_id"]
    print("start doc_rev:", rev, "| active:", o["active_baseline"], "| change:", chg,
          "| 回归需求实现事件:", impl_regressed)

    with open(EVIDENCE, encoding="utf-8") as f:
        ev = json.load(f)
    per = {}
    for r in ev.get("results", []):
        per.setdefault(r["condition"], []).append(r)
    need = list(ids["retests"])
    missing = [x["condition_id"] for x in need if x["condition_id"] not in per]
    failed = [c for c in per if any(not r["pass"] for r in per[c])]
    if missing or failed:
        print("!! 证据缺失或未通过：missing=", missing, "failed=", failed)
        return 1

    # dev：只针对本轮改动的需求
    impl = {}
    digest = cur[rid]["digest"]
    for act in ("start", "complete"):
        code, body = call(["dev", act], {
            "operation_id": f"bgm-dev-{act}", "agent": "octie-agent",
            "reason": "开始实现轮次" if act == "start" else "实现完成，e2e_bgm 10/10、range 单测 9/9、四套回归全 PASS",
            "expected_revision": rev,
            "data": {"baseline_id": base, "id": rid, "revision": rrev, "digest": digest},
        })
        if not ok(f"dev {act}", code, body):
            return 1
        rev = body["document_revision"]
        if act == "complete":
            impl[rid] = body["object"]["implemented_event_id"]

    exe = {}
    for item in need:
        cid = item["condition_id"]
        owner = REGRESSED if cid in REGRESSED_CONDITIONS else rid
        owner_rev = cur[owner]["revision"]
        impl_event = impl_regressed if owner == REGRESSED else impl[rid]
        rows = per[cid]
        actual = "；".join(f"{r['name']} → {json.dumps(r.get('detail'), ensure_ascii=False)}" for r in rows)
        code, body = call(["acceptance", "record"], {
            "operation_id": f"bgm-acc-{cid}", "agent": "octie-agent",
            "reason": "按实测证据登记该条件的验收结果", "expected_revision": rev,
            "data": {"baseline_id": base, "requirement_id": owner, "revision": owner_rev, "cycle": 1,
                     "condition_id": cid, "delivery_id": DELIVERY,
                     "implemented_event_id": impl_event,
                     "evidence": EVIDENCE, "actual": actual[:4000],
                     "method": "HTTP 头断言 + CDP 受信任手势驱动的页面状态采样",
                     "result": "通过"},
        })
        if not ok(f"acc {cid}", code, body):
            return 1
        rev = body["document_revision"]
        exe[cid] = body["object"]["id"]

    code, body = call(["release", "add"], {
        "operation_id": "bgm-release-v13", "agent": "octie-agent",
        "reason": "发布 crab-coast-v13（多人在线版背景音乐 + 静态资源 Range）", "expected_revision": rev,
        "data": {"baseline_id": base, "delivery_id": DELIVERY,
                 "members": [{"id": rid, "revision": rrev, "cycle": 1},
                             {"id": REGRESSED, "revision": cur[REGRESSED]["revision"], "cycle": 1}]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "bgm-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、8 项重验义务已逐条登记执行结果",
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
    print("done. doc_rev:", body["document_revision"], "| release:", rel, "| baseline:", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
