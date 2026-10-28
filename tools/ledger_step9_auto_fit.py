"""把 REQ-000007 的 5 条验收条件逐条登记到台账。

用 python 直接走 stdin，避免 PowerShell 把 JSON 里的双引号吃掉；
expected_revision 从每次响应里的 document_revision 递推，不手算。
每条都是「声明式登记」：actual/method/evidence 来自 evidence/req7_*.json 的真实测量。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
BASELINE = "BASE-000006"
REQ = "REQ-000007"
REV = 1
CYCLE = 1
DELIVERY = "crab-coast-v6"
IMPLEMENTED = "EVT-000162"

RECORDS = [
    {
        "condition_id": "AC-000027",
        "result": "通过",
        "actual": "把 visualViewport.height 由 390 覆写为 460（模拟浏览器工具栏收起，全程不派发任何事件）后静置 700ms：__probe.viewBox() 变为 {w:844,h:460}，画布由 693×390 自动变为 818×460，__probe.fitCount() 由 3 增至 4，期间没有任何用户点击。",
        "method": "移动模拟（844×390、hasTouch）下用 Object.defineProperty 覆写 visualViewport.height，读取 __probe.canvasRect() / viewBox() / fitCount()。",
        "evidence": "evidence/req7_landscape.json 步骤 1→2；另于本地 8099 与线上 ?v=10 各复测一次，结果一致",
    },
    {
        "condition_id": "AC-000028",
        "result": "通过",
        "actual": "把 visualViewport.height 由 460 改回 390（同样不发事件）后静置 700ms：画布自动由 818×460 回到 693×390，fitCount 由 4 增至 5。",
        "method": "与上一条同一套覆写手段，反向修改高度后读取画布尺寸与 fitCount。",
        "evidence": "evidence/req7_landscape.json 步骤 2→3",
    },
    {
        "condition_id": "AC-000029",
        "result": "通过",
        "actual": "依次派发 visualViewport 的 resize、window 的 resize、window 的 pageshow：fitCount 分别 +1、+1、+1；随后静置 900ms，fitCount 增量为 0（不空转）。",
        "method": "派发合成事件并在每步后读取 __probe.fitCount() 的增量。",
        "evidence": "evidence/req7_landscape.json 的 events 字段：{vvResize:1, windowResize:1, pageshow:1, idle900ms:0}",
    },
    {
        "condition_id": "AC-000030",
        "result": "通过",
        "actual": "竖屏 390×844 下画布为 390×219（宽度完全铺满，改动前为 382×215）；横屏 844×390 下画布为 693×390（高度完全铺满，改动前为 652×367）。收起虚拟按键后操作带由 236px 归零、场景重新居中，再展开恢复原状。",
        "method": "在两个移动视口下读取 __probe.canvasRect() 与 innerWidth/innerHeight，并调用 __touch.hide()/show() 观察居中变化。",
        "evidence": "evidence/req7_portrait.json（竖屏与收起/恢复）、evidence/req7_landscape.json（横屏）",
    },
    {
        "condition_id": "AC-000031",
        "result": "通过",
        "actual": "桌面 852×875 视口（未做触屏模拟，html 无 touch-mode、无触屏覆盖层）下画布为 835×470，与 0.98/0.94 公式计算值 835×470 逐像素一致，铺满逻辑未误用在桌面。",
        "method": "在未模拟触屏的桌面页读取 __probe.canvasRect() 与 __probe.viewBox()，并用同一公式计算期望值比较。",
        "evidence": "evidence/req7_desktop.json",
    },
]


def run(payload):
    proc = subprocess.run(
        ["cmd", "/c", "reqledger", "acceptance", "record", "--file", LEDGER, "--stdin"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    try:
        return proc.returncode, json.loads(out)
    except json.JSONDecodeError:
        return proc.returncode, {"_raw": out, "_err": proc.stderr.decode("utf-8", "replace")}


def main():
    # 先取当前文档修订
    proc = subprocess.run(
        ["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
        input=b'{"type":"ledger"}', capture_output=True)
    doc = json.loads(proc.stdout.decode("utf-8", "replace"))
    rev = doc["document_revision"]
    print("start doc_rev:", rev)

    for r in RECORDS:
        payload = {
            "operation_id": f"crab-req7-acc-{r['condition_id']}",
            "agent": "octie-agent",
            "reason": "按实测数据登记该条件的验收结果",
            "expected_revision": rev,
            "data": {
                "baseline_id": BASELINE,
                "requirement_id": REQ,
                "revision": REV,
                "cycle": CYCLE,
                "condition_id": r["condition_id"],
                "delivery_id": DELIVERY,
                "implemented_event_id": IMPLEMENTED,
                "evidence": r["evidence"],
                "actual": r["actual"],
                "method": r["method"],
                "result": r["result"],
            },
        }
        code, body = run(payload)
        ok = body.get("type") == "success"
        print(f"{r['condition_id']}: exit={code} type={body.get('type')} "
              f"doc_rev={body.get('document_revision')} id={(body.get('object') or {}).get('id')}")
        if not ok:
            print("  issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:600])
            return 1
        rev = body["document_revision"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
