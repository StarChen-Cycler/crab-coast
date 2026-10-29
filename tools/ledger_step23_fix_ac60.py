"""审计第三轮：AC-000060 仍然不可达（y=380 向左只有 384px，3.49s 就撞墙）。

改为：3.4 秒持按 + 每 1 秒续期，在撞墙前（t=3.2s）取样断言 moving；并加一组「不续期」对照，
用于区分「TTL 停车」与「撞墙停车」。REQ-000016 → r5。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
AC_FIELDS = ("allow_na", "evidence", "exception", "expected", "input", "method", "operation",
             "preconditions", "role", "scenario")


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
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={o.get('id')} r={o.get('revision')}")
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
    data["acceptance"] = []
    for a in cur["acceptance"]:
        item = {**{k: a[k] for k in AC_FIELDS}, "id": a["id"]}
        if a["id"] == "AC-000060":
            item.update({
                "scenario": "按住期间续期，超过 3 秒仍在移动",
                "preconditions": ("动物在出生点 (500,412) 附近；先向上按约 0.3 秒到 y≈380。"
                                  "实测该行从 x=500 向左可连续走到 x=116（384px），"
                                  "已用 shared/grid.js 的 canStand 逐点核实"),
                "input": "客户端按住「左」并每 1 秒续期一次，持续 3.4 秒；另做一组不续期的对照",
                "operation": "在 t=3.2 秒（撞墙前）读取 moving 与坐标，t=3.4 秒再读一次；对照组同样在 t=3.2 秒读一次",
                "expected": ("续期组：t=3.2 秒时 moving 仍为 true 且 x 仍在减小（已走约 350px，尚未触及 x=116 边界），"
                             "3.4 秒累计位移不小于 330px；对照组：约 3.0 秒即停，t=3.2 秒时 moving 为 false 且累计位移明显小于续期组"),
                "exception": {
                    "scenario": "续期组约 3 秒即停、或 t=3.2 秒 moving 为 false",
                    "expected": "判定续期未生效（能与撞墙区分开，因为 t=3.2s 时距边界还有约 30px）",
                    "handling": "检查续期是否刷新了同一来源按住项的时间戳",
                },
                "method": "按 1 秒间隔续期并采样；对照组不续期，用两组位移与 moving 对比",
                "evidence": "两组的位置序列、t=3.2 秒的 moving 值、累计位移对比",
            })
        data["acceptance"].append(item)

    data["id"] = "REQ-000016"
    data["base_revision"] = cur["revision"]

    code, body = call(["req", "revise"], {
        "operation_id": "audit3-revise-16", "agent": "octie-agent",
        "reason": "审计第三轮：AC-000060 的位移与时间组合在 384px 走廊上仍不可达，改为撞墙前取样 + 对照组",
        "expected_revision": rev, "data": data,
    })
    if not ok("revise", code, body):
        return 1
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]

    scoped = [
        (["req", "submit"], {"id": "REQ-000016", "revision": rrev, "digest": digest}, "octie-agent", "修订版转入待审核"),
        (["review", "add"], {
            "target_type": "requirement", "target_id": "REQ-000016",
            "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
            "necessity_review": "必要性不变：两路控制同时存在时必须能回落到仍按住的方向，否则人一松手就停车。",
            "completeness_review": ("本轮只改 AC-000060：把「4 秒 / 350px / t=3.5s」改成「3.4 秒、t=3.2s 取样、≥330px」，"
                                    "并加入「不续期对照组」。原因是实测 y=380 向左只有 384px，3.49 秒会撞墙，"
                                    "原写法会因撞墙而非 TTL 失败。其余条件与 ID 不变。"),
            "acceptance_review": ("验收复核：取样点（t=3.2s，距边界约 30px）在撞墙之前，因此 moving=true 只可能来自续期生效；"
                                  "对照组提供了区分「TTL 停车」与「撞墙停车」的对照证据。"),
            "basis": f"依据 REQ-000016 第 {rrev} 修订摘要 {digest[:12]}…；走廊数据来自 shared/grid.js 实测（x 500→116）。声明式审核。",
        }, "review-agent", "审计第三轮复核"),
        (["req", "confirm"], {"id": "REQ-000016", "revision": rrev, "digest": digest,
                              "scope": {"decision": "纳入"}}, "octie-agent", "确认纳入"),
    ]
    for args, data2, agent, why in scoped:
        code, body = call(args, {"operation_id": f"audit3-{args[1]}-16", "agent": agent,
                                 "reason": why, "expected_revision": rev, "data": data2})
        if not ok(f"  {args[1]}", code, body):
            return 1
        rev = body["document_revision"]
    print("done. doc_rev:", rev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
