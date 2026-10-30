"""相机平滑/全量/自愈三条修复的台账闭环（CHG-000011）。

dev → 17 项验收（直接读 evidence/*.json 里的实测值，不手抄）→ 发布 crab-coast-v12 → 关闭变更。
基线/变更已经从 ledger_step30 落好（BASE-000012 V1.11 / CHG-000011），这里只补开发、验收与发布。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
DELIVERY = "crab-coast-v12"
IDS = "tools/_step30_ids.json"
EVIDENCE = {
    "camera": "evidence/camera.json",
    "smooth": "evidence/smooth.json",
    "visible": "evidence/visible.json",
}
# 条件 → 证据文件
COND_SOURCE = {}
for cid in ("AC-000070", "AC-000071", "AC-000072", "AC-000073", "AC-000074", "AC-000075"):
    COND_SOURCE[cid] = "camera"
for cid in ("AC-000076", "AC-000077", "AC-000078", "AC-000079",
            "AC-000080", "AC-000081", "AC-000082", "AC-000083"):
    COND_SOURCE[cid] = "smooth"
for cid in ("AC-000084", "AC-000085", "AC-000086"):
    COND_SOURCE[cid] = "visible"


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
        print("    raw:", (body.get("_raw") or "")[:500])
    return good


def load_evidence():
    """把三个证据文件里的断言结果按 condition 聚合（实测值原样进台账）。"""
    per = {}
    for key, path in EVIDENCE.items():
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for r in doc.get("results", []):
            per.setdefault(r["condition"], []).append({
                "file": path, "name": r["name"], "pass": r["pass"], "detail": r.get("detail")})
    return per


def main():
    with open(IDS, encoding="utf-8") as f:
        ids = json.load(f)
    chg = ids["change"]
    base = ids["baseline"]
    reqs = ids["requirements"]

    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    cur = {r["id"]: r["revisions"][-1] for r in doc["object"]["requirements"]}
    print("start doc_rev:", rev, "| active:", doc["object"]["active_baseline"], "| change:", chg)

    ev = load_evidence()
    missing = [c for c in COND_SOURCE if c not in ev]
    if missing:
        print("!! 证据里缺条件：", missing)
        return 1
    bad = [c for c, rows in ev.items() if any(not r["pass"] for r in rows) and c in COND_SOURCE]
    if bad:
        print("!! 有断言未通过，拒绝登记：", bad)
        return 1

    impl = {}
    for rid, rv in reqs.items():
        digest = cur[rid]["digest"]
        for act in ("start", "complete"):
            code, body = call(["dev", act], {
                "operation_id": f"smooth-dev-{rid}-{act}", "agent": "octie-agent",
                "reason": "开始实现轮次" if act == "start" else "实现完成，probe_smooth / probe_visible / e2e_camera 全 PASS",
                "expected_revision": rev,
                "data": {"baseline_id": base, "id": rid, "revision": rv, "digest": digest},
            })
            if not ok(f"dev {rid} {act}", code, body):
                return 1
            rev = body["document_revision"]
            if act == "complete":
                impl[rid] = body["object"]["implemented_event_id"]

    exe = {}
    for cid, key in COND_SOURCE.items():
        rows = ev[cid]
        rid = next(r for r in reqs if cid in {a["id"] for a in cur[r]["acceptance"]})
        rv = reqs[rid]
        actual = "；".join(f"{r['name']} → {json.dumps(r['detail'], ensure_ascii=False)}" for r in rows)
        code, body = call(["acceptance", "record"], {
            "operation_id": f"smooth-acc-{cid}", "agent": "octie-agent",
            "reason": "按实测证据登记该条件的验收结果", "expected_revision": rev,
            "data": {"baseline_id": base, "requirement_id": rid, "revision": rv, "cycle": 1,
                     "condition_id": cid, "delivery_id": DELIVERY,
                     "implemented_event_id": impl[rid],
                     "evidence": EVIDENCE[key], "actual": actual[:4000],
                     "method": "CDP 页面内取数（rAF 逐帧采样 / 快照年龄 / 画布像素）+ REST/WS 对照",
                     "result": "通过"},
        })
        if not ok(f"acc {cid}", code, body):
            return 1
        rev = body["document_revision"]
        exe[cid] = body["object"]["id"]

    code, body = call(["release", "add"], {
        "operation_id": "smooth-release-v12", "agent": "octie-agent",
        "reason": "发布 crab-coast-v12（快照全量 + 连接自愈 + 插值渲染）", "expected_revision": rev,
        "data": {"baseline_id": base, "delivery_id": DELIVERY,
                 "members": [{"id": rid, "revision": rv, "cycle": 1} for rid, rv in reqs.items()]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "smooth-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、17 项重验义务已逐条登记执行结果",
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
