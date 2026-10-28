"""多人世界重构：第 1 步 —— 建页面 + 登记来源。

不可重复执行：每个 operation_id 只提交一次，重跑会命中 replay 或字段冲突。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    body = json.loads(out) if out.startswith("{") else {"_raw": out}
    return proc.returncode, body


def doc_rev():
    _, d = call(["show"], {"type": "ledger"})
    return d["document_revision"]


def report(name, code, body):
    print(f"{name}: exit={code} type={body.get('type')} doc_rev={body.get('document_revision')} "
          f"id={(body.get('object') or {}).get('id')}")
    if body.get("type") != "success":
        print("  issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
        return False
    return True


def main():
    rev = doc_rev()
    print("start doc_rev:", rev)

    # ---- 1. 新页面：多人前端 ----
    page = {
        "operation_id": "mp-page-add",
        "agent": "octie-agent",
        "reason": "多人客户端是独立页面（/play?t=token），与单机首页分开登记",
        "expected_revision": rev,
        "data": {
            "name": "多人小世界前端（/play）",
            "location": "crab-coast/play/index.html，带 token 打开；用 WebSocket 接收快照",
            "regions": [
                {"name": "世界画布区", "locator": "#world 画布：绘制海岸背景 + 所有在线动物及其四向帧"},
                {"name": "自身状态区", "locator": "画布角落实时显示自己的 id / 位置 / 朝向"},
                {"name": "附近动物提示区", "locator": "显示附近动物数量与最近一只的方向提示"},
                {"name": "连接状态提示", "locator": "WebSocket 连接中 / 已连接 / 重连中的角标"},
            ],
        },
    }
    code, body = call(["page", "add"], page)
    if not report("page add", code, body):
        return 1
    rev = body["document_revision"]

    # ---- 2. 来源：用户原话 ----
    src = {
        "operation_id": "mp-src-add",
        "agent": "octie-agent",
        "reason": "登记用户关于云端多人小世界的原始需求与三轮访谈结论",
        "expected_revision": rev,
        "data": {
            "kind": "用户消息",
            "name": "用户提出云端多人小世界重构需求（含三轮访谈结论）",
            "date_note": "2026-10-28 用户消息 + 同日三轮 interview 回答",
            "quote": "我希望这是一个运行在云服务器上的游戏……每个人制作好自己角色或小动物的动作卡之后，可以将其上传到游戏的服务器里。用户会使用 Agent 进行开发，利用我们提供的 skill，将动作卡转化为能够表现出动作帧的人物。用户不是通过输入账号和密码登录，而是由他们的 Agent 向我们未来部署的云服务或域名请求 token……在网址后面加上独一无二的 token 后，Agent 就可以登录进去……Agent 会返回给用户一个前端二维码。用户扫码打开后，可以直接在里面控制小动物的上下左右运动。",
            "summary": "访谈定稿：Node 单进程 + SQLite、共享一个世界、Agent 本地转换动作卡后上传成品、WebSocket 推送、保留 file:// 单机模式；token 直接进 URL（长随机、无密码）、自助注册需注册口令 + 限流、服务端权威校验移动、动作卡沿用 4×4 四向 48px、不做尺寸切换、四向各自固定朝向（不沿用螃蟹圆弧转身）。详细规格见 crab-coast/spec_multiplayer-world.md。",
            "manual_note": "原始需求为用户消息；具体决策来自 ask_user_question 三轮回答（用户已确认）",
        },
    }
    code, body = call(["source", "add"], src)
    if not report("source add", code, body):
        return 1
    print("page/source done. next doc_rev:", body["document_revision"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
