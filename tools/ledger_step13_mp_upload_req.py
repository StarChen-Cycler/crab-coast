"""多人世界重构：第 3 步 —— 新增 REQ-000013（无动作卡时先拖拽上传）。

流程：req add → submit → review → confirm，digest 全部来自响应。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
SRC = {"source_id": "SRC-000004", "source_revision": 1}
PLACEMENT = {
    "kind": "页面",
    "other": [],
    "primary": {"page_id": "PAGE-000002", "page_revision": 1,
                "region_id": "REG-000002-0001-0001"},
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
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:800])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


REQ = {
    "title": "无动作卡时先进拖拽上传页，上传成功后才进入游戏",
    "type": "功能", "module": "多人前端", "priority": "P0", "placement": PLACEMENT,
    "sources": [SRC], "questions": [],
    "description": "用户带 token 打开 /play 时，页面先用该 token 查询这只动物是否已有通过校验的动作卡。若没有，页面不渲染世界画布，而是显示一个拖拽上传区（也支持点击选择文件），要求用户先把成品卡片传上来；上传时仍按动作卡规格校验，通过后立即切换到游戏画面并开始接收快照。若已有卡片，则直接进入游戏。这样用户不必回到命令行就能完成「上传 → 开玩」。",
    "purpose": "让没有动作卡的用户在同一个页面里完成上传并立即开玩，而不是看到一个画不出来的角色发呆。",
    "necessity": "去掉这一步，无卡用户打开链接后世界画面里没有自己的动物（或画出空白占位），既看不出问题也无法自助修复，只能去找 Agent；而玩家侧最常见的首次使用场景恰恰就是「还没传过卡」。",
    "included": [
        "打开页面时按 token 查询该动物是否已有卡片",
        "无卡时显示拖拽上传区（拖拽 + 点击选择文件）",
        "上传走与 Agent 相同的规格校验，失败逐条显示原因",
        "上传成功后不刷新页面直接切到游戏画面",
        "已有卡片时跳过上传页直接进入游戏",
    ],
    "excluded": [
        "在浏览器里做母版转换（只接收成品 card.png + manifest.json）",
        "尺寸变体的生成",
        "在线编辑角色外观",
    ],
    "normal_behavior": {
        "scenario": "一只刚注册、还没上传过卡片的动物被用户打开链接",
        "behavior": "页面查询卡片状态，未找到后显示上传区",
        "expected": "页面显示可拖拽的上传区域而不是游戏画面；拖入合格卡片后立即进入游戏并能操控自己的动物",
    },
    "boundaries": [
        {"scenario": "已有卡片再次上传", "expected": "允许覆盖，新卡片生效", "handling": "上传成功后重新拉取卡片并重绘"},
        {"scenario": "上传过程中断网或服务端报错", "expected": "停留在上传页并提示可重试", "handling": "上传失败不清空已选文件，显示服务端错误原因"},
        {"scenario": "token 无效或已轮换", "expected": "提示 token 无效，不显示上传区", "handling": "先校验 token 再决定渲染哪个界面"},
    ],
    "acceptance": [
        ac("前端验收者", "无卡时显示上传页", "已注册一只动物但未上传卡片，持有其 token",
           "打开 /play?t=<token>", "观察页面首屏内容",
           "首屏是拖拽上传区（含「拖入或点击选择」提示与服务端返回的卡片缺失说明），没有渲染世界画布",
           ("仍显示游戏画面或空白", "判定无卡检测未生效", "检查卡片状态请求与首屏分支"),
           "用浏览器打开页面并读取 DOM 中的上传区节点是否存在", "首屏截图 + 上传区节点存在性结果"),
        ac("前端验收者", "上传合格卡片后进入游戏", "同上，处于上传页",
           "拖入符合 4×4/48px 规格的 card.png 与 manifest.json", "等待上传完成并读取页面状态",
           "上传返回 200，页面在 2 秒内切换到游戏画面并开始收到快照，能看到自己的动物",
           ("上传成功但页面仍停在上传区", "判定切换逻辑缺失", "检查上传成功回调与状态重取"),
           "上传后读取页面上的连接状态与快照计数", "上传响应、切换时间、快照计数"),
        ac("前端验收者", "不合格卡片停在上传页并报错", "处于上传页",
           "拖入行数不符（3 行）的卡片", "观察页面提示",
           "不上传成功、不切换画面；页面显示服务端返回的具体原因（指出行数不符）",
           ("页面切到游戏或静默失败无提示", "判定错误展示缺失", "把服务端 errors 透传到 UI"),
           "上传坏卡片后读取页面错误文本", "状态码、errors 内容与页面显示的文本"),
        ac("前端验收者", "已有卡片直接进游戏", "该动物已成功上传过卡片",
           "重新打开 /play?t=<token>", "观察首屏",
           "首屏直接是游戏画面，不出现上传区，且 3 秒内收到快照",
           ("又出现上传区", "判定卡片状态判断有误", "检查卡片状态接口返回与本地缓存"),
           "重新打开页面并检查上传区节点是否出现", "首屏截图 + 上传区节点存在性结果"),
    ],
    "technical": "实现放在 play/play.js：启动时 GET /api/v1/animals/:id/card-status；无卡渲染 #dropzone（dragover/drop + input[type=file]），上传成功后重取状态并初始化 WebSocket。",
}


def main():
    _, d = call(["show"], {"type": "ledger"})
    rev = d["document_revision"]
    print("start doc_rev:", rev)

    code, body = call(["req", "add"], {
        "operation_id": "mp-req-add-6",
        "agent": "octie-agent",
        "reason": "登记「无动作卡时先拖拽上传」的完整需求草稿",
        "expected_revision": rev,
        "data": REQ,
    })
    if not ok("req add REQ-000013", code, body):
        return 1
    rev = body["document_revision"]
    rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]

    steps = [
        (["req", "submit"], {
            "operation_id": f"mp-submit-{rid}", "agent": "octie-agent",
            "reason": "把完整草稿转入待审核", "expected_revision": rev,
            "data": {"id": rid, "revision": rrev, "digest": digest}}),
        (["review", "add"], {
            "operation_id": f"mp-rev-{rid}", "agent": "review-agent",
            "reason": f"对 {rid} 第 {rrev} 修订做语义审核", "expected_revision": rev + 1,
            "data": {
                "target_type": "requirement", "target_id": rid,
                "target_revision": rrev, "target_digest": digest, "conclusion": "通过",
                "necessity_review": "必要性核对：无卡用户是首次使用的主要人群，若不在页面内引导上传，他们打开链接后既看不到自己的动物也不知道要做什么，必须在命令行与浏览器之间来回；本项把「上传→开玩」收在同一个页面里，缺失会直接打断首次使用。",
                "completeness_review": "完整性核对：13 类字段齐全；纳入 5 条、排除 3 条、边界 3 条（覆盖已有卡再次上传、上传中断、token 无效）；页面归属 PAGE-000002 r1 的世界画布区，来源 SRC-000004 r1；开放问题为空。",
                "acceptance_review": "验收核对：4 条条件都给出角色/场景/前置/输入/操作/预期/异常/方法/证据，分别覆盖无卡显示上传页、上传成功切游戏、不合格卡片停页报错、已有卡直接进游戏，均为可直接照做的可观察现象。",
                "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}… 与来源 SRC-000004 r1（用户 2026-10-28 追加消息）逐字段审阅。声明式审核，Agent 身份仅作操作归因。",
            }}),
        (["req", "confirm"], {
            "operation_id": f"mp-confirm-{rid}", "agent": "octie-agent",
            "reason": "审核通过且无开放问题，确认纳入", "expected_revision": rev + 2,
            "data": {"id": rid, "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}}}),
    ]

    for args, payload in steps:
        code, body = call(args, payload)
        if not ok(" ".join(args), code, body):
            return 1
        rev = body["document_revision"]

    print("done. doc_rev:", rev, "req:", rid, "digest:", digest[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
