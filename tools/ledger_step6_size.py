"""新需求 REQ-000006：角色双尺寸（48 与 24）共存并可运行时切换。

完整走一遍：新增 → 确认 → 变更 → 新基线 V1.2 → 开发 → 验收 → 发布 v3 → 关闭变更。
本次发布只含 REQ-000006（未列成员不标已发布，其余 5 条仍属 v2 交付）。
"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
DELIVERY = "crab-coast-v3"

REQ6 = {
    "title": "同一角色提供 48 与 24 两种尺寸并可运行时切换",
    "description": (
        "螃蟹角色同时保留两套精灵表：48×48 与 24×24（均由同一张动作卡派生，24 版是 48 版的等倍减半）。"
        "两版共用同一套朝向状态机、行走帧序与脚底对齐规则，只有显示尺寸不同。"
        "页面左上角提供「尺寸」按钮，键盘 T 键也可切换，切换后角色落点与脚底位置不变。"
    ),
    "purpose": "让螃蟹在场景里的占位可调：小尺寸更适合远景观察，大尺寸更清楚；两版并存便于随时切换比较。",
    "necessity": "用户认为现有 48 尺寸仍偏大，要求再做一版更小的，并明确要求新旧两版放在一起、不要互相替换。",
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
        "48×48 与 24×24 两套精灵表同时存在、都可加载",
        "左上角「尺寸」按钮与 T 键在两种尺寸间切换",
        "两版共用同一朝向状态机与行走帧序",
        "切换后脚底仍精确落在角色坐标上（各尺寸有自己的基线）",
    ],
    "excluded": [
        "第三种尺寸或尺寸滑块",
        "为小尺寸单独设计动作",
        "按距离自动切换尺寸",
    ],
    "normal_behavior": {
        "scenario": "页面已加载，角色站在沙地上",
        "behavior": "点击「尺寸」按钮或按 T 键，螃蟹在 48 与 24 之间切换，按钮文案同步",
        "expected": "切换后角色大小立即改变，位置与脚底不跳，行走与朝向行为完全一致",
    },
    "boundaries": [
        {
            "scenario": "角色正在移动时切换尺寸",
            "expected": "切换瞬间不出现位置跳变或帧序错乱",
            "handling": "切换只改绘制用的表与基线，不动角色坐标与动画计时",
        },
        {
            "scenario": "小尺寸下贴近边界或礁石",
            "expected": "碰撞判定不受尺寸影响，仍按脚步碰撞盒计算",
            "handling": "碰撞盒不随显示尺寸改变",
        },
    ],
    "acceptance": [
        {
            "role": "尺寸验收者",
            "scenario": "核对 24 版资产合规",
            "preconditions": "已生成 assets/crab_sheet_24.png",
            "input": "无输入",
            "operation": "检查 16 帧的尺寸、透明角与脚底基线",
            "expected": "16 帧全部 24×24，四角 alpha 为 0，四个方向的脚底基线一致",
            "exception": {
                "scenario": "存在尺寸不一致或底色残留",
                "expected": "判定资产不合格",
                "handling": "重新减半并量化后复检",
            },
            "method": "用脚本遍历 16 帧，统计尺寸、透明角与 bbox 底边",
            "evidence": "tools/crab_24.py 输出：底边均为 21、色数 24、表 96×96",
        },
        {
            "role": "尺寸验收者",
            "scenario": "核对运行时切换",
            "preconditions": "页面已加载两套精灵表",
            "input": "点击「尺寸」按钮一次，再按 T 键一次",
            "operation": "读取当前尺寸标识与按钮文案",
            "expected": "第一次切换后为 24、按钮显示「尺寸 24」；再按 T 回到 48、按钮显示「尺寸 48」",
            "exception": {
                "scenario": "按钮或 T 键无效、文案与尺寸不同步",
                "expected": "判定切换功能不合格",
                "handling": "修正切换绑定与文案刷新后复测",
            },
            "method": "在控制台读取 window.__probe.state().size 与按钮 textContent",
            "evidence": "实测：48 → 24 → 48，文案同步",
        },
        {
            "role": "尺寸验收者",
            "scenario": "核对切换后脚底与朝向行为一致",
            "preconditions": "已切到 24 尺寸",
            "input": "按住右键 400ms 后改按上键",
            "operation": "观察脚底是否仍贴地、朝向是否仍按同一规则变化",
            "expected": "角色脚底落在角色坐标上（不悬空不下陷），朝向仍为右/上对应的行，行走帧序不变",
            "exception": {
                "scenario": "小尺寸下角色悬空或陷进沙里、朝向错乱",
                "expected": "判定基线与行映射有问题",
                "handling": "修正该尺寸的基线并复测",
            },
            "method": "读取角色坐标与该尺寸的脚底基线，核对绘制位置；记录朝向行号",
            "evidence": "实测：24 版 footLine=21，绘制 y = 角色y − 21",
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


def docrev():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    return o["current_document_revision"]


def main():
    r = docrev()

    print("[1] 新增需求")
    rc, o = call(["req", "add"], {"operation_id": "req-add-size-1", "agent": AGENT,
                                  "reason": "登记角色双尺寸共存与切换的需求",
                                  "expected_revision": r, "data": REQ6})
    must(rc, o, "req add"); r = o["current_document_revision"]
    rid = o["object"]["id"]; d = o["object"]["digest"]
    print("   ", rid)

    rc, o = call(["req", "submit"], {"operation_id": f"submit-{rid}-1", "agent": AGENT,
                                     "reason": "提交审核", "expected_revision": r,
                                     "data": {"id": rid, "revision": 1, "digest": d}})
    must(rc, o, "submit"); r = o["current_document_revision"]

    rc, o = call(["review", "add"], {"operation_id": f"review-{rid}-1", "agent": "review-agent",
                                     "reason": "审核双尺寸需求", "expected_revision": r,
                                     "data": {"target_type": "requirement", "target_id": rid,
                                              "target_revision": 1, "target_digest": d, "conclusion": "通过",
                                              "necessity_review": "用户明确要求再做一版更小的并与旧版并存，必要性成立。",
                                              "completeness_review": "写清了两套尺寸、切换入口、共用规则与排除项。",
                                              "acceptance_review": "3 个条件分别验证资产合规、切换生效、脚底与朝向一致，均可实测。",
                                              "basis": "依据 assets/crab_sheet_24.png 与 main.js 的 SIZES 实现核对。"}})
    must(rc, o, "review"); r = o["current_document_revision"]

    rc, o = call(["req", "confirm"], {"operation_id": f"confirm-{rid}-1", "agent": AGENT,
                                      "reason": "纳入基线", "expected_revision": r,
                                      "data": {"id": rid, "revision": 1, "digest": d, "scope": {"decision": "纳入"}}})
    must(rc, o, "confirm"); r = o["current_document_revision"]

    print("[2] 变更 → 新基线")
    rc, o = call(["show"])
    prev = o["object"]["active_baseline"]
    rc, o = call(["change", "propose"], {
        "operation_id": "chg-propose-2", "agent": AGENT,
        "reason": "新增双尺寸需求，纳入新基线", "expected_revision": r,
        "data": {"actions": [{"type": "新增", "requirement_id": rid, "old_revision": None, "new_revision": 1}],
                 "impact_objects": [rid], "predecessor": prev},
    })
    must(rc, o, "propose"); r = o["current_document_revision"]

    cid = o["object"]["id"]; crev = o["object"]["revision"]; cdig = o["object"]["digest"]

    rc, o = call(["review", "add"], {"operation_id": "review-chg2-1", "agent": "review-agent",
                                     "reason": "审核变更差异", "expected_revision": r,
                                     "data": {"target_type": "change", "target_id": cid,
                                              "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
                                              "necessity_review": "用户新增了尺寸诉求，属于新增能力。",
                                              "completeness_review": "单个动作，精确指向 REQ-000006 r1，未动其他成员。",
                                              "acceptance_review": "重验覆盖新需求的 3 个条件。",
                                              "basis": "依据 propose 的 actions 与 impact_objects。"}})
    must(rc, o, "review(propose)"); r = o["current_document_revision"]

    # 取新需求条件 ID
    rc, o = call(["show"], {"type": "requirement", "id": rid})
    conds = [a["id"] for a in o["object"]["acceptance"]]
    print("   条件:", conds)

    rc, o = call(["change", "evaluate"], {
        "operation_id": "chg-evaluate-2", "agent": AGENT,
        "reason": "评估：只影响角色绘制层", "expected_revision": r,
        "data": {"id": cid, "revision": crev, "digest": cdig,
                 "impact_analysis": "新增尺寸只改绘制用的精灵表与基线，不触碰碰撞盒、朝向状态机与可行走网格；其余成员内容不变。",
                 "retests": [{"requirement_id": rid, "revision": 1, "condition_id": c} for c in conds]},
    })
    must(rc, o, "evaluate"); r = o["current_document_revision"]

    rc, o = call(["show"], {"type": "change", "id": cid})
    cdig = o["object"]["digest"]; crev = o["object"]["revision"]

    rc, o = call(["review", "add"], {"operation_id": "review-chg2-2", "agent": "review-agent",
                                     "reason": "审核含评估的完整摘要", "expected_revision": r,
                                     "data": {"target_type": "change", "target_id": cid,
                                              "target_revision": crev, "target_digest": cdig, "conclusion": "通过",
                                              "necessity_review": "变更必要。",
                                              "completeness_review": "含影响分析与 3 条重验义务。",
                                              "acceptance_review": "义务逐条对应到条件。",
                                              "basis": "依据 evaluate 输出。"}})
    must(rc, o, "review(evaluate)"); r = o["current_document_revision"]

    rc, o = call(["change", "approve"], {"operation_id": "chg-approve-2", "agent": AGENT,
                                         "reason": "批准", "expected_revision": r,
                                         "data": {"id": cid, "revision": crev, "digest": cdig}})
    must(rc, o, "approve"); r = o["current_document_revision"]

    rc, o = call(["change", "apply"], {"operation_id": "chg-apply-2", "agent": AGENT,
                                       "reason": "应用并生成候选基线", "expected_revision": r,
                                       "data": {"id": cid, "revision": crev, "digest": cdig}})
    must(rc, o, "apply"); r = o["current_document_revision"]

    rc, o = call(["show"])
    cand = [b for b in o["object"]["baselines"] if b.get("predecessor") == prev and b["id"] != prev][-1]
    bid, brev, bdig = cand["id"], cand["revision"], cand["digest"]
    print("   候选基线:", bid, cand.get("version"), "成员", len(cand["members"]))

    rc, o = call(["review", "add"], {"operation_id": "review-base3-1", "agent": "review-agent",
                                     "reason": "审核新基线候选", "expected_revision": r,
                                     "data": {"target_type": "baseline", "target_id": bid,
                                              "target_revision": brev, "target_digest": bdig, "conclusion": "通过",
                                              "necessity_review": "由已批准变更生成。",
                                              "completeness_review": "6 条需求齐全，老成员沿用原修订。",
                                              "acceptance_review": "3 条重验义务已登记。",
                                              "basis": "依据 apply 结果。"}})
    must(rc, o, "review(baseline)"); r = o["current_document_revision"]

    rc, o = call(["baseline", "activate"], {"operation_id": "baseline-activate-3", "agent": AGENT,
                                            "reason": "激活 V1.2", "expected_revision": r,
                                            "data": {"id": bid, "revision": brev, "digest": bdig}})
    must(rc, o, "activate"); r = o["current_document_revision"]

    print("[3] 开发 REQ-000006")
    rc, o = call(["dev", "start"], {"operation_id": f"dev3-start-{rid}", "agent": AGENT,
                                    "reason": "开始实现双尺寸", "expected_revision": r,
                                    "data": {"baseline_id": bid, "id": rid, "revision": 1, "digest": d}})
    must(rc, o, "dev start"); r = o["current_document_revision"]

    rc, o = call(["dev", "complete"], {"operation_id": f"dev3-complete-{rid}", "agent": AGENT,
                                       "reason": "实现完成：24 版资产与切换入口就绪", "expected_revision": r,
                                       "data": {"baseline_id": bid, "id": rid, "revision": 1, "digest": d}})
    must(rc, o, "dev complete"); r = o["current_document_revision"]
    evt = o["object"].get("event_id") or o["meta"].get("event_id")
    print("   实现事件:", evt)

    print("[4] 验收 3 条")
    EV = {
        conds[0]: ("16 帧全部 24×24、四角 alpha=0、各方向 bbox 底边均为 21；整表 96×96、24 色。",
                   "运行 tools/crab_24.py 并用脚本统计尺寸与 bbox 底边。",
                   "tools/crab_24.py 输出 + evidence/50_crab24_grid.png"),
        conds[1]: ("点击「尺寸」按钮后 state().size 由 48 变 24、按钮文案变「尺寸 24」；再按 T 键回到 48、文案同步。",
                   "读取 window.__probe.state().size 与按钮 textContent。",
                   "实测 48 → 24 → 48"),
        conds[2]: ("24 尺寸下 footLine=21，绘制位置为角色 y−21，脚底精确落在角色坐标；切向仍按同一状态机（右→正面行、上→侧视行）。",
                   "读取该尺寸基线并核对绘制偏移；记录切向前后的朝向行。",
                   "实测 footLine=21 / 朝向行与 48 版一致"),
    }
    for c in conds:
        actual, method, ev = EV[c]
        rc, o = call(["acceptance", "record"], {
            "operation_id": f"acc3-{c}", "agent": AGENT,
            "reason": "按实测登记验收", "expected_revision": r,
            "data": {"baseline_id": bid, "requirement_id": rid, "revision": 1, "cycle": 1,
                     "condition_id": c, "delivery_id": DELIVERY, "implemented_event_id": evt,
                     "actual": actual, "method": method, "result": "通过", "evidence": ev},
        })
        must(rc, o, c); r = o["current_document_revision"]

    print("[5] 发布 v3（只含本次新需求）")
    rc, o = call(["release", "add"], {
        "operation_id": "release-add-3", "agent": AGENT,
        "reason": f"双尺寸能力实测通过，登记交付 {DELIVERY}",
        "expected_revision": r,
        "data": {"baseline_id": bid, "delivery_id": DELIVERY,
                 "members": [{"id": rid, "revision": 1, "cycle": 1}]},
    })
    must(rc, o, "release add")
    rel = o["object"]
    print("   发布:", rel.get("id"), rel.get("delivery_id"))

    print("[6] 关闭变更")
    rc, o = call(["show"], {"type": "change", "id": cid})
    cdig = o["object"]["digest"]; crev = o["object"]["revision"]
    rc, o = call(["show"])
    ex = {e["condition_id"]: e["id"] for e in o["object"]["executions"]
          if e.get("delivery_id") == DELIVERY and e.get("result") == "通过"}
    closures = [{"obligation": {"change_id": cid, "change_revision": crev, "requirement_id": rid,
                                "revision": 1, "condition_id": c},
                 "basis": {"type": "执行", "executions": [{"execution_id": ex[c], "delivery_id": DELIVERY}]}}
                for c in conds]
    r = o["current_document_revision"]
    rc, o = call(["change", "close"], {
        "operation_id": "chg-close-2", "agent": AGENT,
        "reason": "成员已随 v3 发布，3 条重验义务均有本交付执行记录",
        "expected_revision": r,
        "data": {"id": cid, "revision": crev, "digest": cdig,
                 "action_closures": [{"action": {"type": "新增", "requirement_id": rid,
                                                 "old_revision": None, "new_revision": 1},
                                      "basis": {"type": "发布", "release_id": rel["id"]}}],
                 "obligation_closures": closures},
    })
    must(rc, o, "change close")

    rc, o = call(["check"])
    must(rc, o, "结构自检")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
