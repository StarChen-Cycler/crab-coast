"""相机裁切视角闭环（REQ-000018 新增 + REQ-000017 r2 措辞修正）。

阶段：修订 → 提交 → 审核 → 确认 → 变更(propose/evaluate/review/approve/apply)
      → 候选基线审核与激活 → dev → 12 条验收 → 发布 crab-coast-v10 → 变更关闭。

实测来源：evidence/camera.json（AC-000070…075）、evidence/touch_ui.json（AC-000064…069）。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
DELIVERY = "crab-coast-v10"
AC_FIELDS = ("allow_na", "evidence", "exception", "expected", "input", "method", "operation",
             "preconditions", "role", "scenario")

R17, R17_REV = "REQ-000017", 2
R18, R18_REV = "REQ-000018", 2


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
        print("    raw:", (body.get("_raw") or "")[:600])
    return good


def current(rid):
    doc = show({"type": "ledger"})
    cur = [r for r in doc["object"]["requirements"] if r["id"] == rid][0]["revisions"][-1]
    return doc["document_revision"], cur


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


def revise(rid, mutate, tag, why, reviews):
    """修订 + submit + review + confirm 一条需求，返回 (新修订号, digest, doc_rev)。"""
    rev, cur = current(rid)
    data = {k: cur[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                                "priority", "placement", "included", "excluded", "normal_behavior",
                                "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in cur["sources"]]
    data["acceptance"] = [{**{k: a[k] for k in AC_FIELDS}, "id": a["id"]} for a in cur["acceptance"]]
    mutate(data)
    data["id"] = rid
    data["base_revision"] = cur["revision"]
    code, body = call(["req", "revise"], {"operation_id": f"cam-{tag}-revise", "agent": "octie-agent",
                                          "reason": why, "expected_revision": rev, "data": data})
    if not ok(f"revise {rid}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]
    for args, agent, reason in ((["req", "submit"], "octie-agent", "修订转入待审核"),
                                (["review", "add"], "review-agent", "修订审核"),
                                (["req", "confirm"], "octie-agent", "确认纳入")):
        if args[1] == "add":
            d2 = {"target_type": "requirement", "target_id": rid, "target_revision": rrev,
                  "target_digest": digest, "conclusion": "通过"}
            d2.update(reviews)
        elif args[1] == "submit":
            d2 = {"id": rid, "revision": rrev, "digest": digest}
        else:
            d2 = {"id": rid, "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}}
        code, body = call(args, {"operation_id": f"cam-{tag}-{args[1]}", "agent": agent,
                                 "reason": reason, "expected_revision": rev, "data": d2})
        if not ok(f"{rid} {args[1]}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    return rrev, digest, rev


# ---------------- 修订内容 ----------------
def mutate_17(data):
    for a in data["acceptance"]:
        if a["id"] == "AC-000069":
            a["expected"] = ("横屏开关落在顶部一行内（top ≤60）且水平居中（中心与视口中心偏差 ≤24px），"
                             "与自身/附近/连接三个 HUD 以及四键零重叠；矮屏 ABXY 缩放 0.78 不越界；"
                             "桌面不显示控件但键盘仍能移动动物")
            a["exception"]["scenario"] = "横屏开关压住 HUD 或按键"
            a["exception"]["handling"] = "把开关放在顶部居中（两侧顶角已被 HUD 占用）"
    data["technical"] = (data["technical"].rstrip() +
                         " 横屏时开关改为顶部居中（左/右顶角已被 HUD 占用，实测压字后调整）。")


def mutate_18(data):
    for a in data["acceptance"]:
        if a["id"] == "AC-000070":
            a["expected"] = ("未被钳制且视野小于世界的轴上，动物屏幕坐标与画布中心偏差 ≤2px；"
                             "背景与其它动物按相反方向平移相同距离（±2px）。视野 ≥ 世界的轴按 AC-000075 映射")
    data["acceptance"].append(ac(
        "前端验收者", "视野大于世界时整幅居中", "视口 1400x1000（视野 1400x1000 > 世界 960x540）",
        "按住方向键走 1 秒", "读相机坐标、可见世界范围与留白，并对比走动前后",
        "相机固定为 (0,0)、可见范围 = 世界 960x540、留白 = (画布-世界)/2；动物屏幕坐标 = 世界坐标 + 留白，走动时画面不平移",
        ("相机跟着动物跑或世界没居中", "判定视野大于世界时缺少居中分支", "相机尺寸超过世界时取世界尺寸并把留白居中"),
        "CDP 读 camera 与 worldToScreen 并与画布尺寸对比", "evidence/camera.json 中「视野大于世界」断言"))
    data["included"] = data["included"] + ["视野大于世界时整幅世界居中、相机不再移动"]
    data["boundaries"] = data["boundaries"] + [
        {"scenario": "相机在某一轴已顶到世界边界", "expected": "该轴不再跟随，另一轴照常跟随",
         "handling": "两轴各自独立钳制"}]
    data["technical"] = (data["technical"].rstrip() +
                         " fit() 只设 camera.w/h，可见范围 vw/vh = min(画布, 世界)，留白 ox/oy = (画布-可见)/2；"
                         "worldToScreen() 与背景 drawImage 共用同一份整数取整。")


REV17 = {
    "necessity_review": "必要性不变：手机端控件的可用性依赖横屏不遮挡。",
    "completeness_review": "完整性：只改 AC-000069 的 expected 与异常项（旧措辞「开关在左半屏」与实际实现不符，且左半屏必与自身 HUD 重叠）；其余 5 条与所有字段未变。",
    "acceptance_review": "验收：AC-000069 改为「顶部一行 + 与 HUD/四键零重叠」这种可测量、且不与 HUD 布局冲突的判据，仍由 e2e_touch_ui.js 在三档视口断言。",
    "basis": "依据 REQ-000017 第 2 修订与 evidence/touch_ui.json 实测开关矩形 l=378 r=466 t=16（844x390 顶部居中）。声明式审核。",
}

REV18 = {
    "necessity_review": "必要性：1:1 相机裁切是手机端「看得清 + 看见身边人」的唯一做法，新增的 6 条把边界语义也纳入验收。",
    "completeness_review": "完整性：6 条条件覆盖居中跟随、平移一致、左/上钳制、右/下钳制、可见⊆已收到、视野大于世界居中、Agent 半径不变；纳入 6 条、排除 3 条、边界 5 条。",
    "acceptance_review": "验收：6 条全部由 e2e_camera.js 自动断言（15 项断言，含纯函数分支），condition 映射写入 evidence/camera.json。",
    "basis": "依据 REQ-000018 第 2 修订与 evidence/camera.json 15/15 通过。声明式审核。",
}

# ---------------- 验收执行（全部来自实测） ----------------
ACC = [
    (R17, R17_REV, "AC-000064",
     "触屏 390x844 四向各 400ms：位移 +144/-106/-89/+96 px，facing 依次 right/left/up/down，松手 moving=false。",
     "CDP 驱动页面合成 TouchEvent，读服务端快照比对坐标与朝向。", "evidence/touch_ui.json 中 AC-000064"),
    (R17, R17_REV, "AC-000065",
     "推杆到 (4,3)（5px < 死区 10px）保持 400ms：坐标位移 0,0。",
     "同类合成事件 + 前后坐标对比。", "evidence/touch_ui.json 中 AC-000065"),
    (R17, R17_REV, "AC-000066",
     "依次按 Y/X/B/A：坐标与 facing 无变化，四键 disabled=true。",
     "合成 touchstart 后读快照与 DOM 属性。", "evidence/touch_ui.json 中 AC-000066"),
    (R17, R17_REV, "AC-000067",
     "点收起：摇杆/ABXY display=none、开关可见、--touch-band 0px、画布高度 608→844（补回操作带）；再点恢复为 block / 236px / 608。",
     "点击开关并读取计算样式与画布矩形（相机裁切后画布 top 恒为 0，重算表现为高度变化）。",
     "evidence/touch_ui.json 中 AC-000067"),
    (R17, R17_REV, "AC-000068",
     "390x844：全部控件在视口内；摇杆/ABXY/开关/三个 HUD 两两不相交；画布 (0,0)-(390,608) 底边距操作带 0px 重叠。",
     "逐对矩形相交检测 + 画布与操作带间距计算。", "evidence/touch_ui.json 中 AC-000068"),
    (R17, R17_REV, "AC-000069",
     "844x390：开关矩形 l=378 r=466 t=16（中心 422 = 视口中心 422，偏差 0）与自身/附近/连接 HUD 及四键零重叠；"
     "844x260 矮屏不越界不重叠；桌面 900x560 不挂载控件但方向键使 x 625→659。",
     "三档视口读矩形与可见性；桌面派发 KeyboardEvent 后读坐标。", "evidence/touch_ui.json 中 AC-000069"),
    (R18, R18_REV, "AC-000070",
     "390x844：位图 390x608 = 相机窗口 = CSS 尺寸，画布贴 (0,0)；水平居中 screen.x=195 = 画布中心，偏差 0.00px（cam.x=427 未钳制）；"
     "向右 1.2s：世界位移 122px、相机位移 122px、屏幕坐标变化 0px；"
     "900x300：双轴未钳制时 screen=(450,150) = 中心，偏差 (0,0)；纯函数 cameraTarget(480,270,900x300)=(30,120) 把中心放在画布中心。",
     "CDP 读 __play.camera / worldToScreen（与绘制同一份实现），对比前后快照和服务端位置。",
     "evidence/camera.json 中 AC-000070"),
    (R18, R18_REV, "AC-000071",
     "900x300 持续向左 2.5s：cam.x 50→0 并停住，动物屏幕 x 450→232（-218px，继续减小）；"
     "纯函数：self=(0,0) 时相机 = (0,0)。世界上边界 195px 内无可走地块（可走区 y 最小约 318），上边界用同一份纯函数断言。",
     "读相机与屏幕坐标；边界不可达的一侧用 cameraTarget 纯函数验证。", "evidence/camera.json 中 AC-000071"),
    (R18, R18_REV, "AC-000072",
     "900x300 持续向右 4s：cam.x 停在 60 = 960-900，屏幕 x 232→540（+308px）；"
     "持续向下 2s：cam.y 停在 240 = 540-300，屏幕 y 150→282（+132px）；纯函数 self=(960,540) → 相机 (60,240)。",
     "读相机与屏幕坐标；右下角另用 cameraTarget 断言。", "evidence/camera.json 中 AC-000072"),
    (R18, R18_REV, "AC-000073",
     "390x844：握手半径 386 = ceil(半对角 362)+24，服务端回显 386（未触发 RADIUS_MAX）；"
     "另一只动物世界 (500,412) 映射到屏幕 (73,446) 落在视野内，它同时出现在 nearby 与 drawn 里，绘制集合减去 nearby 的缺失数 = 0。",
     "服务端快照 nearby/drawn 集合比对 + 用参照动物的 REST 状态独立判断「是否在视野内」。",
     "evidence/camera.json 中 AC-000073"),
    (R18, R18_REV, "AC-000074",
     "GET /animals/me/state → world.radius=200；?radius=10000 → 400（RADIUS_MAX 钳制）。与相机半径请求（386/400）互不影响。",
     "REST 两次调用读 world.radius。", "evidence/camera.json 中 AC-000074"),
    (R18, R18_REV, "AC-000075",
     "1400x1000：cam=(0,0)、可见范围 960x540、留白 ox=220 oy=(1000-540)/2=230；走动 110px 期间 cam 始终 (0,0)，"
     "screen.x = self.x + 220（偏差 ≤2px）；纯函数 self=(480,270) → 相机 (0,0) 留白 (220,230)。",
     "CDP 读相机/可见范围/留白，走动前后对比；纯函数验证分支。", "evidence/camera.json 中 AC-000075"),
]


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    pred = doc["object"]["active_baseline"]
    print("start doc_rev:", rev, "active:", pred)

    r17_rev, r17_digest, rev = revise(R17, mutate_17, "17r2",
                                      "横屏开关措辞改为「顶部一行居中且不压 HUD/按键」", REV17)
    print(R17, "->r", r17_rev, r17_digest[:12])
    r18_rev, r18_digest, rev = revise(R18, mutate_18, "18r2",
                                      "补「视野大于世界整幅居中」条件并明确居中判据的轴", REV18)
    print(R18, "->r", r18_rev, r18_digest[:12])

    actions = [{"type": "替换", "requirement_id": R17, "old_revision": 1, "new_revision": r17_rev},
               {"type": "新增", "requirement_id": R18, "old_revision": None, "new_revision": r18_rev}]
    retests = [{"requirement_id": rid, "revision": rv, "condition_id": cid} for rid, rv, cid, *_ in ACC]

    code, body = call(["change", "propose"], {
        "operation_id": "cam-chg-propose", "agent": "octie-agent",
        "reason": "纳入相机裁切视角（REQ-000018）并修正 REQ-000017 的横屏开关判据",
        "expected_revision": rev,
        "data": {"predecessor": pred, "actions": actions, "impact_objects": [R17, R18]},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "cam-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与重验清单", "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "impact_analysis": (
                     "本次变更两处：①新增 REQ-000018（play/play.js 相机裁切 + worldToScreen、play/index.html "
                     "画布贴视口、ws.js 握手支持 r= 半径、play.js 按视野半对角请求半径），服务端位置权威、"
                     "卡片管线、CLI/技能、单机版均未改动；②REQ-000017 只改 AC-000069 的措辞（旧文字要求"
                     "「开关在左半屏」，与 HUD 布局冲突，实际实现改为顶部居中），实现代码未再改动。"
                     "因此重验范围 = REQ-000018 全 6 条 + REQ-000017 全 6 条（该条被替换，按规则整套重验）。"),
                 "retests": retests},
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "cam-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 做变更审核", "expected_revision": rev,
        "data": {"target_type": "change", "target_id": chg,
                 "target_revision": ch["revision"], "target_digest": ch["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：手机端整幅渲染把 48px 角色压到约 20px，且按半径裁剪会在全图上留下凭空出现/消失的可见边界；相机裁切同时解决两者。REQ-000017 的措辞与 HUD 布局自相矛盾，必须改正。",
                 "completeness_review": f"完整性：两条动作（替换 REQ-000017 r1→r{r17_rev}、新增 REQ-000018 r{r18_rev}）；候选成员 = 原基线成员 + 这两条，其余保持原修订；{len(retests)} 项重验逐条对应条件 ID。",
                 "acceptance_review": "验收：12 项重验由 e2e_camera.js（15 项断言）与 e2e_touch_ui.js（6 项断言）实测覆盖，证据文件带 condition 映射；本审核不声称已执行。",
                 "basis": f"依据 {chg} 评估后摘要 {ch['digest'][:12]}… 与两台 e2e 的实测结果。声明式审核，Agent 身份仅作操作归因。"},
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        ch = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"cam-chg-{act}", "agent": "octie-agent",
            "reason": "批准变更" if act == "approve" else "生成候选基线（不自动激活）",
            "expected_revision": rev,
            "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"]},
        })
        if not ok(act, code, body):
            return 1
        rev = body["document_revision"]

    doc = show({"type": "ledger"})
    cand = [b for b in doc["object"]["baselines"] if b.get("predecessor") == pred][-1]
    print("candidate:", cand["id"], cand.get("version"), "members:", len(cand["members"]))

    code, body = call(["review", "add"], {
        "operation_id": "cam-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {"target_type": "baseline", "target_id": cand["id"],
                 "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：相机裁切与横屏判据修正需要与既有成员一起冻结成可发布快照。",
                 "completeness_review": f"成员完整：{len(cand['members'])} 个，前驱为当前有效基线 {pred}，其余成员保持原修订。",
                 "acceptance_review": f"{len(retests)} 项重验尚未登记执行结果，属后续验收环节，本审核不声称其已通过。",
                 "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}…。声明式审核。"},
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "cam-base-activate", "agent": "octie-agent",
        "reason": "候选基线已审核通过，激活为当前有效基线", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1
    rev = body["document_revision"]

    impl = {}
    for rid, rv, digest in ((R17, r17_rev, r17_digest), (R18, r18_rev, r18_digest)):
        for act in ("start", "complete"):
            code, body = call(["dev", act], {
                "operation_id": f"cam-dev-{rid}-{act}", "agent": "octie-agent",
                "reason": "开始实现轮次" if act == "start" else "实现完成，两台 e2e 全 PASS",
                "expected_revision": rev,
                "data": {"baseline_id": cand["id"], "id": rid, "revision": rv, "digest": digest},
            })
            if not ok(f"dev {rid} {act}", code, body):
                return 1
            rev = body["document_revision"]
            if act == "complete":
                impl[rid] = body["object"]["implemented_event_id"]

    exe = {}
    for rid, rv, cid, actual, method, ev in ACC:
        code, body = call(["acceptance", "record"], {
            "operation_id": f"cam-acc-{cid}", "agent": "octie-agent",
            "reason": "按 e2e 实测登记该条件的验收结果", "expected_revision": rev,
            "data": {"baseline_id": cand["id"], "requirement_id": rid, "revision": rv, "cycle": 1,
                     "condition_id": cid, "delivery_id": DELIVERY,
                     "implemented_event_id": impl[rid], "evidence": ev, "actual": actual,
                     "method": method, "result": "通过"},
        })
        if not ok(f"acc {cid}", code, body):
            return 1
        rev = body["document_revision"]
        exe[cid] = body["object"]["id"]

    code, body = call(["release", "add"], {
        "operation_id": "cam-release-v10", "agent": "octie-agent",
        "reason": "发布 crab-coast-v10（手机端相机裁切视角）", "expected_revision": rev,
        "data": {"baseline_id": cand["id"], "delivery_id": DELIVERY,
                 "members": [{"id": R17, "revision": r17_rev, "cycle": 1},
                             {"id": R18, "revision": r18_rev, "cycle": 1}]},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "cam-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、12 项重验义务已逐条登记执行结果",
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
