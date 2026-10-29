"""手机端相机裁切视角（REQ-000018）+ 修正 REQ-000011 的渲染口径（r3）。

用户决定：Agent 的 nearby 判据保留；人的视角改为相机裁切跟随 + 世界边界钳制。
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
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')} r={o.get('revision')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:800])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


PLACEMENT = {"kind": "页面", "other": [], "primary": {"page_id": "PAGE-000002", "page_revision": 1,
                                                      "region_id": "REG-000002-0001-0001"}}
SRC = [{"source_id": "SRC-000004", "source_revision": 1},
       {"source_id": "SRC-000005", "source_revision": 1}]

REQ18 = {
    "title": "手机端相机裁切：自己居中跟随，世界边界处相机停住",
    "type": "功能", "module": "多人前端", "priority": "P0", "placement": PLACEMENT,
    "sources": SRC, "questions": [],
    "description": "多人前端在手机上不再整幅显示 960×540 的世界，而是用一块与设备视口等大的相机窗口（1 逻辑像素 = 1 CSS 像素）裁切世界，并把操作者自己的动物放在窗口中心。相机随动物移动而平移；当相机窗口触及世界边界（0 与 960/540）时相机停止，画面不再移动，动物继续朝屏幕边缘移动直到贴住世界边界。视野内的其它动物全部绘制，不再按半径 200 决定可见性；半径判据仅保留给 Agent 的 /state 接口（Agent 无法截图，靠它读取附近角色）。为保证「屏幕上看得见的一定收到过」，客户端按「相机视野半对角」向服务端请求快照半径，服务端仍按 RADIUS_MAX 钳制。",
    "purpose": "让手机上的每一帧都是「自己的世界」：看得清角色、看得到身边的其它动物，且世界边界有明确的空间感。",
    "necessity": "整幅渲染在手机上把 48px 角色压到约 20px，几乎看不清；而按半径 200 裁剪又在全图上留出一圈「凭空消失/出现」的可见边界，看起来像 bug。两条只有相机裁切能同时解决。",
    "included": [
        "相机窗口尺寸 = 画布 CSS 尺寸（1 逻辑像素 = 1 CSS 像素），居中跟随自己的动物",
        "相机在世界范围 [0, worldW-viewW] × [0, worldH-viewH] 内钳制，到边界即停",
        "边界处动物继续移动到世界边界，画面保持不动",
        "视野内其它动物全部绘制，不按半径 200 隐藏",
        "客户端按相机视野半对角请求快照半径，服务端按 RADIUS_MAX 钳制并回显实际半径",
    ],
    "excluded": [
        "相机缩放（固定 1:1，不做 zoom）",
        "相机旋转与平滑跟随缓动（直接跟随）",
        "Agent 侧半径语义的改动（/state 仍默认 200）",
    ],
    "normal_behavior": {
        "scenario": "手机竖屏 390×844 打开 /play，动物位于世界中部",
        "behavior": "相机以动物为中心裁切 390×220 的世界窗口并绘制",
        "expected": "动物始终在画面中心，移动时背景与其它动物相对平移，镜头不会跳出世界边界",
    },
    "boundaries": [
        {"scenario": "动物走到世界左/上边缘", "expected": "相机停在 0，动物继续移动到贴边，画面不再左移", "handling": "相机坐标钳制到 [0, world-view]"},
        {"scenario": "动物走到世界右/下边缘", "expected": "相机停在 world-view，动物继续移动到贴边", "handling": "同上"},
        {"scenario": "视野大于世界（极端小屏或放大设备）", "expected": "整幅世界居中显示，相机不再移动", "handling": "相机尺寸超过世界时取世界尺寸并居中"},
        {"scenario": "视野内出现其它动物", "expected": "必然在本次快照的 nearby 内", "handling": "客户端请求半径 = 视野半对角 + 余量"},
    ],
    "acceptance": [
        ac("前端验收者", "自己始终居中且相机跟随", "手机视口 390x844，动物在中部",
           "按住方向键走 1 秒", "对比移动前后动物屏幕坐标与背景偏移",
           "动物屏幕坐标偏差 ≤2px（保持居中）；背景与其它动物的屏幕坐标按相反方向平移相同距离",
           ("动物跑出中心或背景不动", "判定相机未跟随", "检查 camera.x/y 的更新与绘制偏移"),
           "CDP 读取画布像素坐标与相机偏移", "evidence/camera.json 中居中与位移断言"),
        ac("前端验收者", "世界左/上边界相机停住、动物继续走", "动物被放在世界左上角附近",
           "持续向左/向上移动 2 秒", "读相机坐标与动物屏幕坐标",
           "相机停在 (0,0)；动物屏幕坐标继续减小到贴边（≥0）；背景不再平移",
           ("相机继续移动或露出世界外空白", "判定钳制缺失", "相机坐标 clamp 到 [0, world-view]"),
           "读相机与动物屏幕坐标", "evidence/camera.json 中左/上边界断言"),
        ac("前端验收者", "世界右/下边界同样停住", "动物被放在世界右下角附近",
           "持续向右/向下移动 2 秒", "读相机坐标与动物屏幕坐标",
           "相机停在 (worldW-viewW, worldH-viewH)；动物屏幕坐标继续增大到贴边",
           ("相机越过 world-view", "判定钳制上下界不一致", "检查 clamp 上界"),
           "同上", "evidence/camera.json 中右/下边界断言"),
        ac("接口验收者", "视野内的动物一定被发送过", "两名动物相距小于视野半对角",
           "动物 A 的页面打开并读最近一次快照", "比对 nearby 中的 id 与画面中实际绘制的 id 集合",
           "画面里绘制的 id 集合是 nearby 的子集，缺失为 0（视野内可见 ⇒ 必在快照内）",
           ("画面上有，nearby 里没有", "判定请求半径不足", "客户端半径改由相机半对角推导"),
           "页面内比较绘制集合与快照集合", "evidence/camera.json 中可见/收到一致性断言"),
        ac("接口验收者", "Agent 侧半径语义不变", "Agent 调 /state 不传 radius",
           "读取 world.radius 与 nearby 半径", "校验默认值与钳制",
           "默认 radius=200；传 10000 时回显 400；均与相机无关",
           ("默认值被相机逻辑改写", "判定服务端被耦合", "半径默认值保持常量"),
           "CLI state 调两次（默认 / 10000）", "evidence/camera.json 中 agentRaidus 断言"),
    ],
    "technical": "play.js 新增 camera{x,y,w,h} 与 worldToScreen()；画布 width/height 设为相机尺寸并按 devicePixelRatio 处理；bg 用 drawImage 子矩形绘制；快照请求半径 = ceil(hypot(w,h)/2)+8。",
}


def lifecycle_add(data, tag):
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    code, body = call(["req", "add"], {"operation_id": f"cam-{tag}-add", "agent": "octie-agent",
                                       "reason": "登记相机裁切视角需求", "expected_revision": rev, "data": data})
    if not ok(f"add {tag}", code, body):
        raise SystemExit(1)
    rev = body["document_revision"]
    rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]
    steps = [
        (["req", "submit"], {"id": rid, "revision": rrev, "digest": digest}, "octie-agent", "转入待审核"),
        (["review", "add"], {
            "target_type": "requirement", "target_id": rid, "target_revision": rrev,
            "target_digest": digest, "conclusion": "通过",
            "necessity_review": "必要性：整幅渲染把角色压到约 20px 看不清，按半径裁剪又在全图上留下可见的凭空消失边界；相机裁切同时解决清晰度与边界语义。",
            "completeness_review": "完整性：15 类字段齐全；纳入 5 条、排除 3 条（不做缩放/缓动/不改 Agent 半径）、边界 4 条；页面归属 PAGE-000002；开放问题为空。",
            "acceptance_review": "验收：5 条覆盖居中跟随、左/上钳制、右/下钳制、可见⊆已收到、Agent 半径不变，均为可断言的坐标/集合关系。",
            "basis": f"依据 {rid} 第 {rrev} 修订摘要 {digest[:12]}… 与用户 2026-10-30 的口述规则审阅。声明式审核。",
        }, "review-agent", "语义审核"),
        (["req", "confirm"], {"id": rid, "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}},
         "octie-agent", "确认纳入"),
    ]
    opname = {"submit": "submit", "add": "review", "confirm": "confirm"}
    for args, data2, agent, why in steps:
        code, body = call(args, {"operation_id": f"cam-{tag}-{opname[args[1]]}", "agent": agent,
                                 "reason": why, "expected_revision": rev, "data": data2})
        if not ok(f"{args[1]} {tag}", code, body):
            raise SystemExit(1)
        rev = body["document_revision"]
    return rid, rev


def revise_11():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    cur = [r for r in doc["object"]["requirements"] if r["id"] == "REQ-000011"][0]["revisions"][-1]
    data = {k: cur[k] for k in ("title", "description", "purpose", "necessity", "type", "module",
                               "priority", "placement", "included", "excluded", "normal_behavior",
                               "boundaries", "questions", "technical")}
    data["sources"] = [{"source_id": s["source_id"], "source_revision": s["source_revision"]} for s in cur["sources"]]
    data["acceptance"] = [{**{k: a[k] for k in AC_FIELDS}, "id": a["id"]} for a in cur["acceptance"]]
    data["included"] = [x for x in data["included"] if "10Hz" not in x] + [
        "10Hz 快照渲染（自己 + 视野内动物；视野由相机裁切决定，见 REQ-000018）",
    ]
    data["description"] = (data["description"].replace(
        "页面同时绘制半径 200 逻辑像素内的其他动物（含朝向帧）",
        "页面用相机裁切窗口绘制视野内的其他动物（含朝向帧）；半径 200 的判据仅用于 Agent 的 /state 接口（REQ-000018）"))
    data["id"] = "REQ-000011"
    data["base_revision"] = cur["revision"]
    code, body = call(["req", "revise"], {"operation_id": "cam-rev11", "agent": "octie-agent",
                                          "reason": "渲染口径改为相机裁切，半径判据只留给 Agent", "expected_revision": rev, "data": data})
    if not ok("revise REQ-000011", code, body):
        return 1
    rev = body["document_revision"]
    rrev, digest = body["object"]["revision"], body["object"]["digest"]
    for args, agent, why in (
        (["req", "submit"], "octie-agent", "修订转入待审核"),
        (["review", "add"], "review-agent", "渲染口径修订审核"),
        (["req", "confirm"], "octie-agent", "确认纳入"),
    ):
        if args[1] == "add":
            data2 = {"target_type": "requirement", "target_id": "REQ-000011", "target_revision": rrev,
                     "target_digest": digest, "conclusion": "通过",
                     "necessity_review": "必要性不变：浏览器要给用户可玩的视图。",
                     "completeness_review": "完整性：只改渲染口径（视野由相机决定），半径语义移交给 REQ-000018；条件 ID 与其余字段未变。",
                     "acceptance_review": "验收：原 4 条条件不变，其中「看到附近动物」的判定改由 REQ-000018 的可见⊆已收到约束保证。",
                     "basis": f"依据 REQ-000011 第 {rrev} 修订摘要 {digest[:12]}…。声明式审核。"}
        elif args[1] == "submit":
            data2 = {"id": "REQ-000011", "revision": rrev, "digest": digest}
        else:
            data2 = {"id": "REQ-000011", "revision": rrev, "digest": digest, "scope": {"decision": "纳入"}}
        code, body = call(args, {"operation_id": f"cam-rev11-{"review" if args[1] == "add" else args[1]}", "agent": agent,
                                 "reason": why, "expected_revision": rev, "data": data2})
        if not ok(f"rev11 {args[1]}", code, body):
            return 1
        rev = body["document_revision"]
    return rev


def main():
    rid, rev = lifecycle_add(REQ18, "18")
    print("REQ-000018:", rid, "doc_rev", rev)
    rev = revise_11()
    print("done. doc_rev:", rev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
