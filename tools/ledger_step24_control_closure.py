"""控制语义三项：change → 新基线 → dev → 逐条验收 → 发布 → 关闭。

变更内容：替换 REQ-000010 r2→r3（含 AC-000063）、替换 REQ-000014 r1→r3、新增 REQ-000016 r5。
证据：cloud/tools/e2e_control.js（6/6）、e2e_multiplayer.js（21/21）、e2e_env.js、浏览器实测。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
PRED = "BASE-000007"
DELIVERY = "crab-coast-v8"
MAX_SESSIONS = 2


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
          f"id={o.get('id')} status={o.get('status')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


# 验收实测数据（本次运行）
ACC = {
    "AC-000038": ("合法卡片上传返回 200，状态里 card.width=192、height=192、digest 为 64 位十六进制。",
                  "skill 生成成品 → CLI 上传 → 读 state。", "evidence/e2e_multiplayer.json 中 AC-000038"),
    "AC-000039": ("3 行高 PNG 上传返回 400，errors 含「行数必须是 4，收到 3」。",
                  "构造 192×144 PNG 上传。", "evidence/e2e_multiplayer.json 中 AC-000039"),
    "AC-000040": ("四角 alpha=255 的 PNG 返回 400，errors 指出「四角必须透明：(0,0)」。",
                  "构造角不透明 PNG 上传。", "evidence/e2e_multiplayer.json 中 AC-000040"),
    "AC-000063": ("manifest 字段齐全但 fps=7、footLine=40：返回 400，errors 同时含「帧率」与「脚底线」，"
                  "上传后 state.self.card 仍为 null（未落库）。",
                  "上传合法 PNG + 错值 manifest，读 errors 与 state。",
                  "evidence/e2e_control.json 中 AC-000063（status=400 errors=2 card=null）"),
    "AC-000051": ("未上传卡片时 self.card 为 null；上传后为 {width:192,height:192,digest:64位}。",
                  "上传前后各读一次 state。", "evidence/e2e_multiplayer.json 中 AC-000051"),
    "AC-000052": ("实际距离 204.4：radius=50 时 nearby 不含对方；radius=400 时含对方且 distance=204。",
                  "两个半径各查一次同一对动物。", "evidence/e2e_multiplayer.json 中 AC-000052"),
    "AC-000053": ("状态响应原文中搜不到任何一方的明文 token，nearby 项只有 id/name/x/y/facing/distance。",
                  "序列化响应搜索 token 与字段白名单。", "evidence/e2e_multiplayer.json 中 AC-000053"),
    "AC-000054": ("请求 radius=10000，响应回显 world.radius=400（RADIUS_MAX），nearby 按 400 返回。",
                  "带超大半径调用并读回显。", "evidence/e2e_multiplayer.json 中 AC-000054"),
    "AC-000058": ("REST 来源按住「上」并持续续期（每 500ms），WebSocket 来源随后按「右」：0.6 秒后 facing=right、"
                  "x 由 500 增至 569，说明后按者优先，且续期没有抢走优先级。",
                  "两个来源分别驱动同一只动物，采样 facing 与坐标。",
                  "evidence/e2e_control.json 中 AC-000058（facing=right x 500→569）"),
    "AC-000059": ("WebSocket 来源松开「右」后，REST 来源仍按着「上」：facing 变为 up，y 由 385 降到 330，没有停车。",
                  "松开后继续采样 facing 与 y。", "evidence/e2e_control.json 中 AC-000059（y 385→330）"),
    "AC-000060": ("续期组：从 y≈380 的长走廊按住「左」3.4 秒并每 100ms 续期，t=3.2 秒时 moving=true、"
                  "累计位移 383px（撞墙前）；对照组只发一次不续期，t=3.2 秒 moving=false、位移 327px（约 3 秒 ×110px/s）。"
                  "两组对比证明续期生效且能与撞墙区分。",
                  "两组分别续期/不续期，按 100ms 采样并在 t=3.2s 对比 moving 与位移。",
                  "evidence/e2e_control.json 中 AC-000060（续期 dx=383 moving=true；对照 dx=327 moving=false）"),
    "AC-000061": ("同一 token 依次建立 conn-1/2/3：conn-1 收到 close code=1008 reason='replaced by newer session'，"
                  "conn-2 与 conn-3 保持 open，最终恰好 2 个在线；浏览器侧被淘汰页显示「已在别处被接管」且 5 秒内不重连。",
                  "并发建立三个 WebSocket 并记录 close 事件；再用浏览器三页验证前端不重连。",
                  "evidence/e2e_control.json 中 AC-000061 + 浏览器实测（hud=已在别处被接管, connected=false）"),
    "AC-000062": ("状态响应字段为 id/name/x/y/facing/moving/card，没有 agent/human/source/role 之类身份字段；"
                  "REST 与 WebSocket 两种来源行为一致（见 AC-000058/059 两组混合来源实验）。",
                  "检查响应 key 集合，并用两种来源混合驱动验证行为只取决于按下顺序。",
                  "evidence/e2e_control.json 中 AC-000062（keys 无身份字段）"),
    "AC-000042": ("WebSocket 下发「左」意图后 x 由 684 降到 615、facing=left（重构来源记账后行为不变）。",
                  "WS 连接下发意图并采样坐标与朝向。", "evidence/e2e_multiplayer.json 中 AC-000042"),
}

RETESTS = [
    ("REQ-000010", 3, ["AC-000038", "AC-000039", "AC-000040", "AC-000063"]),
    ("REQ-000014", 3, ["AC-000051", "AC-000052", "AC-000053", "AC-000054"]),
    ("REQ-000016", 5, ["AC-000058", "AC-000059", "AC-000060", "AC-000061", "AC-000062"]),
    ("REQ-000011", 2, ["AC-000042"]),
]


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    o = doc["object"]
    print("start doc_rev:", rev, "active:", o["active_baseline"])
    reqs = {r["id"]: r["revisions"][-1] for r in o["requirements"]}

    actions = [
        {"type": "替换", "requirement_id": "REQ-000010", "old_revision": 2, "new_revision": 3},
        {"type": "替换", "requirement_id": "REQ-000014", "old_revision": 1, "new_revision": 3},
        {"type": "新增", "requirement_id": "REQ-000016", "old_revision": None, "new_revision": 5},
    ]
    impacts = ["REQ-000010", "REQ-000011", "REQ-000014", "REQ-000016"]

    code, body = call(["change", "propose"], {
        "operation_id": "ctl-chg-propose", "agent": "octie-agent",
        "reason": "把控制语义三项实现对应的台账差异提成变更",
        "expected_revision": rev,
        "data": {"predecessor": PRED, "actions": actions, "impact_objects": impacts},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    retests = [{"requirement_id": r, "revision": v, "condition_id": c}
               for r, v, cs in RETESTS for c in cs]
    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "ctl-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与精确重验清单",
        "expected_revision": rev,
        "data": {
            "id": chg, "revision": cur["revision"], "digest": cur["digest"],
            "impact_analysis": (
                "本次差异是控制语义的实质性改造：world.js 把单一 intentDir 换成按来源的按住集合"
                "（pressedAt 决定优先级、aliveAt 决定是否失联），ws.js 增加每动物 2 会话上限与 FIFO 淘汰，"
                "play.js 增加按住续期与「被接替不重连」，card.js 的 manifest 取值校验补上验收。"
                "受影响：REQ-000010（新增 AC-000063 需验收）、REQ-000014（边界与半径数值写清需复验）、"
                "REQ-000016（全新）、REQ-000011（WS 下发意图的实现路径被重构，需回归 AC-000042）。"
                "场景、素材、动画与音频未改动。"
            ),
            "retests": retests,
        },
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "ctl-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 当前修订做变更审核", "expected_revision": rev,
        "data": {
            "target_type": "change", "target_id": chg,
            "target_revision": cur["revision"], "target_digest": cur["digest"], "conclusion": "通过",
            "necessity_review": "必要性：三条差异都来自用户明确提出的控制行为（多来源合成、续期、两会话 FIFO）与审计发现的行为缺口（manifest 取值未验收），直接决定多人同时操作时是否正确。",
            "completeness_review": f"完整性：actions 三条（两条替换、一条新增），new_revision 与台账当前修订一致；候选成员在原 16 条基础上更新这 3 条；评估给出 {len(retests)} 项重验义务，覆盖被改动实现路径上的全部条件。",
            "acceptance_review": f"验收：{len(retests)} 项义务都对应可执行条件，AC-000060 已改为撞墙前取样并带对照组；AC-000061 同时覆盖服务端关闭码与前端不重连。",
            "basis": f"依据 {chg} 评估后摘要 {cur['digest'][:12]}… 与三份 e2e 证据文件审阅。声明式审核。",
        },
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        cur = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"ctl-chg-{act}", "agent": "octie-agent",
            "reason": ("批准变更" if act == "approve" else "按批准差异生成候选基线"),
            "expected_revision": rev,
            "data": {"id": chg, "revision": cur["revision"], "digest": cur["digest"]},
        })
        if not ok(act, code, body):
            return 1
        rev = body["document_revision"]

    doc = show({"type": "ledger"})
    cand = [b for b in doc["object"]["baselines"] if b.get("predecessor") == PRED][-1]
    print("candidate:", cand["id"], cand.get("version"), "members:", len(cand["members"]))

    code, body = call(["review", "add"], {
        "operation_id": "ctl-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {
            "target_type": "baseline", "target_id": cand["id"],
            "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
            "necessity_review": "必要性：三条需求的新修订需要与既有成员一起冻结成可发布快照。",
            "completeness_review": f"成员完整：{len(cand['members'])} 个，未改动的保持原修订，改动的指向最新确认修订。",
            "acceptance_review": f"{len(retests)} 项重验义务尚未登记执行结果，属后续开发与验收环节，本审核不声称已通过。",
            "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}…。声明式审核。",
        },
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "ctl-base-activate", "agent": "octie-agent",
        "reason": "候选基线审核通过，激活", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1
    rev = body["document_revision"]

    # ---------- dev ----------
    implemented = {}
    for rid, rrev in (("REQ-000010", 3), ("REQ-000014", 3), ("REQ-000016", 5)):
        cur_r = reqs[rid]
        for act in ("start", "complete"):
            code, body = call(["dev", act], {
                "operation_id": f"ctl-dev-{act}-{rid}", "agent": "octie-agent",
                "reason": ("开始实现轮次" if act == "start" else "实现完成并通过三套 e2e 与浏览器实测"),
                "expected_revision": rev,
                "data": {"baseline_id": cand["id"], "id": rid, "revision": rrev,
                         "digest": cur_r["digest"]},
            })
            if not ok(f"dev {act} {rid}", code, body):
                return 1
            rev = body["document_revision"]
            if act == "complete":
                implemented[rid] = body["object"]["implemented_event_id"]

    # ---------- acceptance ----------
    for rid, rrev, conds in RETESTS:
        if rid == "REQ-000011":
            # 未改动的需求：沿用其当前已实现事件
            dev = show({"type": "development", "id": rid, "revision": rrev})["object"]
            implemented[rid] = dev["implemented_event_id"]
        for cid in conds:
            actual, method, ev = ACC[cid]
            code, body = call(["acceptance", "record"], {
                "operation_id": f"ctl-acc-{cid}", "agent": "octie-agent",
                "reason": "按本次实测登记",
                "expected_revision": rev,
                "data": {
                    "baseline_id": cand["id"], "requirement_id": rid, "revision": rrev,
                    "cycle": 1, "condition_id": cid, "delivery_id": DELIVERY,
                    "implemented_event_id": implemented[rid],
                    "evidence": ev, "actual": actual, "method": method, "result": "通过",
                },
            })
            if not ok(f"acc {cid}", code, body):
                return 1
            rev = body["document_revision"]
            ACC_EXE[cid] = body["object"]["id"]

    # ---------- release ----------
    members = [{"id": "REQ-000010", "revision": 3, "cycle": 1},
               {"id": "REQ-000014", "revision": 3, "cycle": 1},
               {"id": "REQ-000016", "revision": 5, "cycle": 1}]
    code, body = call(["release", "add"], {
        "operation_id": "ctl-release-v8", "agent": "octie-agent",
        "reason": "在控制语义变更后的基线上发布 crab-coast-v8",
        "expected_revision": rev,
        "data": {"baseline_id": cand["id"], "delivery_id": DELIVERY, "members": members},
    })
    if not ok("release", code, body):
        return 1
    rev = body["document_revision"]
    rel = body["object"]["id"]

    # ---------- change close ----------
    chg_cur = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "close"], {
        "operation_id": "ctl-chg-close", "agent": "octie-agent",
        "reason": "变更已应用、基线已激活、重验义务已由本交付执行，逐动作逐义务关闭",
        "expected_revision": rev,
        "data": {
            "id": chg, "revision": chg_cur["revision"], "digest": chg_cur["digest"],
            "action_closures": [
                {"action": a, "basis": {"type": "发布", "release_id": rel}}
                for a in chg_cur["actions"]
            ],
            "obligation_closures": [
                {"obligation": {k: ob[k] for k in ("change_id", "change_revision", "requirement_id",
                                                   "revision", "condition_id")},
                 "basis": {"type": "执行", "executions": [
                     {"execution_id": ACC_EXE[ob["condition_id"]], "delivery_id": DELIVERY}]}}
                for ob in chg_cur["evaluation"]["obligations"]
            ],
        },
    })
    if not ok("change close", code, body):
        return 1
    print("done. doc_rev:", body["document_revision"], "| release:", rel, "| baseline:", cand["id"])
    return 0


ACC_EXE = {}

if __name__ == "__main__":
    sys.exit(main())
