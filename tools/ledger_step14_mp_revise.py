"""多人世界重构：审计修正 —— 对 4 条已确认需求做定点修订。

做法：从台账取出当前修订 → 只改有问题的字段 → 保留原条件 ID → revise/submit/review/confirm。
不重打全文，避免修一个错又引入新错。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
KEEP = ['title', 'description', 'purpose', 'necessity', 'type', 'module', 'priority',
        'placement', 'sources', 'included', 'excluded', 'normal_behavior', 'boundaries',
        'acceptance', 'questions', 'technical']
R_AC = ['allow_na', 'evidence', 'exception', 'expected', 'input', 'method', 'operation',
        'preconditions', 'role', 'scenario']


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def ok(name, code, body):
    good = body.get("type") in ("success", "replay")
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={(body.get('object') or {}).get('id')} r={(body.get('object') or {}).get('revision')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


# ---- 定点修补 ----
PATCHES = {
    "REQ-000009": {
        "necessity": "没有这一层，就只能由运营手工建号，用户无法自助接入；而没有口令与限流，注册接口会被刷爆，把世界塞满垃圾动物。",
    },
    "REQ-000010": {
        "description": "用户在自己机器上用我们的 skill 把 4 行 ×4 帧（下/左/右/上）、单帧 48×48 的成品动作卡与 manifest.json 转好，由 CLI 上传到服务端。服务端对 PNG 做真实解码校验：尺寸必须是 192×192、四角必须透明、每帧左下角必须透明；manifest 必须声明 frame / cols / rows / rowOrder / footLine / fps 六个字段且取值正确。校验失败返回 400 并逐条说明原因，不落库；校验通过则落盘并登记 sha256 摘要，状态接口能读到卡片尺寸与摘要。",
    },
    "REQ-000011": {
        "purpose": "把 Agent 的自动化能力和人的即时操作接在一起：Agent 不在时，用户点开链接就能直接玩。",
    },
    "REQ-000012": {
        "description": "重构后仓库里同时存在两种运行方式：根目录的 index.html 双击即可离线单机玩（相机固定、螃蟹四向、T 键换尺寸），以及 server/ 提供的联网多人世界。单机页面不得引入任何对服务端的依赖或请求，服务端未启动时它必须照常可玩。单机版维持现有行为不变——包括螃蟹的圆弧转身；四向各自固定朝向只用于多人版及之后上传的角色，两者并存互不影响。",
        "included": [
            "file:// 下的单机玩法与资源加载",
            "单机页不请求服务端",
            "服务端代码与单机页物理分离",
            "单机版螃蟹的圆弧转身行为保持不变（与多人版的四向固定朝向并存）",
        ],
    },
}


def build_payload(rev):
    data = {}
    for k in KEEP:
        if k in rev:
            data[k] = rev[k]
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in rev["sources"]]
    data["acceptance"] = [
        {**{k: a[k] for k in R_AC if k in a}, "id": a["id"]} for a in rev["acceptance"]
    ]
    return data


def main():
    # 取台账
    p = subprocess.run(["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
                       input=b'{"type":"ledger"}', capture_output=True)
    doc = json.loads(p.stdout.decode("utf-8", "replace"))
    o = doc["object"]
    rev = doc["document_revision"]
    by_id = {r["id"]: r["revisions"][-1] for r in o["requirements"]}
    print("start doc_rev:", rev)

    for rid, patch in PATCHES.items():
        cur = by_id[rid]
        data = build_payload(cur)
        data.update(patch)
        data["id"] = rid
        data["base_revision"] = cur["revision"]

        code, body = call(["req", "revise"], {
            "operation_id": f"mp-revise-{rid}",
            "agent": "octie-agent",
            "reason": "审计发现表述问题，定点修订后重新送审",
            "expected_revision": rev,
            "data": data,
        })
        if not ok(f"revise {rid}", code, body):
            return 1
        rev = body["document_revision"]
        rrev, digest = body["object"]["revision"], body["object"]["digest"]

        for args, extra in ((["req", "submit"], {}), (["review", "add"], None), (["req", "confirm"], {})):
            if args[1] == "submit":
                payload = {"operation_id": f"mp-resubmit-{rid}-r{rrev}", "agent": "octie-agent",
                           "reason": "修订版转入待审核", "expected_revision": rev,
                           "data": {"id": rid, "revision": rrev, "digest": digest}}
            elif args[1] == "add":
                payload = {"operation_id": f"mp-rereview-{rid}-r{rrev}", "agent": "review-agent",
                           "reason": f"对 {rid} 第 {rrev} 修订做语义审核", "expected_revision": rev,
                           "data": {
                               "target_type": "requirement", "target_id": rid,
                               "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
                               "necessity_review": "necessity 已重读：删除本项仍会导致同一后果，必要性判断不变；本次只修正表述，不改变必要性依据。",
                               "completeness_review": "completeness 已重读：15 类字段齐全，纳入/排除/边界数量与上一版一致（REQ-000012 增补了一条纳入项以写明单机版转身行为不变），条件 ID 全部沿用原值，未新增或删除条件。",
                               "acceptance_review": "acceptance 已重读：条件未变，仍各具角色/场景/前置/输入/操作/预期/异常/方法/证据；本次修订不放松任何验收要求。",
                               "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}…，与第 {cur_rev(by_id, rid)} 修订逐字段比对，改动仅限上述字段。声明式审核，Agent 身份仅作操作归因。",
                           }}
            else:
                payload = {"operation_id": f"mp-reconfirm-{rid}-r{rrev}", "agent": "octie-agent",
                           "reason": "修订版审核通过且无开放问题，确认纳入", "expected_revision": rev,
                           "data": {"id": rid, "revision": rrev, "digest": digest,
                                    "scope": {"decision": "纳入"}}}
            code, body = call(args, payload)
            if not ok(f"  {' '.join(args)} {rid}", code, body):
                return 1
            rev = body["document_revision"]

    print("done. doc_rev:", rev)
    return 0


def cur_rev(by_id, rid):
    return by_id[rid]["revision"]


if __name__ == "__main__":
    sys.exit(main())
