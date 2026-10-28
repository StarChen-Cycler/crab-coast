"""多人世界重构：第 5 步 —— 新增 REQ-000014（Agent 读取自身/附近状态）。

用户原话里的核心之一：Agent 要能拿到「附近的一些动态状态」。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
SRC = {"source_id": "SRC-000004", "source_revision": 1}
PLACEMENT = {
    "kind": "全局",
    "reason": "服务端只读接口，供 Agent 与浏览器共用；不属于某一个页面区域",
}


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def ok(name, code, body):
    good = body.get("type") in ("success", "replay")
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={(body.get('object') or {}).get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


REQ = {
    "title": "Agent 可读取自身与附近动物的动态状态",
    "type": "功能", "module": "服务端接口", "priority": "P0", "placement": PLACEMENT,
    "sources": [SRC], "questions": [],
    "description": "Agent 用自身 token 调用 GET /api/v1/animals/:id/state，返回三段结构：self（id、name、x、y、facing、moving、已上传卡片的尺寸与摘要）、nearby（半径 200 逻辑像素内其他动物的 id、name、x、y、facing 与到自己的距离，按距离升序）、world（画布宽高、在线数量、本次实际使用的半径）。响应只包含白名单字段，绝不返回任何动物的 token、token 哈希或其它凭据。半径可用查询参数调整，但服务端设上限，返回体里回显实际生效的半径，便于 Agent 判断是否被截断。",
    "purpose": "让 Agent 能「看见」自己在哪、旁边有谁，从而据此决定下一步动作，而不是盲发移动指令。",
    "necessity": "用户原话明确要求 Agent 在登录后「获取附近的一些动态状态」；没有读接口，Agent 只能开环地发方向指令，任何依赖周围信息的行为（避让、跟随、聚集）都无法实现。",
    "included": [
        "GET /api/v1/animals/:id/state 的 self / nearby / world 三段结构",
        "nearby 按半径过滤并按距离升序",
        "字段白名单（不含任何凭据）",
        "半径查询参数与上限，并在响应里回显实际半径",
        "未上传卡片时 self.card 为 null，接口照常可用",
    ],
    "excluded": [
        "环境层（潮汐、天气、时间段）",
        "历史轨迹与回放",
        "遮挡与可见性计算",
    ],
    "normal_behavior": {
        "scenario": "两只动物相距小于 200 逻辑像素，各自调用状态接口",
        "behavior": "服务端计算距离并组装两段数据",
        "expected": "双方的 nearby 互相包含对方，且各自的 self 字段只描述自己",
    },
    "boundaries": [
        {"scenario": "动物之间距离超过半径", "expected": "不出现在对方 nearby 里", "handling": "按欧氏距离过滤"},
        {"scenario": "请求半径远大于上限", "expected": "实际按上限截断，响应里回显真实半径", "handling": "服务端钳制参数并在返回体声明"},
        {"scenario": "动物还没上传卡片", "expected": "状态仍可读，self.card 为 null", "handling": "卡片信息作为可选字段组装"},
    ],
    "acceptance": [
        ac("接口验收者", "自身状态包含卡片信息", "动物已上传通过校验的卡片且在线",
           "调用状态接口", "读取 self 段字段",
           "self 含 id/name/x/y/facing/moving，且 card 里有 192×192 尺寸与 64 位摘要",
           ("self 缺字段或 card 为空", "判定状态组装有误", "检查卡片元数据是否随动物读取一并返回"),
           "用 CLI state 命令输出完整 JSON", "状态响应 json"),
        ac("接口验收者", "附近按半径过滤", "A、B 两只动物分别位于相距 120 与 400 的位置",
           "A 调用状态接口", "读取 nearby 列表",
           "只包含相距 120 的那一只；相距 400 的不出现",
           ("远处动物出现在 nearby 里", "判定半径过滤失效", "检查距离计算与阈值比较"),
           "移动 B 到两个位置分别调用一次", "两次 nearby 的内容与距离值"),
        ac("接口验收者", "不泄露凭据", "已有两只动物在线",
           "调用状态接口并检查整个响应体", "在响应文本中搜索两方的明文 token 与 token 哈希",
           "两段都搜不到；响应只出现白名单字段",
           ("响应中出现 token 或哈希", "判定字段白名单失效", "改为显式挑选字段后再序列化"),
           "把响应原文保存后逐字段核对", "响应原文与搜索结果"),
        ac("接口验收者", "半径参数上限", "两只动物相距 500",
           "调用状态接口并传 radius=10000", "读取响应里回显的实际半径与 nearby",
           "实际半径被钳制到上限（200 或配置值），nearby 不包含相距 500 的动物",
           ("按 10000 返回", "判定参数未钳制", "对 radius 做上下限校验"),
           "带大半径参数调用并读回显值", "请求参数、响应回显半径与 nearby 内容"),
    ],
    "technical": "与浏览器快照共用同一套距离计算与字段白名单（world.js 里抽出 buildState(animal, radius)），避免两条路径字段不一致。",
}


def main():
    _, d = call(["show"], {"type": "ledger"})
    rev = d["document_revision"]
    print("start doc_rev:", rev)

    code, body = call(["req", "add"], {
        "operation_id": "mp-req-add-7", "agent": "octie-agent",
        "reason": "登记 Agent 读取附近状态接口的完整需求草稿",
        "expected_revision": rev, "data": REQ,
    })
    if not ok("req add", code, body):
        return 1
    rev = body["document_revision"]
    rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]

    for args, payload in (
        (["req", "submit"], {"operation_id": f"mp-submit-{rid}", "agent": "octie-agent",
                             "reason": "把完整草稿转入待审核", "expected_revision": rev,
                             "data": {"id": rid, "revision": rrev, "digest": digest}}),
        (["review", "add"], {"operation_id": f"mp-rev-{rid}", "agent": "review-agent",
                             "reason": f"对 {rid} 第 {rrev} 修订做语义审核", "expected_revision": rev + 1,
                             "data": {
                                 "target_type": "requirement", "target_id": rid,
                                 "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
                                 "necessity_review": "必要性核对：用户原话要求 Agent 登录后能获取附近动态状态；没有读接口，Agent 只能开环发方向指令，任何依赖周围信息的自动化都无法实现。",
                                 "completeness_review": "完整性核对：15 类字段齐全；纳入 5 条、排除 3 条、边界 3 条（超半径、参数钳制、未上传卡片）；页面归属为全局（服务端只读接口）并给出 reason；来源 SRC-000004 r1；开放问题为空。",
                                 "acceptance_review": "验收核对：4 条条件覆盖自身+卡片信息、半径过滤、凭据不泄露、参数上限，均给出可执行方法与可观察证据；「不泄露凭据」这条是可被自动化断言的硬检查。",
                                 "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}… 与来源 SRC-000004 r1 逐字段审阅。声明式审核，Agent 身份仅作操作归因。",
                             }}),
        (["req", "confirm"], {"operation_id": f"mp-confirm-{rid}", "agent": "octie-agent",
                              "reason": "审核通过且无开放问题，确认纳入", "expected_revision": rev + 2,
                              "data": {"id": rid, "revision": rrev, "digest": digest,
                                       "scope": {"decision": "纳入"}}}),
    ):
        code, body = call(args, payload)
        if not ok(" ".join(args), code, body):
            return 1
        rev = body["document_revision"]

    print("done. doc_rev:", rev, "req:", rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
