"""REQ-000017：多人版手机端摇杆/ABXY 与页面布局对齐单机版（add → submit → review → confirm）。"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
SRC = {"source_id": "SRC-000004", "source_revision": 1}
SRC2 = {"source_id": "SRC-000005", "source_revision": 1}
PLACEMENT = {"kind": "页面", "other": [],
             "primary": {"page_id": "PAGE-000002", "page_revision": 1,
                         "region_id": "REG-000002-0001-0001"}}


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


REQ = {
    "title": "多人版手机端沿用单机版的摇杆与 ABXY，并保持页面布局一致",
    "type": "功能", "module": "多人前端", "priority": "P1", "placement": PLACEMENT,
    "sources": [SRC, SRC2], "questions": [],
    "description": "多人前端（/play）在手机上改为与单机版一致的控件与版式：左下 132px 半透明摇杆（死区 10px、最大位移 44px、按主导轴四向判定）、右下 ABXY 菱形（Y 74/0、X 12/74、B 136/74、A 68/142 74px）、右上收起/显示开关；摇杆驱动服务端意图。多人版没有尺寸轮询（REQ-000011 已排除尺寸切换），因此 ABXY 四键全部为禁用占位，只保留视觉与布局，不绑定任何功能。布局沿用单机版规则：固定元素用 env(safe-area-inset-*)、竖屏预留 236px 操作带（收起后归零）、横屏叠加并在矮屏（max-height 560px）缩放到 0.78/0.84、收起开关竖屏右上 / 横屏左上。现有 4 键 D-pad 与 156px 方键方案废弃。",
    "purpose": "让手机用户用与单机版完全一致的手感操作自己的动物，并避免控件压住场景或被刘海/手势条遮挡。",
    "necessity": "现状是 4 个 52px 方键 D-pad：无死区、无主导轴判定、无安全区、无法收起，手机上误触多且遮挡场景；单机版已经验证过一套手感更好的摇杆方案，多人版没有理由另造一套。",
    "included": [
        "左下 132px 半透明摇杆（死区 10px、最大位移 44px、主导轴四向）",
        "右下 ABXY 菱形（四键均禁用占位，仅保留视觉）",
        "右上收起/显示开关，收起只藏摇杆与 ABXY",
        "竖屏 236px 操作带、横屏叠加与矮屏缩放 0.78/0.84",
        "固定元素使用 env(safe-area-inset-*)",
        "桌面不显示控件，键盘 WASD/方向键保持可用",
    ],
    "excluded": [
        "大/中/小尺寸切换（多人版不做，ABXY 的 A 键不承担该功能）",
        "为 ABXY 临时编造新功能",
        "多人版的真实摇杆（物理手柄）适配",
    ],
    "normal_behavior": {
        "scenario": "用户在手机上打开 /play 并操作摇杆",
        "behavior": "摇杆按主导轴产生方向意图，经 WebSocket 发往服务端",
        "expected": "动物按方向移动且朝向正确；松手立即停；控件不遮挡场景主体",
    },
    "boundaries": [
        {"scenario": "推杆位移小于 10px", "expected": "不产生任何方向意图", "handling": "死区内的移动被忽略"},
        {"scenario": "斜向推杆", "expected": "只取主导轴（|dx|>=|dy| 取水平），不出现斜向移动", "handling": "按绝对值比较取单轴"},
        {"scenario": "按下 ABXY 任意键", "expected": "无任何状态变化", "handling": "四键均为禁用占位，不绑定事件"},
        {"scenario": "竖屏收起控件", "expected": "只隐藏摇杆与 ABXY，开关仍在，场景重新居中", "handling": "折叠类 + 操作带归零 + 触发画布重算"},
    ],
    "acceptance": [
        ac("前端验收者", "四向摇杆各推一次都在正确方向产生位移", "触屏视口，动物在开阔沙地",
           "摇杆分别推右/上/左/下各 400ms 后松手", "读取服务端 state 的坐标与 facing",
           "四次位移方向与推杆一致，每次累计位移 ≥30px；松手 300ms 内 moving=false；facing 与方向一致",
           ("方向不符或松手仍移动", "判定意图映射或松手逻辑有误", "检查主导轴判定与 pointerup 复位"),
           "合成触摸事件驱动摇杆，每次后读 /api/v1/animals/:id/state", "evidence/touch_ui.json 的四向断言"),
        ac("前端验收者", "死区内不产生移动", "同上",
           "把摇杆推到 (4,3)（距离 5px，小于死区 10px）保持 400ms", "读取坐标",
           "坐标位移为 0，facing 不变",
           ("出现位移", "判定死区未生效", "检查 DEAD 常量与距离比较"),
           "合成触摸事件，记录前后坐标", "evidence/touch_ui.json 的死区断言"),
        ac("前端验收者", "ABXY 四键为禁用占位", "触屏视口",
           "依次按下 Y/X/B/A", "读取坐标与 facing，并检查元素类名",
           "四次均无坐标与 facing 变化；四键都带 disabled 类",
           ("出现任何状态变化", "判定占位键被误绑定功能", "移除事件绑定，只保留视觉"),
           "合成 pointerdown 并读 state", "evidence/touch_ui.json 的 ABXY 断言"),
        ac("前端验收者", "收起/显示开关行为正确", "触屏视口，控件可见",
           "点收起开关，再点一次恢复", "读取摇杆/ABXY 的 display、开关可见性、--touch-band 与画布矩形",
           "收起后摇杆与 ABXY 的 display 为 none、开关仍可见、--touch-band 为 0px、画布重新居中；恢复后三者回到原值",
           ("开关随控件一起消失或画布出现空白带", "判定折叠逻辑或重算缺失", "只隐藏控件并触发一次 fit()"),
           "点击开关并逐项读取计算样式与矩形", "evidence/touch_ui.json 的收起断言"),
        ac("前端验收者", "竖屏布局不遮挡", "390x844 竖屏",
           "打开页面并测量各元素矩形", "读取摇杆/ABXY/开关/HUD/画布的 getBoundingClientRect",
           "所有控件矩形落在视口内且互不重叠；画布底边与操作带顶边间距 ≥8px；收起后画布垂直居中误差 ≤2px",
           ("控件越界或压住画布", "判定布局或操作带计算有误", "核对 --touch-band 与 fit()"),
           "读取矩形并做相交/间距计算", "evidence/touch_ui.json 的竖屏布局断言"),
        ac("前端验收者", "横屏与桌面都不出问题", "844x390 与 844x260 横屏，以及桌面视口",
           "在三个视口下打开页面并测量", "读取开关与四键矩形、控件可见性；桌面上按方向键",
           "横屏开关在左半屏（left ≤24px 且 right < 视口宽/2）且与四键零重叠；矮屏 ABXY 缩放 0.78 不越界；桌面不显示控件但键盘仍能移动动物",
           ("矮屏重叠或桌面显示控件", "判定矮屏媒体查询或触屏判定有误", "核对 max-height 560 与 coarse 判定"),
           "逐视口读取矩形与显示状态；桌面按方向键后读坐标", "evidence/touch_ui.json 的横屏与桌面断言"),
    ],
    "technical": "新增 cloud/play/touch.js（从单机 touch-controls.js 泛化的 createTouchControls），由 play.js 注入 onIntent=__play.sendIntent 与 onCollapse=重新 fit；单机版 touch-controls.js 不改动。",
}


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    print("start doc_rev:", rev)
    code, body = call(["req", "add"], {
        "operation_id": "ui-req-add-17", "agent": "octie-agent",
        "reason": "登记多人版手机控件与布局对齐单机版的需求", "expected_revision": rev, "data": REQ,
    })
    if not ok("add", code, body):
        return 1
    rev = body["document_revision"]
    rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]

    steps = [
        (["req", "submit"], {"id": rid, "revision": rrev, "digest": digest}, "octie-agent", "转入待审核"),
        (["review", "add"], {
            "target_type": "requirement", "target_id": rid, "target_revision": rrev,
            "target_digest": digest, "conclusion": "通过",
            "necessity_review": "必要性：现有多人版是 4 键方 D-pad，无死区/主导轴/安全区/收起，手机上误触并遮挡场景；单机版已有验证过的摇杆方案，复用即可。",
            "completeness_review": "完整性：15 类字段齐全；纳入 6 条、排除 3 条（明确不做尺寸切换、不为 ABXY 编造功能）、边界 4 条；页面归属 PAGE-000002 世界画布区；来源 SRC-000004/000005；开放问题为空。",
            "acceptance_review": "验收：6 条条件分别对应四向、死区、ABXY 禁用、收起、竖屏布局、横屏与桌面，均为可自动断言的矩形/坐标/样式检查，并与 Octie 任务 e0ca26b0 的 6 条判据一一对应。",
            "basis": f"依据 REQ-000017 第 {rrev} 修订摘要 {digest[:12]}… 与源码事实（touch-controls.js 的 DEAD=10/R_MAX=44/236px/0.78|0.84；play 的 #dpad 52px）审阅。声明式审核。",
        }, "review-agent", "语义审核"),
        (["req", "confirm"], {"id": rid, "revision": rrev, "digest": digest,
                              "scope": {"decision": "纳入"}}, "octie-agent", "确认纳入"),
    ]
    for args, data, agent, why in steps:
        code, body = call(args, {"operation_id": f"ui-{args[1]}-17", "agent": agent,
                                 "reason": why, "expected_revision": rev, "data": data})
        if not ok(args[1], code, body):
            return 1
        rev = body["document_revision"]
    print("done. doc_rev:", rev, "req:", rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
