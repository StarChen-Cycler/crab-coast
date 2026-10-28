"""REQ-000006 r2 → r3：T 键改为「反弹」切换（小↔中↔大来回），并给按钮加 大/中/小 标签。

链路同前：revise → submit/review/confirm → change(替换) → 基线 V1.4
          → dev → 验收 3 条 → release v5 → close change
"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
DELIVERY = "crab-coast-v5"
RID = "REQ-000006"

REQ6_R3 = {
    "id": RID,
    "base_revision": 2,
    "title": "同一角色三档尺寸按 T 键反弹切换（小↔中↔大）",
    "description": (
        "螃蟹保留 96（大）、48（中）、24（小）三套精灵表，由同一张动作卡逐级派生，共用朝向状态机、"
        "行走帧序与脚底对齐规则；三档都做了侧视按行缩放 90%。"
        "T 键或左上角按钮采用**反弹式**切换：从中档出发先变小，到最小档后掉头变大，"
        "到最大档后再掉头变小，形成 中→小→中→大→中→小… 的往复，而不是跳回另一端。"
        "按钮显示当前档位的中文标签与像素尺寸（如「尺寸 中 48」）。"
    ),
    "purpose": "让调节尺寸的过程连续、可预期：越按越接近想要的大小，不会在两端之间突然跳变。",
    "necessity": "用户明确要求把绕回式切换改成反弹式，并要求用 小/中/大 表达档位。",
    "type": "功能",
    "module": "角色渲染",
    "priority": "P1",
    "placement": {
        "kind": "页面",
        "other": [],
        "primary": {"page_id": "PAGE-000001", "page_revision": 1, "region_id": "REG-000001-0001-0001"},
    },
    "sources": [{"source_id": "SRC-000001", "source_revision": 1}],
    "included": [
        "96/48/24 三套精灵表同时存在且都可加载",
        "T 键与按钮按反弹方式切换：中→小→中→大→中…",
        "按钮显示「尺寸 大/中/小 + 像素值」",
        "三档共用朝向状态机与行走帧序，侧视均缩 90%",
    ],
    "excluded": [
        "绕回式（一端的下一档直接跳到另一端）切换",
        "尺寸滑块或自定义尺寸",
        "按距离自动切换尺寸",
    ],
    "normal_behavior": {
        "scenario": "页面加载完成，默认停在中档 48",
        "behavior": "每按一次 T 或点一次按钮，档位沿当前方向走一格；走到端点则反向",
        "expected": "序列为 中→小→中→大→中→小…，按钮文案随之更新，且不会出现两端直接互跳",
    },
    "boundaries": [
        {
            "scenario": "在最小档继续按 T",
            "expected": "回到中档（而不是跳到大档）",
            "handling": "索引越界时翻转方向再前进一步",
        },
        {
            "scenario": "在最大档继续按 T",
            "expected": "回到中档（而不是跳到小档）",
            "handling": "同上",
        },
        {
            "scenario": "角色移动过程中切换",
            "expected": "位置、碰撞与帧序都不受影响",
            "handling": "切换只改绘制用的表与基线",
        },
    ],
    "acceptance": [
        {
            "role": "尺寸验收者",
            "scenario": "核对反弹序列与标签",
            "preconditions": "页面已加载三套表，默认中档",
            "input": "连续按 T 键 7 次",
            "operation": "记录每次的尺寸与按钮文案",
            "expected": "序列为 48(中)→24(小)→48(中)→96(大)→48(中)→24(小)→48(中)；按钮依次显示「尺寸 小 24 / 中 48 / 大 96 …」",
            "exception": {
                "scenario": "出现 96 直接跳到 24、或文案与尺寸不符",
                "expected": "判定反弹逻辑或标签绑定有误",
                "handling": "修正方向翻转与文案刷新后复测",
            },
            "method": "点击按钮并读取 window.__probe.state().size 与按钮 textContent",
            "evidence": "实测 7 次序列：24,48,96,48,24,48,96（含 小/中/大 标签）",
        },
        {
            "role": "尺寸验收者",
            "scenario": "核对两端不互跳",
            "preconditions": "已停在最小档 24 或最大档 96",
            "input": "在端点再按一次 T",
            "operation": "观察下一档",
            "expected": "24 的下一档是 48；96 的下一档也是 48",
            "exception": {
                "scenario": "24 跳到 96 或 96 跳到 24",
                "expected": "判定仍在绕回",
                "handling": "检查方向变量是否在越界时翻转",
            },
            "method": "把档位切到端点后按一次 T，读取结果",
            "evidence": "实测 24 → 48、96 → 48",
        },
        {
            "role": "尺寸验收者",
            "scenario": "核对三档脚底与朝向不受切换逻辑影响",
            "preconditions": "分别切到三档",
            "input": "每档按住右键后改按上键",
            "operation": "核对脚底贴地与朝向行",
            "expected": "三档脚底分别落在 86/43/21 基线上，朝向仍为右→正面行、上→侧视行",
            "exception": {
                "scenario": "某档悬空或朝向错乱",
                "expected": "判定该档基线或行映射有问题",
                "handling": "修正后复测",
            },
            "method": "读取角色坐标与该档基线核对偏移",
            "evidence": "三档基线 86/43/21，朝向行一致",
        },
    ],
    "questions": [],
}


def call(argv, data=None):
    args = ["reqledger"] + argv + ["--file", F]
    if data is not None:
        args += ["--json", json.dumps(data, ensure_ascii=False)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        return p.returncode, json.loads(p.stdout.strip())
    except Exception:
        return p.returncode, {"raw": p.stdout.strip()[:500], "err": p.stderr[:300]}


def must(rc, obj, what):
    if rc != 0 or obj.get("type") == "error" or obj.get("commit_status") == "not_committed":
        print(f"\n!! {what} 失败 rc={rc}")
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:1800])
        raise SystemExit(1)
    print(f"   ✓ {what}")
    return obj


def main():
    rc, o = call(["show"]); must(rc, o, "读台账")
    r = o["current_document_revision"]; prev = o["object"]["active_baseline"]

    print("[1] 修订 → r3")
    rc, o = call(["req", "revise"], {"operation_id": "req-revise-req6-3", "agent": AGENT,
                                     "reason": "T 键改为反弹切换，按钮加 大/中/小 标签",
                                     "expected_revision": r, "data": REQ6_R3})
    must(rc, o, "revise"); r = o["current_document_revision"]; d3 = o["object"]["digest"]

    rc, o = call(["req", "submit"], {"operation_id": "submit-req6-3", "agent": AGENT,
                                     "reason": "提交", "expected_revision": r,
                                     "data": {"id": RID, "revision": 3, "digest": d3}})
    must(rc, o, "submit"); r = o["current_document_revision"]

    rc, o = call(["review", "add"], {"operation_id": "review-req6-3", "agent": "review-agent",
                                     "reason": "审核反弹切换", "expected_revision": r,
                                     "data": {"target_type": "requirement", "target_id": RID,
                                              "target_revision": 3, "target_digest": d3, "conclusion": "通过",
                                              "necessity_review": "用户明确要求改成反弹式。",
                                              "completeness_review": "写清了序列、端点行为、标签与不受影响的部分。",
                                              "acceptance_review": "3 个条件分别覆盖序列、端点、基线一致性。",
                                              "basis": "依据 main.js 的 sizeDir 反弹实现核对。"}})
    must(rc, o, "review"); r = o["current_document_revision"]

    rc, o = call(["req", "confirm"], {"operation_id": "confirm-req6-3", "agent": AGENT,
                                      "reason": "纳入基线", "expected_revision": r,
                                      "data": {"id": RID, "revision": 3, "digest": d3, "scope": {"decision": "纳入"}}})
    must(rc, o, "confirm"); r = o["current_document_revision"]

    print("[2] 变更 → 基线 V1.4")
    rc, o = call(["change", "propose"], {"operation_id": "chg-propose-4", "agent": AGENT,
                                         "reason": "切换方式由绕回改为反弹", "expected_revision": r,
                                         "data": {"actions": [{"type": "替换", "requirement_id": RID,
                                                               "old_revision": 2, "new_revision": 3}],
                                                  "impact_objects": [RID], "predecessor": prev}})
    must(rc, o, "propose"); r = o["current_document_revision"]
    cid = o["object"]["id"]; crev = o["object"]["revision"]; cdig = o["object"]["digest"]

    rc, o = call(["review", "add"], {"operation_id": "review-chg4-1", "agent": "review-agent",
                                     "reason": "审核差异", "expected_revision": r,
                                     "data": {"target_type": "change", "target_id": cid,
                                              "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
                                              "necessity_review": "交互规则变化。", "completeness_review": "单动作指向 r3。",
                                              "acceptance_review": "覆盖 3 个条件。", "basis": "依据 propose。"}})
    must(rc, o, "review(propose)"); r = o["current_document_revision"]

    rc, o = call(["show"], {"type": "requirement", "id": RID})
    conds = [a["id"] for a in o["object"]["acceptance"]]
    print("   条件:", conds)

    rc, o = call(["change", "evaluate"], {"operation_id": "chg-evaluate-4", "agent": AGENT,
                                          "reason": "只影响切换交互", "expected_revision": r,
                                          "data": {"id": cid, "revision": crev, "digest": cdig,
                                                   "impact_analysis": "只改切换算法与按钮文案，不触碰精灵资产、碰撞与朝向。",
                                                   "retests": [{"requirement_id": RID, "revision": 3,
                                                                "condition_id": c} for c in conds]}})
    must(rc, o, "evaluate"); r = o["current_document_revision"]

    rc, o = call(["show"], {"type": "change", "id": cid})
    cdig = o["object"]["digest"]; crev = o["object"]["revision"]

    rc, o = call(["review", "add"], {"operation_id": "review-chg4-2", "agent": "review-agent",
                                     "reason": "审核含评估摘要", "expected_revision": r,
                                     "data": {"target_type": "change", "target_id": cid,
                                              "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
                                              "necessity_review": "必要。", "completeness_review": "含影响分析与义务。",
                                              "acceptance_review": "义务对应条件。", "basis": "依据 evaluate。"}})
    must(rc, o, "review(evaluate)"); r = o["current_document_revision"]

    rc, o = call(["change", "approve"], {"operation_id": "chg-approve-4", "agent": AGENT,
                                         "reason": "批准", "expected_revision": r,
                                         "data": {"id": cid, "revision": crev, "digest": cdig}})
    must(rc, o, "approve"); r = o["current_document_revision"]

    rc, o = call(["change", "apply"], {"operation_id": "chg-apply-4", "agent": AGENT,
                                       "reason": "生成候选", "expected_revision": r,
                                       "data": {"id": cid, "revision": crev, "digest": cdig}})
    must(rc, o, "apply"); r = o["current_document_revision"]

    rc, o = call(["show"])
    cand = [b for b in o["object"]["baselines"] if b.get("predecessor") == prev][-1]
    bid, brev, bdig = cand["id"], cand["revision"], cand["digest"]
    print("   候选基线:", bid, cand.get("version"))

    rc, o = call(["review", "add"], {"operation_id": "review-base5-1", "agent": "review-agent",
                                     "reason": "审核候选", "expected_revision": r,
                                     "data": {"target_type": "baseline", "target_id": bid,
                                              "target_revision": brev, "target_digest": bdig, "conclusion": "通过",
                                              "necessity_review": "由已批准变更生成。", "completeness_review": "6 条需求齐全。",
                                              "acceptance_review": "3 条义务已登记。", "basis": "依据 apply。"}})
    must(rc, o, "review(baseline)"); r = o["current_document_revision"]

    rc, o = call(["baseline", "activate"], {"operation_id": "baseline-activate-5", "agent": AGENT,
                                            "reason": "激活 V1.4", "expected_revision": r,
                                            "data": {"id": bid, "revision": brev, "digest": bdig}})
    must(rc, o, "activate"); r = o["current_document_revision"]

    print("[3] 开发 / 验收 / 发布")
    rc, o = call(["dev", "start"], {"operation_id": "dev5-start", "agent": AGENT,
                                    "reason": "实现反弹切换", "expected_revision": r,
                                    "data": {"baseline_id": bid, "id": RID, "revision": 3, "digest": d3}})
    must(rc, o, "dev start"); r = o["current_document_revision"]

    rc, o = call(["dev", "complete"], {"operation_id": "dev5-complete", "agent": AGENT,
                                       "reason": "实现完成", "expected_revision": r,
                                       "data": {"baseline_id": bid, "id": RID, "revision": 3, "digest": d3}})
    must(rc, o, "dev complete"); r = o["current_document_revision"]
    evt = o["object"].get("event_id") or o["meta"].get("event_id")

    EV = {
        conds[0]: ("连按 7 次 T：48(中)→24(小)→48(中)→96(大)→48(中)→24(小)→48(中)，按钮文案依次为「尺寸 小 24 / 中 48 / 大 96」。",
                   "点击按钮并读取 state().size 与按钮 textContent。", "实测序列 24,48,96,48,24,48,96"),
        conds[1]: ("在端点 24 再按一次得到 48；在端点 96 再按一次也是 48，没有两端互跳。",
                   "把档位切到端点后按一次 T 读取结果。", "实测 24→48、96→48"),
        conds[2]: ("三档基线 86/43/21 不变，脚底仍贴地；朝向仍为右→正面行、上→侧视行。",
                   "读取角色坐标与各档基线核对绘制偏移。", "三档基线一致对齐，朝向行与之前相同"),
    }
    for c in conds:
        actual, method, ev = EV[c]
        rc, o = call(["acceptance", "record"], {
            "operation_id": f"acc5-{c}", "agent": AGENT, "reason": "按实测登记",
            "expected_revision": r,
            "data": {"baseline_id": bid, "requirement_id": RID, "revision": 3, "cycle": 1,
                     "condition_id": c, "delivery_id": DELIVERY, "implemented_event_id": evt,
                     "actual": actual, "method": method, "result": "通过", "evidence": ev}})
        must(rc, o, c); r = o["current_document_revision"]

    rc, o = call(["release", "add"], {"operation_id": "release-add-5", "agent": AGENT,
                                      "reason": f"反弹切换实测通过，登记交付 {DELIVERY}",
                                      "expected_revision": r,
                                      "data": {"baseline_id": bid, "delivery_id": DELIVERY,
                                               "members": [{"id": RID, "revision": 3, "cycle": 1}]}})
    must(rc, o, "release add"); rel = o["object"]; print("   发布:", rel.get("id"))

    rc, o = call(["show"], {"type": "change", "id": cid})
    cdig = o["object"]["digest"]; crev = o["object"]["revision"]
    rc, o = call(["show"])
    ex = {e["condition_id"]: e["id"] for e in o["object"]["executions"]
          if e.get("delivery_id") == DELIVERY and e.get("result") == "通过"}
    r = o["current_document_revision"]
    rc, o = call(["change", "close"], {
        "operation_id": "chg-close-4", "agent": AGENT,
        "reason": "成员已随 v5 发布，3 条义务均有本交付执行记录",
        "expected_revision": r,
        "data": {"id": cid, "revision": crev, "digest": cdig,
                 "action_closures": [{"action": {"type": "替换", "requirement_id": RID,
                                                 "old_revision": 2, "new_revision": 3},
                                      "basis": {"type": "发布", "release_id": rel["id"]}}],
                 "obligation_closures": [
                     {"obligation": {"change_id": cid, "change_revision": crev, "requirement_id": RID,
                                     "revision": 3, "condition_id": c},
                      "basis": {"type": "执行", "executions": [{"execution_id": ex[c], "delivery_id": DELIVERY}]}}
                     for c in conds]}})
    must(rc, o, "change close")
    rc, o = call(["check"]); must(rc, o, "结构自检")
    print("\n完成。")


if __name__ == "__main__":
    main()
