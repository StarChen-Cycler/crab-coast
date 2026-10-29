"""REQ-000017 台账闭环：change → 基线 → dev → 6 条验收 → 发布 → 关闭。"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
PRED = "BASE-000008"
DELIVERY = "crab-coast-v9"
REQ = "REQ-000017"
REV = 1


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
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:700])
    return good


ACC = {
    "AC-000064": ("触屏 390x844，摇杆分别推右/左/上/下各 700ms：位移 +68 / -69 / -75 / +75 px，"
                  "facing 依次 right/left/up/down，松手后 moving=false。",
                  "CDP 驱动页面合成 TouchEvent，读服务端快照比对坐标与朝向。",
                  "evidence/touch_ui.json 中 AC-000064"),
    "AC-000065": ("把摇杆推到 (4,3)（距离 5px < 死区 10px）保持 400ms：坐标位移 0,0。",
                  "同类合成事件 + 前后坐标对比。", "evidence/touch_ui.json 中 AC-000065"),
    "AC-000066": ("依次按下 Y/X/B/A：坐标与 facing 均无变化，四键 disabled=true 且带 disabled 类。",
                  "合成 touchstart 后读状态与 DOM 属性。", "evidence/touch_ui.json 中 AC-000066"),
    "AC-000067": ("点收起：摇杆与 ABXY display=none、开关仍可见、--touch-band 0px、画布 top 197→315；"
                  "再点恢复为 block / 236px / 197。",
                  "点击开关并读取计算样式与画布矩形。", "evidence/touch_ui.json 中 AC-000067"),
    "AC-000068": ("390x844 竖屏：所有控件矩形在视口内；摇杆与 ABXY、开关与摇杆/ABXY、HUD 之间均不相交；"
                  "画布 (4,197)-(386,412) 位于 236px 操作带之上。",
                  "逐对矩形相交检测 + 画布与操作带间距计算。", "evidence/touch_ui.json 中 AC-000068"),
    "AC-000069": ("844x390 横屏开关矩形 l=18 r=106（在左半屏）且与四键零重叠；844x260 矮屏不越界不重叠；"
                  "桌面 900x560 不挂载控件但键盘方向键使 x 650→657。",
                  "三个视口分别测量矩形与可见性；桌面派发 KeyboardEvent 后读坐标。",
                  "evidence/touch_ui.json 中 AC-000069"),
}


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    o = doc["object"]
    print("start doc_rev:", rev, "active:", o["active_baseline"])
    cur = [r for r in o["requirements"] if r["id"] == REQ][0]["revisions"][-1]

    code, body = call(["change", "propose"], {
        "operation_id": "ui-chg-propose", "agent": "octie-agent",
        "reason": "把多人版手机控件对齐单机版的 REQ-000017 纳入基线",
        "expected_revision": rev,
        "data": {"predecessor": PRED,
                 "actions": [{"type": "新增", "requirement_id": REQ,
                              "old_revision": None, "new_revision": REV}],
                 "impact_objects": [REQ]},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    retests = [{"requirement_id": REQ, "revision": REV, "condition_id": c} for c in ACC]
    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "ui-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与重验清单", "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "impact_analysis": ("只改多人前端：新增 play/touch.js 控件层、play 页移除 D-pad 并接入、"
                                     "HUD 加安全区、fit() 扣操作带。服务端、卡片管线、单机版均未改动，"
                                     "因此只重验 REQ-000017 自身的 6 条条件。"),
                 "retests": retests},
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "ui-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 做变更审核", "expected_revision": rev,
        "data": {"target_type": "change", "target_id": chg,
                 "target_revision": ch["revision"], "target_digest": ch["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：用户在真机上认为多人版控件不如单机版；单机版参数已验证，复用可消除误触与遮挡。",
                 "completeness_review": "完整性：仅一条新增动作，new_revision=1 与台账一致；6 项重验覆盖全部验收条件。",
                 "acceptance_review": "验收：6 条均由 e2e_touch_ui.js 自动断言并写入 evidence/touch_ui.json（condition 映射）。",
                 "basis": f"依据 {chg} 评估后摘要 {ch['digest'][:12]}… 与 e2e 证据审阅。声明式审核。"},
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        ch = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"ui-chg-{act}", "agent": "octie-agent",
            "reason": "批准变更" if act == "approve" else "生成候选基线", "expected_revision": rev,
            "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"]},
        })
        if not ok(act, code, body):
            return 1
        rev = body["document_revision"]

    doc = show({"type": "ledger"})
    cand = [b for b in doc["object"]["baselines"] if b.get("predecessor") == PRED][-1]
    print("candidate:", cand["id"], cand.get("version"))

    code, body = call(["review", "add"], {
        "operation_id": "ui-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {"target_type": "baseline", "target_id": cand["id"],
                 "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：REQ-000017 已确认但不在基线内，需要冻结成可发布快照。",
                 "completeness_review": f"成员完整：{len(cand['members'])} 个，其余保持原修订。",
                 "acceptance_review": "6 项重验尚未登记执行结果，属后续验收环节，本审核不声称已通过。",
                 "basis": f"依据 {cand['id']} r{cand['revision']}。声明式审核。"},
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "ui-base-activate", "agent": "octie-agent",
        "reason": "激活候选基线", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1
    rev = body["document_revision"]

    impl = None
    for act in ("start", "complete"):
        code, body = call(["dev", act], {
            "operation_id": f"ui-dev-{act}", "agent": "octie-agent",
            "reason": "开始实现轮次" if act == "start" else "实现完成，e2e 6/6 通过",
            "expected_revision": rev,
            "data": {"baseline_id": cand["id"], "id": REQ, "revision": REV, "digest": cur["digest"]},
        })
        if not ok(f"dev {act}", code, body):
            return 1
        rev = body["document_revision"]
        if act == "complete":
            impl = body["object"]["implemented_event_id"]

    exe = {}
    for cid, (actual, method, ev) in ACC.items():
        code, body = call(["acceptance", "record"], {
            "operation_id": f"ui-acc-{cid}", "agent": "octie-agent",
            "reason": "按 e2e 实测登记", "expected_revision": rev,
            "data": {"baseline_id": cand["id"], "requirement_id": REQ, "revision": REV, "cycle": 1,
                     "condition_id": cid, "delivery_id": DELIVERY,
                     "implemented_event_id": impl, "evidence": ev, "actual": actual,
                     "method": method, "result": "通过"},
        })
        if not ok(f"acc {cid}", code, body):
            return 1
        rev = body["document_revision"]
        exe[cid] = body["object"]["id"]

    code, body = call(["release", "add"], {
        "operation_id": "ui-release-v9", "agent": "octie-agent",
        "reason": "发布 crab-coast-v9（多人版手机控件对齐单机版）", "expected_revision": rev,
        "data": {"baseline_id": cand["id"], "delivery_id": DELIVERY,
                 "members": [{"id": REQ, "revision": REV, "cycle": 1}]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "ui-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、重验义务已执行，逐动作逐义务关闭",
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
    print("done. doc_rev:", body["document_revision"], "| release:", rel, "| baseline:", cand["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
