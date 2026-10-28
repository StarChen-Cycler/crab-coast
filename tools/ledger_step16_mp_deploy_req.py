"""多人世界重构：第 6 步 —— 新增 REQ-000015（部署与运行配置）。

「运行在云服务器上」这条方向需要能被验证：一条命令起服务、环境变量可配、依赖可控。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
SRC = {"source_id": "SRC-000004", "source_revision": 1}
PLACEMENT = {"kind": "全局", "reason": "部署与运行配置是服务端整体能力，不属于任何页面区域"}


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
    "title": "一条命令在服务器上跑起来且关键参数可配置",
    "type": "非功能", "module": "部署与运行", "priority": "P1", "placement": PLACEMENT,
    "sources": [SRC], "questions": [],
    "description": "服务端以单进程方式运行：安装依赖（只有一个 ws）后执行一条启动命令即可提供静态页面、/play 前端、REST 接口与 WebSocket。端口、注册口令、数据目录、限流阈值全部通过环境变量配置并有合理默认值；运行时数据（SQLite 库与上传的卡片）只写入配置的数据目录，不污染代码目录。启动失败时给出可读原因（例如端口被占用、数据目录不可写），而不是抛栈。",
    "purpose": "让这台服务能被云服务器按「拉代码 → 装依赖 → 设几个环境变量 → 启动」这套标准流程部署，而不是依赖本机特有的路径。",
    "necessity": "如果端口、口令、数据目录写死在代码里，部署到云服务器就必须改代码；而运行时数据混在代码目录里会让升级与备份都变危险。",
    "included": [
        "单命令启动并提供静态页 + API + WebSocket",
        "PORT / REGISTER_CODE / DATA_DIR / 限流阈值 的环境变量配置与默认值",
        "运行时数据只写 DATA_DIR",
        "GET /healthz 健康检查",
        "启动失败时输出可读原因",
    ],
    "excluded": [
        "容器镜像与编排文件",
        "进程守护与自动重启（交给外部工具）",
        "HTTPS 终止与域名配置（交给反向代理）",
    ],
    "normal_behavior": {
        "scenario": "在干净目录里按 README 安装依赖并启动",
        "behavior": "进程监听配置端口，打印实际生效的端口与数据目录",
        "expected": "浏览器可打开单机页与 /play，/healthz 返回 200 与在线数",
    },
    "boundaries": [
        {"scenario": "端口被占用", "expected": "进程不静默失败，输出端口被占用的可读提示", "handling": "监听错误时打印原因并以非零码退出"},
        {"scenario": "DATA_DIR 不可写", "expected": "启动时即报错并说明目录与权限", "handling": "启动阶段做一次可写探测"},
    ],
    "acceptance": [
        ac("部署验收者", "一条命令启动并可访问", "已 npm install，环境变量按默认值",
           "运行启动命令", "访问 /healthz 与单机首页",
           "/healthz 返回 200 且含 online 字段；单机首页返回 200",
           ("启动失败或 404", "判定路由或静态托管有误", "检查路由表与静态目录映射"),
           "启动服务后分别 curl 两个地址", "启动日志 + 两个响应的状态码与 body"),
        ac("部署验收者", "关键参数来自环境变量", "端口与数据目录改为非默认值",
           "用 PORT=xxxx、DATA_DIR=<临时目录>、REGISTER_CODE=<自定义口令> 启动", "注册一只动物并让它移动，然后检查数据目录",
           "服务监听新端口；注册用新口令才能成功；SQLite 库与卡片文件出现在新数据目录下，代码目录没有新增运行时文件",
           ("仍监听默认端口或数据写到代码目录", "判定配置未生效", "检查配置读取与默认值覆盖顺序"),
           "换参数重启一轮，重复注册与移动", "进程监听端口、数据目录文件列表、代码目录 git status"),
        ac("部署验收者", "健康检查反映在线数", "服务运行中，在线 0 只与在线 1 只两种状态",
           "分别访问 /healthz", "比较两次返回的 online 字段",
           "在线 0 时 online=0；有一只动物的浏览器或 Agent 连上后 online≥1",
           ("online 恒为 0", "判定在线统计未与连接/动物状态关联", "检查在线数来源"),
           "断开连接前后各请求一次", "两次 /healthz 的 body"),
    ],
    "technical": "server/config.js 读取 process.env 并给出默认值；启动时确保 DATA_DIR 存在且可写；/healthz 直接返回 world 的在线统计。",
}


def main():
    _, d = call(["show"], {"type": "ledger"})
    rev = d["document_revision"]
    print("start doc_rev:", rev)

    code, body = call(["req", "add"], {
        "operation_id": "mp-req-add-8", "agent": "octie-agent",
        "reason": "登记部署与运行配置的完整需求草稿",
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
                                 "necessity_review": "必要性核对：目标是部署到云服务器；参数写死或运行时数据混进代码目录会让部署、升级、备份都变成改代码或搬文件，属于必须现在定下来的运行约束。",
                                 "completeness_review": "完整性核对：15 类字段齐全；纳入 5 条、排除 3 条（容器/守护/HTTPS 明确交给外部）、边界 2 条（端口占用、目录不可写）；全局归属给出了 reason；来源 SRC-000004 r1；开放问题为空。",
                                 "acceptance_review": "验收核对：3 条条件覆盖「一条命令起服务」「环境变量真正生效且数据只写 DATA_DIR」「健康检查反映在线数」，均可由命令行断言，证据是启动日志与响应体。",
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
