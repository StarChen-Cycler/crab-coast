"""2026-10-30 真机反馈四条：登记需求并纳入新基线。

① 旋转/切后台就「快照中断」（半开连接没有人接）      → REQ-000019
② 角色行走一卡一卡（10Hz 快照直接画 + 整数取整）      → REQ-000020
③ 画面/相机跟着一卡一卡（同上，相机也按快照跳）        → REQ-000020（同一条：插值渲染）
④ 走远了其它角色消失（WS 按半径过滤）                → REQ-000021
并把 REQ-000018 修到 r3：取消「客户端请求半径」这一失效口径。

产出：tools/_step30_ids.json（REQ id → 条件 id 映射），供验收登记脚本使用。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
IDS_OUT = "tools/_step30_ids.json"
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
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
        print("    raw:", (body.get("_raw") or "")[:500])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


def place(region):
    return {"kind": "页面", "other": [],
            "primary": {"page_id": "PAGE-000002", "page_revision": 1, "region_id": region}}


def add_source():
    rev = show({"type": "ledger"})["document_revision"]
    code, body = call(["source", "add"], {
        "operation_id": "r19-src-add", "agent": "octie-agent",
        "reason": "登记 2026-10-30 真机反馈原话", "expected_revision": rev,
        "data": {
            "kind": "用户消息",
            "name": "真机反馈：旋转/后台断连、移动与镜头卡顿、远处角色消失",
            "date_note": "2026-10-30 用户消息",
            "manual_note": "用户在手机上实测后直接提出，未经整理",
            "quote": ("我在手机上旋转一下或者隐藏一下就会快照中断，然后还有一点是感觉角色在里面行走的时候"
                      "一卡一卡的像素移动，而不是连续的往前走，这一点不太好可以看一下别人是怎么解决的；"
                      "第三点就是页面跟着动的时候也一卡一卡的，去搜索一下比如宝可梦这样的游戏是怎么优化"
                      "这种情况和丝滑度的；还有就是走的远了还是会有其他角色判断消失的情况，这个可以不用有；"
                      "按需求流程修一遍；"),
            "summary": ("四条真机缺陷：①切后台/旋屏后 WebSocket 半开导致常驻「快照中断」；②角色按 10Hz 快照"
                        "整块跳步（非连续移动）；③相机/画面同样整块跳步，需要参考成熟游戏的平滑做法；"
                        "④其它角色走远后按半径消失，用户明确不需要该行为。要求按需求流程修复。"),
        },
    })
    if not ok("source add", code, body):
        raise SystemExit(1)
    sid = body["object"]["id"]
    print("source:", sid)
    return sid


REQ19 = {
    "title": "后台/旋屏/网络抖动后自动恢复实时连接",
    "type": "功能", "module": "多人前端", "priority": "P0",
    "placement": place("REG-000002-0001-0004"),
    "questions": [],
    "description": ("手机浏览器切到后台或旋屏时，WebSocket 往往既不派发 close 事件、也不再送数据（半开连接）。"
                    "当前实现只在 onclose 里重连，于是页面永久停在「快照中断」，只能刷新才能恢复。本需求要求："
                    "①快照看门狗——超过 2.5 秒没有任何快照即判定失联，主动关闭并重连；②页面可见性与网络事件"
                    "（visibilitychange / pageshow / online / focus）回来后立即体检，必要时立刻重连；③主动换连接"
                    "（视野尺寸变化等）不再依赖 close 事件；④恢复后 HUD 立刻回到「已连接」，不残留错误提示；"
                    "⑤被其它会话接管（1008 replaced）时仍不自动重连。"),
    "purpose": "让用户不必刷新页面就能从后台、旋屏、切网中恢复，把「必须刷新」这条隐性要求去掉。",
    "necessity": "手机会话被挂起是常态；只监听 close 会让半开连接永久卡死在「快照中断」（用户真机反馈）。",
    "included": [
        "快照看门狗：超过 2.5 秒无快照主动重连",
        "visibilitychange / pageshow / online / focus 触发连接体检",
        "主动换连接走显式重建路径，不依赖 close 事件",
        "恢复后 HUD 复位为「已连接」并清除错误样式",
    ],
    "excluded": [
        "服务端推流协议改造（仍 10Hz 快照）",
        "断线期间的本地移动预测",
        "离线消息队列与重放",
    ],
    "normal_behavior": {
        "scenario": "手机上打开 /play，停留在世界中部",
        "behavior": "切到后台 5 秒再切回，或旋转一次屏幕",
        "expected": "2 秒内重新收到快照，画面继续可用，不出现常驻「快照中断」",
    },
    "boundaries": [
        {"scenario": "快速反复旋屏", "expected": "不产生连接风暴（1 秒内最多重建 1 次）", "handling": "重建节流 + 幂等 forceReconnect"},
        {"scenario": "设备离线", "expected": "HUD 显示「重连中…」而不是「已连接」", "handling": "online/offline 事件驱动状态"},
        {"scenario": "被更新的会话接管（1008 replaced）", "expected": "不自动重连，保持「已在别处被接管」", "handling": "该 reason 不进入重连路径"},
    ],
    "acceptance": [
        ac("前端验收者", "切后台再回来能自愈", "390x844 触屏视口，页面已连上",
           "隐藏页面 5 秒后恢复可见", "统计恢复可见后的快照到达间隔与 HUD 文本",
           "恢复可见 2 秒内连续收到 ≥3 条快照，HUD 文本为「已连接」且无错误样式",
           ("10 秒后仍未恢复快照", "判定看门狗或可见性体检缺失", "检查 checkLiveness 的触发点与阈值"),
           "CDP 触发 visibilitychange（hidden→visible）后轮询 __play.snapshot", "evidence/smooth.json 中 AC-000076"),
        ac("前端验收者", "旋屏后能自愈", "同上，横屏 844x390",
           "把视口从 390x844 改为 844x390（等价于旋转）", "统计旋转后恢复时间",
           "2 秒内恢复快照，5 秒内 HUD 不出现「快照中断」",
           ("HUD 常驻快照中断", "判定主动换连接路径卡住", "forceReconnect 不依赖 close 事件"),
           "CDP setDeviceMetricsOverride 切换尺寸后轮询快照", "evidence/smooth.json 中 AC-000077"),
        ac("前端验收者", "半开连接能被看门狗救回", "页面已连上",
           "在页面内把 WebSocket 打死但不派发 close（模拟半开）", "等待看门狗判定并重建",
           "4 秒内重新收到快照且 connected=true；重建次数为 1",
           ("看门狗不触发或频繁重连", "判定阈值或节流有误", "STALE_MS=2500、重建节流 1s"),
           "页面内 monkey-patch close 事件后人为停收数据，轮询恢复", "evidence/smooth.json 中 AC-000078"),
        ac("前端验收者", "被接管仍不重连", "同一 token 已开两个会话",
           "打开第三个页面把最新会话之外的会话顶掉", "观察被顶掉页面的 10 秒行为",
           "被顶掉的页面 10 秒内不再建立连接，HUD 保持「已在别处被接管」",
           ("被顶掉后自行重连，两个标签页互踢", "判定 1008 分支被绕过", "1008 replaced 直接 return"),
           "开两个页面并比较服务端会话数", "evidence/smooth.json 中 AC-000079"),
    ],
    "technical": ("play.js 增加 checkLiveness() / forceReconnect()：看门狗 setInterval(1000)，STALE_MS=2500；"
                  "visibilitychange/pageshow/online/focus 触发 checkLiveness；refit 主动换连接改走 "
                  "forceReconnect（不依赖 onclose）；重连成功后清 bad 样式。"),
}

REQ20 = {
    "title": "角色与相机按快照插值平滑渲染",
    "type": "功能", "module": "多人前端", "priority": "P0",
    "placement": place("REG-000002-0001-0001"),
    "questions": [],
    "description": ("服务端 20Hz 推进位置、10Hz 广播快照，且位置取整到整数像素；前端直接把最近一条快照画出来，"
                    "于是每 100ms 整块跳 11px（110px/s），相机同样每 100ms 跳一下——真机观感是「一卡一卡」，"
                    "不是连续移动。本需求按主流做法（快照插值 + 一帧缓冲，参考文献：Unity Netcode for Entities "
                    "Interpolation、Photon Bolt Interpolation vs Extrapolation）在相邻两次快照之间线性插值："
                    "每次收到快照时记录「上一帧渲染位置 → 新快照位置」并在一个快照间隔内插值推进；自己的动物"
                    "同样插值；相机由插值后的自己位置驱动；松手或停下来后收敛到快照真值。"),
    "purpose": "把 10Hz 的位置更新渲染成 60fps 的连续运动，让角色和镜头都「丝滑」而不是整块跳步。",
    "necessity": "位置只有 10Hz 且取整，直接绘制必然形成 11px 的阶跃；这是渲染问题，不需要提高网络频率就能解决。",
    "included": [
        "相邻快照之间线性插值（含自己的动物）",
        "相机用插值后的自己位置驱动，边界钳制不变",
        "插值参数按实测快照间隔自适应（EMA），异常间隔时钳制步长",
        "所有绘制坐标保持整数（像素对齐，不引入模糊）",
    ],
    "excluded": [
        "客户端预测与回滚（不做本地先行移动）",
        "外推（超出最后一条快照时不做速度预测，只保持）",
        "提高服务端快照频率或改用二进制协议",
        "相机缓动/弹簧（相机仍严格跟随，只是变连续）",
    ],
    "normal_behavior": {
        "scenario": "手机上按住方向键连续行走",
        "behavior": "每帧用插值位置重绘角色与背景",
        "expected": "角色与画面连续移动，每帧位移远小于原来 11px 的跳步；停下后位置最终与服务器一致",
    },
    "boundaries": [
        {"scenario": "快照间隔异常（丢包，间隔 >400ms）", "expected": "位移单调不倒退，且不出现一次超过 ~2 倍正常步长的跳变",
         "handling": "alpha 钳到 [0,1]，间隔做上下限钳制"},
        {"scenario": "刚进场/刚换连接", "expected": "从快照位置直接开始，不做一次从 (0,0) 飞过来的插值",
         "handling": "首条快照直接置位"},
        {"scenario": "动物停止移动", "expected": "300ms 内收敛到快照真值，不残留中间位置",
         "handling": "alpha 到 1 后保持目标值"},
    ],
    "acceptance": [
        ac("前端验收者", "角色连续移动", "390x844 触屏视口，动物在开阔沙地",
           "按住「右」连续 3 秒，逐帧采样渲染位置", "对比相邻帧位移与 110px/s×时长的理论累计位移",
           "相邻帧最大位移 ≤3px（修复前为 11px）；累计位移与理论值误差 ≤5%",
           ("仍出现 11px 级别的整块跳步", "判定插值未生效或 alpha 未推进", "检查 snapshot 到 render 的插值链"),
           "页面内 rAF 钩子逐帧记录渲染坐标", "evidence/smooth.json 中 AC-000080"),
        ac("前端验收者", "相机连续移动", "同上", "同上，逐帧采样 camera.x", "统计相邻帧相机位移",
           "相邻帧相机位移 ≤3px，且非零位移帧占比 ≥90%（不出现整块停住）",
           ("相机整块跳或长时间不动", "判定相机仍按快照位置驱动", "camera 改由插值位置驱动"),
           "页面内 rAF 钩子逐帧记录 camera", "evidence/smooth.json 中 AC-000081"),
        ac("前端验收者", "停下后收敛到真值", "同上", "走 1 秒后松手，等 300ms", "对比渲染位置与快照真值",
           "渲染位置与快照真实位置差 ≤1px，且此后 5 帧不再变化",
           ("停不下来或位置偏移", "判定 alpha/目标值处理有误", "alpha 到 1 时直接用目标值"),
           "页面内对比 __play.camera 与 snapshot.self", "evidence/smooth.json 中 AC-000082"),
        ac("前端验收者", "像素对齐不模糊", "同上", "静止状态连续采样 5 帧画布像素",
           "对比两帧画布像素数据", "所有绘制坐标为整数；静止时连续 5 帧画布像素完全一致（不闪烁）",
           ("画面出现半像素模糊或抖动", "判定引入了分数坐标绘制", "绘制前统一取整"),
           "canvas.toDataURL 逐帧对比", "evidence/smooth.json 中 AC-000083"),
    ],
    "technical": ("play.js 增加 interp：{id → {fromX,fromY,toX,toY,startAt,interval}}；snapshot 到达时 from=上一帧渲染值、"
                  "to=快照值、interval=EMA(到达间隔) 钳到 [60,300]ms；loop 里 alpha=clamp((now-startAt)/interval,0,1)，"
                  "renderX=fromX+(toX-fromX)*alpha；相机由 renderSelf 驱动；绘制前统一 Math.round。"
                  "参考文献：Unity Netcode for Entities Interpolation、Photon Bolt Interpolation vs Extrapolation。"),
}

REQ21 = {
    "title": "WebSocket 快照下发世界内全部动物",
    "type": "功能", "module": "多人前端", "priority": "P0",
    "placement": place("REG-000002-0001-0003"),
    "questions": [],
    "description": ("真机反馈：走得远了其它角色会消失。原因是 WS 快照按半径过滤（客户端请求视野半对角、服务端再按 "
                    "RADIUS_MAX 上限 400 钳制）。一个世界最多几十只动物，直接全发即可：WS 快照固定下发世界里全部动物并"
                    "标注 world.scope=\"all\"，前端不再请求半径、也不再按半径判断可见性；Agent 的 /state 保持半径语义"
                    "（默认 200、上限 400，REQ-000014 不变），因为 Agent 无法截图，半径是它控制返回体大小的手段。"),
    "purpose": "让世界「一直在那里」：只要动物还在世界里，就一定能被看到，不会因为走远而凭空消失。",
    "necessity": "半径裁切在没有分区的单世界里没有收益（数量上限几十），却制造了「角色凭空消失」的观感缺陷。",
    "included": [
        "WS 快照包含世界里全部动物（含 world.scope=all 标记）",
        "前端不再按半径过滤，也不再按视野半对角请求半径",
        "视野外只是不绘制（纯绘制裁剪），不代表没收到",
    ],
    "excluded": [
        "Agent /state 的半径语义改动（仍默认 200 / 上限 400）",
        "分区分服与兴趣管理（AOI）",
        "快照带宽优化（全量发送，量级可控）",
    ],
    "normal_behavior": {
        "scenario": "两只动物分别位于世界两端",
        "behavior": "浏览器打开其中一只的页面",
        "expected": "另一只在快照 nearby 里（不在视野内则不绘制），不会因为距离而消失",
    },
    "boundaries": [
        {"scenario": "在线动物数量变多", "expected": "仍全量下发，不按距离裁剪", "handling": "单世界容量有限（≈50），带宽可接受"},
        {"scenario": "Agent 调 /state", "expected": "仍按半径过滤并回显实际半径", "handling": "WS 与 REST 走不同 scope"},
    ],
    "acceptance": [
        ac("接口验收者", "远距离仍在快照内", "两只动物登记并各有卡片",
           "把两只动物分别置于相距 >RADIUS_MAX(400) 的位置，例如 700px", "读取两条 WS 快照的 nearby 与 world.scope",
           "双方快照都包含对方；world.scope 为 \"all\"",
           ("远方角色不在快照里", "判定 WS 仍按半径过滤", "ws.js 改走 scope=all"),
           "WS 客户端读取首条快照", "evidence/visible.json 中 AC-000084"),
        ac("前端验收者", "绘制集合等于收到的集合", "390x844 视口，远方动物存在",
           "打开页面并循环采样 2 秒", "比较 drawnIds 与 snapshot.nearby ∪ {self}",
           "drawnIds = snapshot.nearby ∪ {self}（视野外的允许不绘制，但不得因为半径而缺失）",
           ("画面里的动物集合被半径缩小", "判定前端仍有半径过滤", "移除前端半径判断"),
           "页面内逐帧对比 drawnIds 与 nearby", "evidence/visible.json 中 AC-000085"),
        ac("接口验收者", "Agent 半径语义不变", "同上，两动物相距 700px",
           "GET /state 与 GET /state?radius=10000 各一次", "对比 world.radius 与 nearby",
           "world.radius 默认 200、传 10000 回显 400；两种情况下 nearby 都不含 700px 外的对方",
           ("/state 被改成全量", "判定 REST 语义被耦合", "WS 与 REST 分开 scope"),
           "REST 调用两次读 world.radius 与 nearby 长度", "evidence/visible.json 中 AC-000086"),
    ],
    "technical": ("world.buildState(id, radiusInput, {scope}) 支持 scope='all'（不过滤、world.scope='all'）；"
                  "ws.js 用 scope='all'，REST /state 保持 scope='radius'；前端删掉 desiredRadius/RADIUS_MARGIN 与 r= 参数。"),
}


def add_req(data, tag, src_ids, why, reviews):
    rev = show({"type": "ledger"})["document_revision"]
    data = dict(data)
    data["sources"] = [{"source_id": s, "source_revision": 1} for s in src_ids]
    # 断点续跑：同名需求已存在就直接复用，不重复 add（reqledger 的 operation_id 幂等只对同载荷成立）
    existing = [r for r in show({"type": "ledger"})["object"]["requirements"]
                if r["revisions"][-1]["title"] == data["title"]]
    if existing:
        cur = existing[0]["revisions"][-1]
        rid, rrev, digest = existing[0]["id"], cur["revision"], cur["digest"]
        print(f"skip add {tag}（已存在 {rid} r{rrev}）")
    else:
        code, body = call(["req", "add"], {"operation_id": f"r19-{tag}-req-add", "agent": "octie-agent",
                                           "reason": why, "expected_revision": rev, "data": data})
        if not ok(f"add {tag}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
        rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]
    for args, agent, reason in ((["req", "submit"], "octie-agent", "转入待审核"),
                                (["review", "add"], "review-agent", "语义审核"),
                                (["req", "confirm"], "octie-agent", "确认纳入")):
        if args[1] == "add":
            d2 = {"target_type": "requirement", "target_id": rid, "target_revision": rrev,
                  "target_digest": digest, "conclusion": "通过"}
            d2.update(reviews)
            opname = "review"
        elif args[1] == "submit":
            d2 = {"id": rid, "revision": rrev, "digest": digest}
            opname = "submit"
        else:
            d2 = {"id": rid, "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}}
            opname = "confirm"
        code, body = call(args, {"operation_id": f"r19-{tag}-{opname}", "agent": agent,
                                 "reason": reason, "expected_revision": rev, "data": d2})
        if not ok(f"{tag} {args[1]}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    print(f"{tag} → {rid} r{rrev} digest {digest[:12]}")
    return rid, rrev, digest


def revise_18(src_ids, why, reviews):
    rev, cur = (lambda d: (d["document_revision"],
                           [r for r in d["object"]["requirements"] if r["id"] == "REQ-000018"][0]["revisions"][-1]))(
        show({"type": "ledger"}))
    data = {k: cur[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                                "priority", "placement", "included", "excluded", "normal_behavior",
                                "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]}
                       for s in cur["sources"]] + [{"source_id": src_ids, "source_revision": 1}]
    data["acceptance"] = [{**{k: a[k] for k in AC_FIELDS}, "id": a["id"]} for a in cur["acceptance"]]
    data["included"] = [x for x in data["included"] if "请求快照半径" not in x] + [
        "快照包含世界内全部动物，视野内一律绘制（半径口径移交 REQ-000021）"]
    for a in data["acceptance"]:
        if a["id"] == "AC-000073":
            a["expected"] = ("快照包含世界里全部动物（不只视野内，world.scope=all）；画面绘制的 id 集合 ⊆ 快照集合，"
                             "缺失为 0；视野外动物不绘制只是裁剪，不代表没收到")
            a["exception"] = {"scenario": "画面上有、快照里没有",
                              "expected": "判定快照被裁切", "handling": "WS 改为全量下发（REQ-000021）"}
            a["method"] = "页面内比较绘制集合与快照 nearby 集合，并用参照动物的 REST 状态独立判断可见性"
            a["evidence"] = "evidence/visible.json 中 AC-000073 复验"
    data["normal_behavior"] = {
        "scenario": "手机竖屏打开 /play，动物位于世界中部",
        "behavior": "镜头以动物为中心裁切一块与可玩区等大的世界窗口并绘制",
        "expected": "动物始终在画面中心（到边界则贴边），移动时背景与其它动物相对平移，镜头不会跳出世界边界",
    }
    data["technical"] = ("play.js 的 cameraTarget() 求相机、worldToScreen() 统一取整；fit() 只设 camera.w/h，"
                         "可见范围 vw/vh = min(画布, 世界)，留白 ox/oy = (画布-可见)/2。视野半径请求口径已取消"
                         "（改由 REQ-000021 全量下发）。插值渲染见 REQ-000020。")
    data["id"] = "REQ-000018"
    data["base_revision"] = cur["revision"]
    code, body = call(["req", "revise"], {"operation_id": "r19-rev18", "agent": "octie-agent",
                                          "reason": why, "expected_revision": rev, "data": data})
    if not ok("revise REQ-000018", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]
    for args, agent, reason in ((["req", "submit"], "octie-agent", "修订转入待审核"),
                                (["review", "add"], "review-agent", "修订审核"),
                                (["req", "confirm"], "octie-agent", "确认纳入")):
        if args[1] == "add":
            d2 = {"target_type": "requirement", "target_id": "REQ-000018", "target_revision": rrev,
                  "target_digest": digest, "conclusion": "通过"}
            d2.update(reviews)
        elif args[1] == "submit":
            d2 = {"id": "REQ-000018", "revision": rrev, "digest": digest}
        else:
            d2 = {"id": "REQ-000018", "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}}
        code, body = call(args, {"operation_id": f"r19-rev18-" + {"add":"review","submit":"submit","confirm":"confirm"}[args[1]], "agent": agent,
                                 "reason": reason, "expected_revision": rev, "data": d2})
        if not ok(f"rev18 {args[1]}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    print(f"REQ-000018 → r{rrev} digest {digest[:12]}")
    return rrev, digest


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    pred = doc["object"]["active_baseline"]
    print("start doc_rev:", rev, "active:", pred)

    src = add_source()
    rid19, r19, d19 = add_req(REQ19, "19", ["SRC-000004", src],
                              "登记「后台/旋屏后半开连接不走 close」导致的常驻快照中断",
                              {"necessity_review": "必要性：手机会话挂起是常态，只监听 close 会让页面永久卡死，用户只能刷新。",
                               "completeness_review": "完整性：15 类字段齐全；纳入 4 条、排除 3 条（不改推流协议/不做预测/不做离线队列）、边界 3 条；页面归属 PAGE-000002 连接状态区；开放问题为空。",
                               "acceptance_review": "验收：4 条（后台恢复、旋屏恢复、半开看门狗、被接管不重连）均为可计时的实测断言。",
                               "basis": "依据 2026-10-30 用户真机反馈原话与 play.js 现状（仅 onclose 重连）。声明式审核。"})
    rid20, r20, d20 = add_req(REQ20, "20", ["SRC-000004", src],
                              "登记 10Hz 快照直接绘制造成的整块跳步，改为插值渲染",
                              {"necessity_review": "必要性：位置只有 10Hz 且取整，直接绘制必然 11px 阶跃；用户明确感到不连续。",
                               "completeness_review": "完整性：15 类字段齐全；纳入 4 条、排除 4 条（不做预测/外推/提频/缓动）、边界 3 条；页面归属 PAGE-000002 世界画布区；开放问题为空。",
                               "acceptance_review": "验收：4 条（逐帧最大位移、相机非零帧占比、停下收敛、像素对齐）都可在页面内 rAF 采样判定。",
                               "basis": "依据 Unity Netcode Interpolation / Photon Bolt Interpolation 文档与当前 10Hz+取整实现。声明式审核。"})
    rid21, r21, d21 = add_req(REQ21, "21", ["SRC-000004", src],
                              "登记「远处角色按半径消失」的取消：WS 全量下发",
                              {"necessity_review": "必要性：单世界数量有限，半径裁剪只换来「角色凭空消失」的观感缺陷。",
                               "completeness_review": "完整性：15 类字段齐全；纳入 3 条、排除 3 条（不动 /state 半径/不做 AOI/不做带宽优化）、边界 2 条；页面归属附近动物提示区；开放问题为空。",
                               "acceptance_review": "验收：3 条（700px 互见、绘制集合=收到集合、/state 仍按半径）分别钉住服务端与前端与 Agent 三侧。",
                               "basis": "依据用户原话「走得远了还是会有其他角色判断消失，这个可以不用有」与 ws.js 现状。声明式审核。"})
    r18, d18 = revise_18(src, "取消已失效的「客户端请求快照半径」口径，半径移交 REQ-000021",
                         {"necessity_review": "必要性：全量下发后客户端不再请求半径，原口径会误导实现与验收。",
                          "completeness_review": "完整性：只改与半径请求相关的 included/technical/AC-000073 与 normal_behavior 措辞；6 条条件 ID 与其余字段不变。",
                          "acceptance_review": "验收：AC-000070/071/072/075 不变；AC-000073 改为「快照全量 + 绘制⊆快照」，由 evidence/visible.json 复验。",
                          "basis": "依据 REQ-000021 与用户原话。声明式审核。"})

    doc = show({"type": "ledger"})
    o = doc["object"]
    rev = doc["document_revision"]
    cur = {r["id"]: r["revisions"][-1] for r in o["requirements"]}
    actions = [
        {"type": "新增", "requirement_id": rid19, "old_revision": None, "new_revision": r19},
        {"type": "新增", "requirement_id": rid20, "old_revision": None, "new_revision": r20},
        {"type": "新增", "requirement_id": rid21, "old_revision": None, "new_revision": r21},
        {"type": "替换", "requirement_id": "REQ-000018", "old_revision": 2, "new_revision": r18},
    ]
    retests = []
    for rid, rv in ((rid19, r19), (rid20, r20), (rid21, r21), ("REQ-000018", r18)):
        for a in cur[rid]["acceptance"]:
            retests.append({"requirement_id": rid, "revision": rv, "condition_id": a["id"]})
    print("retests:", len(retests), [r["condition_id"] for r in retests])

    code, body = call(["change", "propose"], {
        "operation_id": "r19-chg-propose", "agent": "octie-agent",
        "reason": "把真机反馈的三条修复与 REQ-000018 修订纳入新基线",
        "expected_revision": rev,
        "data": {"predecessor": pred, "actions": actions,
                 "impact_objects": [rid19, rid20, rid21, "REQ-000018"]},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "r19-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与重验清单", "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "impact_analysis": (
                     "三处实现改动：①play.js 连接管理（看门狗 + 可见性事件 + 显式重建），只影响前端连接生命周期；"
                     "②play.js 渲染管线改为插值（含相机），不影响服务端位置权威；③world.buildState 增加 scope='all'，"
                     "ws.js 走全量下发、REST /state 不变，前端删掉半径请求。服务端权威移动、卡片管线、CLI/技能、"
                     "单机版均未改动。REQ-000018 只改与半径请求相关的措辞。重验 = 三条新需求全部条件 + "
                     "REQ-000018 全部 6 条（被替换需整套重验）。"),
                 "retests": retests},
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "r19-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 做变更审核", "expected_revision": rev,
        "data": {"target_type": "change", "target_id": chg,
                 "target_revision": ch["revision"], "target_digest": ch["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：四条都是真机上可复现的缺陷（断连常驻、角色与镜头跳步、远处角色消失），且都不需要改服务端权威模型。",
                 "completeness_review": f"完整性：4 个动作（3 新增 + 1 替换）；候选成员 = 前驱全部成员 + 这 4 条；{len(retests)} 项重验逐条对应条件 ID。",
                 "acceptance_review": "验收：逐帧采样（rAF）、连接恢复计时、远距离互见与 /state 半径对照，均为可执行的实测断言；本审核不声称已执行。",
                 "basis": f"依据 {chg} 评估后摘要 {ch['digest'][:12]}…。声明式审核。"},
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        ch = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"r19-chg-{act}", "agent": "octie-agent",
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
        "operation_id": "r19-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {"target_type": "baseline", "target_id": cand["id"],
                 "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：三条新需求与一条修订需要与既有成员一起冻结成可发布快照。",
                 "completeness_review": f"成员完整：{len(cand['members'])} 个，其余保持前驱修订。",
                 "acceptance_review": f"{len(retests)} 项重验尚未登记执行结果，属后续验收环节，本审核不声称其已通过。",
                 "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}…。声明式审核。"},
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "r19-base-activate", "agent": "octie-agent",
        "reason": "候选基线已审核通过，激活为当前有效基线", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1

    ids = {"change": chg, "baseline": cand["id"], "version": cand.get("version"),
           "requirements": {rid19: r19, rid20: r20, rid21: r21, "REQ-000018": r18},
           "conditions": [r["condition_id"] for r in retests]}
    with open(IDS_OUT, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    print("done. doc_rev:", body["document_revision"], "| change:", chg, "| baseline:", cand["id"])
    print("ids →", IDS_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
