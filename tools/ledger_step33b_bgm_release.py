"""CHG-000012 收尾：发布 + 关闭变更（执行登记已由 step33 完成）。

上一版把「被回归、本轮未改」的 REQ-000012 也塞进 release members，门禁按旧基线的完整键
去找「REQ-000012 r2 在 BASE-000007 下、交付 v13 的执行」→ 必然找不到（那是历史交付）。
release 的 members 只应列出本交付真正交付的需求，所以这里只放 REQ-000022。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
DELIVERY = "crab-coast-v13"
IDS = "tools/_bgm_ids.json"


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
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:1200])
    return good


def main():
    with open(IDS, encoding="utf-8") as f:
        ids = json.load(f)
    chg, base = ids["change"], ids["baseline"]
    rid, rrev = next(iter(ids["requirements"].items()))

    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    o = doc["object"]
    print("start doc_rev:", rev, "| active:", o["active_baseline"], "| change:", chg)

    # 本交付已登记的执行（按条件索引）
    exe = {}
    for e in o.get("executions") or []:
        if e.get("delivery_id") == DELIVERY and e.get("baseline_id") == base:
            exe[e["condition_id"]] = e["id"]
    print("本交付执行:", json.dumps(exe, ensure_ascii=False))

    code, body = call(["release", "add"], {
        "operation_id": "bgm-release-v13b", "agent": "octie-agent",
        "reason": "发布 crab-coast-v13（多人在线版背景音乐 + 静态资源 Range）", "expected_revision": rev,
        "data": {"baseline_id": base, "delivery_id": DELIVERY,
                 "members": [{"id": rid, "revision": rrev, "cycle": 1}]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    obligations = ch["evaluation"]["obligations"]
    missing = [ob["condition_id"] for ob in obligations if ob["condition_id"] not in exe]
    if missing:
        print("!! 缺执行，无法关闭：", missing)
        return 1
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
                     for ob in obligations]},
    })
    if not ok("change close", code, body):
        return 1
    print("done. doc_rev:", body["document_revision"], "| release:", rel, "| baseline:", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
