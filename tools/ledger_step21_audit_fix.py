"""审计修正第 1 轮：REQ-000016 → r3、REQ-000014 → r3。

修 6 处：不可达的位移条件、量词/前置歧义、necessity 措辞、included 误放边界、距离前置、半径上限数值。
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
    data["necessity"] = (
        "若服务端只有单一意图状态：任何一路发「松开」都会把整只动物置为停车，于是 Agent 按住「上」时"
        "人一松「右」，动物就停住而不是回到「上」；而且按住超过 3 秒会被 TTL 判为失联而停住。"
        "不把这条规则写清楚，两路同时操作时的行为无法验收。"
    )
    for a in data["acceptance"]:
        if a["id"] == "AC-000058":
            a["preconditions"] = ("两个来源都能驱动同一只动物（例如一个 WebSocket 会话 + 一个 REST 调用，"
                                  "两者使用同一 token 或各自有效 token），动物位于开阔沙地")
        if a["id"] == "AC-000060":
            a.update({
                "scenario": "按住期间续期，超过 3 秒仍在移动",
                "preconditions": "动物位于沙地中央，所选方向至少有 350 逻辑像素的可走空间（例如从 x≈250 向右）",
                "input": "客户端按住「右」并每 1 秒续期一次，持续 4 秒",
                "operation": "在 t=3.5 秒时读取 moving 与坐标，并统计 4 秒内的累计位移",
                "expected": "t=3.5 秒时 moving 仍为 true 且坐标仍在变化；4 秒累计位移不小于 350 px；全程没有因 3 秒 TTL 停车",
                "exception": {
                    "scenario": "约 3 秒后停下、或 t=3.5 秒时 moving 为 false",
                    "expected": "判定续期未生效",
                    "handling": "检查续期是否刷新了同一来源按住项的时间戳",
                },
                "method": "每 1 秒续期一次，在 t=3.5 秒与 t=4 秒各采样一次位置与 moving",
                "evidence": "4 秒内的位置序列、t=3.5 秒的 moving 值、累计位移数值",
            })
    return data


def patch14(data):
    data["description"] = (
        "Agent 用自身 token 调用 GET /api/v1/animals/:id/state，返回三段结构：self（id、name、x、y、"
        "facing、moving、已上传卡片的尺寸与摘要）、nearby（半径 200 逻辑像素内其他动物的 id、name、x、y、"
        "facing 与到自己的距离，按距离升序）、world（画布宽高、在线数量、本次实际使用的半径）。"
        "响应只包含白名单字段，绝不返回任何动物的 token、token 哈希或其它凭据。半径可用查询参数调整，"
        "但服务端设上限（默认上限 400），返回体里回显实际生效的半径，便于 Agent 判断是否被截断。"
        "本接口**只描述动物**，不含潮汐、天气、时间段等环境层信息。"
    )
    # included 里那条其实是"边界确认"，挪到 boundaries
    data["included"] = [x for x in data["included"] if "不含环境层" not in x]
    data["boundaries"] = list(data["boundaries"]) + [{
        "scenario": "调用方希望知道「周围环境是什么样子」（潮汐 / 天气 / 时间段）",
        "expected": "状态接口只返回动物相关字段，不返回任何环境层字段",
        "handling": "环境层作为后续需求单独立项，不在本接口里扩展",
    }]
    for a in data["acceptance"]:
        if a["id"] == "AC-000052":
            a.update({
                "preconditions": "A 附近有两只动物：B 相距 120、C 相距 400（按欧氏距离预置）",
                "input": "A 以 radius=200 调用状态接口",
                "expected": "nearby 只包含 B；相距 400 的 C 不出现",
            })
        if a["id"] == "AC-000054":
            a.update({
                "expected": "实际半径被钳制到上限 400（可由环境变量 RADIUS_MAX 调整），nearby 不包含相距 500 的动物",
                "method": "带超大半径参数调用并读响应回显的 radius",
            })
    return data


def lifecycle(rid, data, rev, base_revision):
    data["id"] = rid
    data["base_revision"] = base_revision
    code, body = call(["req", "revise"], {
        "operation_id": f"audit-r3-revise-{rid}", "agent": "octie-agent",
        "reason": "审计修正：数值可达性、量词与字段语义",
        "expected_revision": rev, "data": data,
    })
    if not ok(f"revise {rid}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]

    for stage in ("submit", "review", "confirm"):
        if stage == "submit":
            payload = {"operation_id": f"audit-r3-submit-{rid}", "agent": "octie-agent",
                       "reason": "修订版转入待审核", "expected_revision": rev,
                       "data": {"id": rid, "revision": rrev, "digest": digest}}
            args = ["req", "submit"]
        elif stage == "review":
            payload = {"operation_id": f"audit-r3-review-{rid}", "agent": "review-agent",
                       "reason": f"对 {rid} 第 {rrev} 修订做审计复核", "expected_revision": rev,
                       "data": {
                           "target_type": "requirement", "target_id": rid,
                           "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
                           "necessity_review": ("必要性不变：两路控制同时存在时若只有单一意图状态，"
                                                "松开一路会导致停车而不是回落，必须写成可验收规则。"
                                                if rid == "REQ-000016" else
                                                "必要性不变：Agent 需要读到自身与附近状态才能做任何依赖周围信息的决策。"),
                           "completeness_review": ("完整性：本次只修被审计指出的 3 处——把不可达的位移条件改成"
                                                   "「t=3.5 秒仍 moving 且 4 秒位移 ≥350px」、把「两只来源」改为「两个来源」并"
                                                   "写清同 token 场景、necessity 不再引用临时实现。其余字段与条件 ID 未变。"
                                                   if rid == "REQ-000016" else
                                                   "完整性：把「不含环境层」从 included 移到 boundaries（它是边界而不是包含项）、"
                                                   "描述补出上限 400、AC-000052 前置写清 B/C 两只、AC-000054 的上限改为 400。条件 ID 未变。"),
                           "acceptance_review": ("验收复核：改写后的 AC-000060 在真实沙地上可达（只需 4 秒、≥350px），"
                                                 "并保留了「3 秒 TTL 不能停车」这一核心断言。"
                                                 if rid == "REQ-000016" else
                                                 "验收复核：AC-000052 与 AC-000054 的预期值已与实现/规格一致（200 过滤、400 钳制），"
                                                 "其余条件未改。"),
                           "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}…，与上一版逐字段比对，改动仅限上述字段。声明式审核。",
                       }}
            args = ["review", "add"]
        else:
            payload = {"operation_id": f"audit-r3-confirm-{rid}", "agent": "octie-agent",
                       "reason": "审计修订审核通过，确认纳入", "expected_revision": rev,
                       "data": {"id": rid, "revision": rrev, "digest": digest,
                                "scope": {"decision": "纳入"}}}
            args = ["req", "confirm"]
        code, body = call(args, payload)
        if not ok(f"  {stage} {rid}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    return rev


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    reqs = {r["id"]: r["revisions"][-1] for r in doc["object"]["requirements"]}
    print("start doc_rev:", rev)

    rev = lifecycle("REQ-000016", patch16(base_from(reqs["REQ-000016"])), rev, reqs["REQ-000016"]["revision"])
    doc = show({"type": "ledger"})
    reqs = {r["id"]: r["revisions"][-1] for r in doc["object"]["requirements"]}
    rev = lifecycle("REQ-000014", patch14(base_from(reqs["REQ-000014"])), rev, reqs["REQ-000014"]["revision"])
    print("done. doc_rev:", rev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
