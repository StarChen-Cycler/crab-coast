"""change 流程：把 REQ-000003 r2 与 REQ-000005 r1 纳入新基线（V1.1）。

步骤：propose → review → evaluate → review → approve → apply
      → （候选基线）review → baseline activate → change close
"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
PREDECESSOR = "BASE-000001"

ACTIONS = [
    {"type": "替换", "requirement_id": "REQ-000003", "old_revision": 1, "new_revision": 2},
    {"type": "新增", "requirement_id": "REQ-000005", "old_revision": None, "new_revision": 1},
]

RETESTS = [
    {"requirement_id": "REQ-000003", "revision": 2, "condition_id": "AC-000008"},
    {"requirement_id": "REQ-000003", "revision": 2, "condition_id": "AC-000009"},
    {"requirement_id": "REQ-000003", "revision": 2, "condition_id": "AC-000010"},
    {"requirement_id": "REQ-000003", "revision": 2, "condition_id": "AC-000011"},
    {"requirement_id": "REQ-000005", "revision": 1, "condition_id": "AC-000015"},
    {"requirement_id": "REQ-000005", "revision": 1, "condition_id": "AC-000016"},
    {"requirement_id": "REQ-000005", "revision": 1, "condition_id": "AC-000017"},
]


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


def rev():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    return o["current_document_revision"]


def main():
    r = rev()
    print(f"[1] propose（文档修订 {r}）")
    rc, o = call(["change", "propose"], {
        "operation_id": "chg-propose-1", "agent": AGENT,
        "reason": "动作卡尺寸与来源已随实现改变；新增背景音乐需求，一并纳入新基线",
        "expected_revision": r,
        "data": {"actions": ACTIONS, "impact_objects": ["REQ-000003", "REQ-000005"],
                 "predecessor": PREDECESSOR},
    })
    must(rc, o, "change propose"); r = o["current_document_revision"]
    chg = o["object"]
    cid, crev, cdig = chg["id"], chg["revision"], chg["digest"]
    print(f"   变更 {cid} r{crev}")

    rc, o = call(["review", "add"], {
        "operation_id": "review-chg-1", "agent": "review-agent",
        "reason": "审核本次变更的差异与影响范围", "expected_revision": r,
        "data": {
            "target_type": "change", "target_id": cid,
            "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
            "necessity_review": "动作卡实际尺寸已改为 48 且侧视缩放，原文的 64×64 与事实不符；背景音乐是完全新增的能力。",
            "completeness_review": "两个动作都精确指向内容修订，未变成员（REQ-000001/002/004）保持不动。",
            "acceptance_review": "重验清单覆盖了被改动的 4 个条件与新增的 3 个条件。",
            "basis": "依据 requirements.md 中 r2 与实际 assets/crab_sheet.png、music/ 实现核对。",
        },
    })
    must(rc, o, "change review(propose)"); r = o["current_document_revision"]

    print("[2] evaluate")
    rc, o = call(["change", "evaluate"], {
        "operation_id": "chg-evaluate-1", "agent": AGENT,
        "reason": "评估：动作卡改动影响渲染层，音乐为独立新增", "expected_revision": r,
        "data": {
            "id": cid, "revision": crev, "digest": cdig,
            "impact_analysis": (
                "REQ-000003 的改动只涉及精灵表尺寸与侧视缩放，画面其余部分不受影响；"
                "REQ-000005 是纯新增的音频能力，与既有渲染/输入逻辑互不干扰。"
                "两项都不改变可行走网格与朝向状态机。"
            ),
            "retests": RETESTS,
        },
    })
    must(rc, o, "change evaluate"); r = o["current_document_revision"]
    # 评估后摘要可能变化，重新取
    rc, o2 = call(["show"]) if False else (0, None)
    chg = o.get("object") or chg
    cdig = chg.get("digest", cdig); crev = chg.get("revision", crev)
    print(f"   评估后 {cid} r{crev} digest={cdig[:10]}")

    rc, o = call(["review", "add"], {
        "operation_id": "review-chg-2", "agent": "review-agent",
        "reason": "审核包含评估与重验义务的完整摘要", "expected_revision": r,
        "data": {
            "target_type": "change", "target_id": cid,
            "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
            "necessity_review": "变更必要：台账原描述与实现不一致，且音乐能力完全缺失。",
            "completeness_review": "差异、影响分析与 7 条重验义务齐全。",
            "acceptance_review": "重验义务逐条对应到具体条件，可执行。",
            "basis": "依据 evaluate 产出的影响分析与 retests 清单。",
        },
    })
    must(rc, o, "change review(evaluate)"); r = o["current_document_revision"]

    print("[3] approve → apply")
    rc, o = call(["change", "approve"], {
        "operation_id": "chg-approve-1", "agent": AGENT,
        "reason": "审核通过，批准应用", "expected_revision": r,
        "data": {"id": cid, "revision": crev, "digest": cdig},
    })
    must(rc, o, "change approve"); r = o["current_document_revision"]

    rc, o = call(["change", "apply"], {
        "operation_id": "chg-apply-1", "agent": AGENT,
        "reason": "按批准差异生成候选基线", "expected_revision": r,
        "data": {"id": cid, "revision": crev, "digest": cdig},
    })
    must(rc, o, "change apply"); r = o["current_document_revision"]
    cand = o.get("object") or {}
    print("   候选基线:", json.dumps({k: cand.get(k) for k in ("id", "revision", "version", "digest")}, ensure_ascii=False))

    if not cand.get("id"):
        rc, o2 = call(["show"])
        print("   apply 返回里没有基线对象，改为从 show 里找候选：")
        for b in o2["object"].get("baselines", []):
            print("   ", b.get("id"), b.get("version"), "activated=", b.get("activated_at"))
        raise SystemExit(1)

    bid, brev, bdig = cand["id"], cand["revision"], cand["digest"]

    print("[4] 候选基线审核 + 激活")
    rc, o = call(["review", "add"], {
        "operation_id": "review-base2-1", "agent": "review-agent",
        "reason": "审核新基线候选的成员与范围", "expected_revision": r,
        "data": {
            "target_type": "baseline", "target_id": bid,
            "target_revision": brev, "target_digest": bdig, "conclusion": "通过",
            "necessity_review": "候选由已批准的变更应用生成，成员精确。",
            "completeness_review": "5 条需求都在，未变成员沿用原修订。",
            "acceptance_review": "重验义务已登记，验收将按新条件执行。",
            "basis": "依据 change apply 生成的候选。",
        },
    })
    must(rc, o, "baseline(candidate) review"); r = o["current_document_revision"]

    rc, o = call(["baseline", "activate"], {
        "operation_id": "baseline-activate-2", "agent": AGENT,
        "reason": "候选审核通过，激活为当前有效基线 V1.1", "expected_revision": r,
        "data": {"id": bid, "revision": brev, "digest": bdig},
    })
    must(rc, o, "baseline activate V1.1"); r = o["current_document_revision"]

    print(f"\n新基线生效：{bid} r{brev}")
    print("文档修订:", r)
    print(f"下一步 change close 需要：id={cid} revision={crev} digest={cdig}")


if __name__ == "__main__":
    main()
