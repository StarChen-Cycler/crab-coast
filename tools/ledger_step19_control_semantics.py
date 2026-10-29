"""2026-10-29 用户澄清：控制指令合成 / 会话上限 / nearby 边界确认。

只登记需求（草稿 → 审核 → 确认），**不做 change/baseline/dev**（用户要求先汇报）。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"


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
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:800])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


SOURCE = {
    "kind": "用户消息",
    "name": "用户澄清控制指令合成、会话上限与 nearby 边界",
    "date_note": "2026-10-29 用户消息",
    "quote": "这个活跃的 WebSocket 会话应该最多有两个：一个是 Agent，另一个是人在浏览器里面浏览时，他自己也可以直接上手操控。Agent 传过去的只有\"向上\"这个动作的指令，它并不会影响用户的动作。如果 Agent 和用户的动作同时传的话……我在电脑上本来按着\"向上\"的按键，同时又点了\"向右\"的按键，那后面这个\"向右\"的按键优先级是更高的。如果持续按着\"向上\"的按键，它应该是没有作用的；但是如果我松开\"向右\"的按键，继续按\"向上\"，这个依然有用。……1. 服务端分辨不了 Agent 和人的指令就对了。……3. 上线前的这个多人版的 nearby，只给其他动物是没问题的，不含环境层，我觉得合理啊。",
    "summary": "用户确认三点：① 服务端不需要区分指令来自 Agent 还是人；② 同一动物最多两个活跃会话（Agent + 浏览器），两路指令按「最近按下优先」，松开后回落到仍按住的那一路；③ nearby 只给其它动物、不含环境层，这个边界合理。",
    "manual_note": "用户在会话中以文字直接提出，未经整理",
}

REQ16 = {
    "title": "多来源移动指令按最近按下优先合成，每只动物最多两个活跃会话",
    "type": "功能", "module": "服务端世界", "priority": "P1",
    "placement": {"kind": "全局", "reason": "服务端的输入合成与会话上限，不属于任何页面区域"},
    "sources": [{"source_id": "SRC-000005", "source_revision": 1}],
    "questions": [],
    "description": "同一只动物可以同时被多个来源控制（典型是 Agent 一个 WebSocket 会话 + 人在浏览器里一个会话）。服务端**不区分**来源是 Agent 还是人，只按连接（或带 token 的调用方）分别记账：每个来源各自维护「当前按住的方向」，动物的实际方向取「最近按下且仍未松开」的那一个。按住 A 再按下 B 时 B 生效；松开 B 后若 A 仍按着就回落到 A；都松开则停车。按住期间客户端周期性续期，使「3 秒无更新即停车」只作用于真正失联的来源。同一只动物最多允许 2 个活跃 WebSocket 会话，第 3 个被拒绝并说明原因。",
    "purpose": "让 Agent 的自动控制和人的手动操作能同时存在且互不打架，松开一个键能自然回到另一个仍按着的方向。",
    "necessity": "按现在的实现，任何一路发「松开」都会把整只动物置为停车，于是 Agent 按住「上」时人一松「右」，动物就停住而不是回到「上」；而且按住超过 3 秒会被 TTL 判为失联而停住。不把这条规则写清楚，两人同时操作时的行为无法验收。",
    "included": [
        "每个来源独立的「按住方向」记账，服务端不区分 Agent 与人",
        "有效方向 = 最近按下且仍未松开的那一个",
        "松开后回落到其它仍按住的方向；全部松开则停车",
        "按住期间客户端周期性续期，3 秒 TTL 只作用于失联来源",
        "每只动物最多 2 个活跃 WebSocket 会话，超出被拒绝",
    ],
    "excluded": [
        "按来源身份设定优先级（例如 Agent 永远高于人）",
        "多方向矢量叠加或斜向移动",
        "来源之间的抢占锁与强制接管",
    ],
    "normal_behavior": {
        "scenario": "Agent 持续按住「上」（周期性续期），人随后在浏览器按下「右」再松开",
        "behavior": "服务端记录两个来源各自的按住项，按最近按下者决定有效方向",
        "expected": "人按下「右」时动物向右移动；人松开「右」后，因为 Agent 仍按着「上」，动物立即回向上移动，而不是停车",
    },
    "boundaries": [
        {"scenario": "同一来源连续按下多个方向", "expected": "以最后按下且未松开的那个为准", "handling": "该来源的按住集合按时间戳取最新"},
        {"scenario": "两个来源按住同一方向后其中一个松开", "expected": "仍按着的那一方继续生效，不中断移动", "handling": "松开只移除该来源自己的记录"},
        {"scenario": "第 3 个 WebSocket 尝试连接同一只动物", "expected": "被拒绝并说明最多两个会话", "handling": "握手阶段返回明确原因，不影响已有两个会话"},
        {"scenario": "某个来源失联、不再续期", "expected": "3 秒后该来源的按住项失效，回落到其它来源", "handling": "按住项带时间戳，超时即视为松开"},
    ],
    "acceptance": [
        ac("控制验收者", "两路同时操作时后按的优先", "两只来源都持有有效 token，动物在开阔沙地",
           "来源甲按住「上」并持续续期；来源乙随后按下「右」", "观察 1 秒内动物的移动方向与 facing",
           "动物向右移动（x 增大），facing 为 right；来源甲的「上」仍在按住状态",
           ("动物不动、或仍向上", "判定最近按下优先未生效", "检查按住项的时间戳比较与有效方向计算"),
           "两个客户端分别驱动，采样位置与 facing", "两段位移轨迹 + facing 记录"),
        ac("控制验收者", "松开后回落到仍按住的方向", "承接上一条：来源甲仍按着「上」，来源乙按着「右」",
           "来源乙松开「右」", "观察松开后 1 秒内的移动方向",
           "动物立即由向右改为向上（y 减小），不停车，也不需要来源甲重新发指令",
           ("动物停住或朝其它方向", "判定回退逻辑缺失", "检查松开是否只移除本来源记录并重算有效方向"),
           "记录松开前后各 1 秒的位移向量", "松开前后位置采样"),
        ac("控制验收者", "按住超过 3 秒不失效", "单一来源按住「上」",
           "客户端每 1 秒续期一次，持续 6 秒", "统计 6 秒内的累计位移与 moving",
           "6 秒内移动持续（累计约 600–720px 若有空间），期间 moving 始终为 true，没有因 TTL 停车",
           ("约 3 秒后停下", "判定续期未生效或 TTL 未被续期刷新", "检查续期请求是否走同一按住项"),
           "按 1 秒间隔续期并采样位置", "位置序列与 moving 标记"),
        ac("控制验收者", "第三个会话被拒", "已有一只动物的两个活跃 WebSocket 会话",
           "用同一 token 建立第 3 个 WebSocket", "记录握手结果与既有会话状态",
           "第 3 个连接被拒绝并给出「最多两个会话」的原因；前两个会话继续正常收快照",
           ("第 3 个连接成功", "判定会话上限未生效", "在握手阶段统计该动物的活跃连接数"),
           "并发建立三个连接并观察", "三次握手结果 + 前两个会话的快照计数"),
        ac("控制验收者", "服务端不区分来源身份", "两个来源分别是 REST 调用与 WebSocket 会话",
           "两路分别按住不同方向并交替松开", "检查接口响应与状态字段",
           "两条路径行为一致，响应与状态里没有任何 agent/human 之类的来源身份字段；行为只取决于按下顺序",
           ("出现按身份区分的优先级字段或行为", "判定引入了身份依赖", "移除身份相关分支"),
           "对比两种来源的响应结构与行为", "两路响应 json 与位移轨迹"),
    ],
    "technical": "world.js 里把单一 intentDir 换成 Map<sourceKey, {dir, at}>：WebSocket 用连接 id 作 sourceKey，REST 用 token 前缀的哈希作 sourceKey；有效方向 = at 最大且未过期（3 秒）的项；现有单来源行为是其退化情形。",
}


def lifecycle(rid=None, payload_data=None, label=""):
    """add 或 revise → submit → review → confirm；返回 (id, revision, digest, doc_rev)。"""
    rev = show({"type": "ledger"})["document_revision"]
    if rid is None:
        code, body = call(["req", "add"], {
            "operation_id": "ctl-req-add-16", "agent": "octie-agent",
            "reason": "登记多来源控制合成的完整需求草稿",
            "expected_revision": rev, "data": payload_data,
        })
        if not ok("req add REQ-000016", code, body):
            raise SystemExit(1)
    else:
        code, body = call(["req", "revise"], {
            "operation_id": f"ctl-req-revise-{rid}", "agent": "octie-agent",
            "reason": "把用户确认的边界写进需求",
            "expected_revision": rev, "data": payload_data,
        })
        if not ok(f"revise {rid}", code, body):
            raise SystemExit(1)
    rev = body["document_revision"]
    rid2, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]

    code, body = call(["req", "submit"], {
        "operation_id": f"ctl-submit-{rid2}-r{rrev}", "agent": "octie-agent",
        "reason": "草稿转入待审核", "expected_revision": rev,
        "data": {"id": rid2, "revision": rrev, "digest": digest},
    })
    if not ok(f"submit {rid2}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]

    code, body = call(["review", "add"], {
        "operation_id": f"ctl-review-{rid2}-r{rrev}", "agent": "review-agent",
        "reason": f"对 {rid2} 第 {rrev} 修订做语义审核", "expected_revision": rev,
        "data": {
            "target_type": "requirement", "target_id": rid2,
            "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
            "necessity_review": ("必要性：现有实现只有单一 intentDir，任何一路松开都会停车，"
                                 "Agent 与人同时操作时无法回到仍按住的方向，按住超过 3 秒还会被 TTL 判为失联——"
                                 "用户已明确描述期望行为，必须写成可验收的规则。"
                                 if rid is None else
                                 "必要性不变：本次只把用户确认的边界写清楚，不改变需求实质。"),
            "completeness_review": ("完整性：15 类字段齐全；纳入 5 条、排除 3 条、边界 4 条（同源多键、两源同向、第 3 会话、来源失联）；"
                                    "全局归属给了 reason；来源 SRC-000005 r1；开放问题为空。"
                                    if rid is None else
                                    "完整性：字段齐全，改动仅在 included/technical 中补充「用户已确认不含环境层」，验收条件全部沿用原 ID 未变。"),
            "acceptance_review": ("验收：5 条条件分别覆盖「后按优先」「松开回落」「按住不失效」「第三会话被拒」「不区分来源身份」，"
                                  "均为可用两个客户端复现的可观察现象。"
                                  if rid is None else
                                  "验收：条件未变，仍覆盖原有五条，本次修订不放松任何验收要求。"),
            "basis": (f"依据 {rid2} 第 {rrev} 修订摘要 {digest[:12]}… 与来源 SRC-000005 r1 逐字段审阅。"
                      "声明式审核，Agent 身份仅作操作归因。"),
        },
    })
    if not ok(f"review {rid2}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]

    code, body = call(["req", "confirm"], {
        "operation_id": f"ctl-confirm-{rid2}-r{rrev}", "agent": "octie-agent",
        "reason": "审核通过且无开放问题，确认纳入", "expected_revision": rev,
        "data": {"id": rid2, "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}},
    })
    if not ok(f"confirm {rid2}", code, body):
        raise SystemExit(1)
    return rid2, rrev, digest, body["document_revision"]


def main():
    rev = show({"type": "ledger"})["document_revision"]
    print("start doc_rev:", rev)

    code, body = call(["source", "add"], {
        "operation_id": "ctl-src-5", "agent": "octie-agent",
        "reason": "登记用户关于控制合成、会话上限与 nearby 边界的澄清",
        "expected_revision": rev, "data": SOURCE,
    })
    if not ok("source add SRC-000005", code, body):
        return 1

    lifecycle(payload_data=REQ16)

    # REQ-000014 → r2：把用户确认的边界写进去
    doc = show({"type": "ledger"})
    r14 = [r for r in doc["object"]["requirements"] if r["id"] == "REQ-000014"][0]["revisions"][-1]
    data = {k: r14[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                                "priority", "placement", "included", "excluded", "normal_behavior",
                                "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in r14["sources"]]
    if not any(s["source_id"] == "SRC-000005" for s in data["sources"]):
        data["sources"].append({"source_id": "SRC-000005", "source_revision": 1})
    data["acceptance"] = [{**{k: a[k] for k in ("allow_na", "evidence", "exception", "expected", "input",
                                                "method", "operation", "preconditions", "role", "scenario")},
                           "id": a["id"]} for a in r14["acceptance"]]
    data["included"] = list(r14["included"]) + [
        "nearby 只包含其它动物，不含环境层（潮汐 / 天气 / 时间段）——用户 2026-10-29 已确认该边界合理",
    ]
    data["id"] = "REQ-000014"
    data["base_revision"] = r14["revision"]
    lifecycle(rid="REQ-000014", payload_data=data)

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
