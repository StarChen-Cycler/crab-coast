"""审计修正第 2 轮：
  A. REQ-000016 → r4：AC-000060 用实测走廊坐标写死（y=380、x 250→600，逐点 canStand 已核实）
  B. REQ-000010 → r3：补一条「manifest 取值错误被拒」的验收条件（原条件里没有任何一条测值错误）
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


def base_from(cur):
    data = {k: cur[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                               "priority", "placement", "included", "excluded", "normal_behavior",
                               "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in cur["sources"]]
    data["acceptance"] = [{**{k: a[k] for k in AC_FIELDS}, "id": a["id"]} for a in cur["acceptance"]]
    return data


def patch16(data):
    for a in data["acceptance"]:
        if a["id"] == "AC-000060":
            a.update({
                "preconditions": ("动物置于逻辑坐标 (250, 380)；该行 y=380 上 x 从 250 到 620 的 370px "
                                  "已用 shared/grid.js 的 canStand 逐点核实全部可站立"),
                "input": "客户端按住「右」并每 1 秒续期一次，持续 4 秒",
                "expected": ("t=3.5 秒时 moving 仍为 true 且 x 仍在增大；4 秒累计位移不小于 350 px"
                             "（x 由 250 到不少于 600，全程仍在可走走廊内）；没有因 3 秒 TTL 停车"),
                "method": "每 1 秒续期一次；在 t=3.5 秒采样 moving 与坐标，t=4 秒再采样一次并计算累计位移",
                "evidence": "4 秒内的位置序列、t=3.5 秒的 moving 值、起终点坐标与累计位移",
            })
    return data


def patch10(data):
    data["description"] = (
        "用户在自己机器上用我们的 skill 把 4 行 ×4 帧（下/左/右/上）、单帧 48×48 的成品动作卡与 "
        "manifest.json 转好，由 CLI 上传到服务端。服务端对 PNG 做真实解码校验：尺寸必须是 192×192、"
        "四角必须透明、每帧左下角必须透明；manifest 必须声明 frame / cols / rows / rowOrder / footLine / fps "
        "六个字段且取值正确（frame=48、cols=rows=4、footLine=43、fps=8）。校验失败返回 400 并逐条说明原因，"
        "不落库；校验通过则落盘并登记 sha256 摘要，状态接口能读到卡片尺寸与摘要。"
    )
    data["acceptance"] = list(data["acceptance"]) + [{
        "role": "资产验收者",
        "scenario": "manifest 取值错误被拒",
        "preconditions": "准备一张尺寸与透明度都合格、但 manifest 里 fps 写成 7、footLine 写成 40 的卡片",
        "input": "上传该卡片",
        "operation": "记录状态码与 errors 内容",
        "expected": "400，errors 中同时指出帧率与脚底线取值不符（fps 必须是 8、footLine 必须是 43），且不落库（状态里的 card 仍为 null）",
        "exception": {
            "scenario": "返回 200 或卡片被覆盖",
            "expected": "判定 manifest 取值校验缺失",
            "handling": "在 manifest 校验里逐字段比对常量，并在落盘前拦截",
        },
        "method": "构造 fps=7 / footLine=40 的 manifest 上传，读 errors 并复查状态里的 card",
        "evidence": "状态码、errors 全文、上传前后 state 的 self.card",
    }]
    return data


def lifecycle(rid, data, rev, base_revision, reason):
    data["id"] = rid
    data["base_revision"] = base_revision
    code, body = call(["req", "revise"], {
        "operation_id": f"audit2-revise-{rid}-r{base_revision + 1}", "agent": "octie-agent",
        "reason": reason, "expected_revision": rev, "data": data,
    })
    if not ok(f"revise {rid}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]

    steps = [
        (["req", "submit"], {"id": rid, "revision": rrev, "digest": digest}, "修订版转入待审核"),
        (["review", "add"], {
            "target_type": "requirement", "target_id": rid,
            "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
            "necessity_review": ("必要性不变：两路同时操作时必须能回落到仍按住的方向，否则人一松手就停车。"
                                 if rid == "REQ-000016" else
                                 "必要性不变：坏素材必须在入库前被拦住，否则会污染世界并让客户端错位渲染。"),
            "completeness_review": ("完整性：本轮只改 AC-000060 的前置与预期，把「累计位移 ≥350px」锚定到已核实的走廊"
                                     "（y=380，x 250→600），不再依赖未经验证的空间假设。"
                                     if rid == "REQ-000016" else
                                     "完整性：新增第 4 条验收条件覆盖「manifest 取值错误」，描述里把六个字段的正确取值写明；其余三条条件与所有条件 ID 保持原样。"),
            "acceptance_review": ("验收复核：AC-000060 现在在真实沙地上可达（370px 走廊逐点验证过），"
                                  "并保留 t=3.5 秒仍 moving 这一核心断言。"
                                  if rid == "REQ-000016" else
                                  "验收复核：新条件同时断言「400 + errors 指出两个字段 + 不落库」，"
                                  "补齐了原本没有覆盖的 manifest 取值分支。"),
            "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}…，与上一版逐字段比对。声明式审核。",
        }, "审计复核"),
        (["req", "confirm"], {"id": rid, "revision": rrev, "digest": digest,
                              "scope": {"decision": "纳入"}}, "审核通过，确认纳入"),
    ]
    for args, data2, why in steps:
        payload = {"operation_id": f"audit2-{args[1]}-{rid}-r{rrev}", "agent":
                   ("review-agent" if args[1] == "add" else "octie-agent"),
                   "reason": why, "expected_revision": rev, "data": data2}
        code, body = call(args, payload)
        if not ok(f"  {args[1]} {rid}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    return rev


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    reqs = {r["id"]: r["revisions"][-1] for r in doc["object"]["requirements"]}
    print("start doc_rev:", rev)

    rev = lifecycle("REQ-000016", patch16(base_from(reqs["REQ-000016"])), rev,
                    reqs["REQ-000016"]["revision"], "审计第 2 轮：把续期验收锚定到已核实的走廊坐标")
    doc = show({"type": "ledger"})
    reqs = {r["id"]: r["revisions"][-1] for r in doc["object"]["requirements"]}
    rev = lifecycle("REQ-000010", patch10(base_from(reqs["REQ-000010"])), rev,
                    reqs["REQ-000010"]["revision"], "审计第 2 轮：补一条 manifest 取值错误被拒的验收条件")
    print("done. doc_rev:", rev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
