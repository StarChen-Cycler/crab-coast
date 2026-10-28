"""为 CHG-000005 的重验义务登记本交付（crab-coast-v6）的执行结果。

覆盖 REQ-000001（AC-000001/2/3，轮次 2）与 REQ-000004（AC-000012/13/14，轮次 2）。
数据全部来自页面内实测（pageId 8，线上 ?v=10）。
"""
import json
import subprocess
import sys

LEDGER = "requirements.md"
BASELINE = "BASE-000006"
DELIVERY = "crab-coast-v6"

RECORDS = [
    # ---- REQ-000001 r1 / cycle 2 ----
    {
        "requirement_id": "REQ-000001",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000064",
        "condition_id": "AC-000001",
        "actual": "线上 ?v=10 画面可逐一指出海水（上方整片）、沙滩（中部大片沙地）、红树林（左上与中部气根树丛）、海藻床（水中成片海草）、珊瑚礁（浅水区礁石）、台阶（左侧木台阶）、高脚屋（右侧木屋）共 7 类元素，无缺失。",
        "method": "截取整页画面，按七类元素清单逐项勾选并标注位置；同时在画布上确认元素分布区域。",
        "evidence": "evidence/req7_scene_seven.png（线上 ?v=10 全屏截图，七类元素均可见）",
        "result": "通过",
    },
    {
        "requirement_id": "REQ-000001",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000064",
        "condition_id": "AC-000002",
        "actual": "冻结环境动画后，对沙地区域 (150,350)-(300,450) 取值，按住右键移动 800ms 前后比较：该区域 15000 个像素中变化 0 个，背景位移为 0。",
        "method": "调用 __probe.freeze(true) 冻结海浪等环境动画，用 canvas getImageData 取同一块沙地像素，移动角色后再取一次做逐像素比较。",
        "evidence": "本次测量的返回值 {bgDiffPixels: 0, regionPixels: 15000}，执行记录见本表",
        "result": "通过",
    },
    {
        "requirement_id": "REQ-000001",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000064",
        "condition_id": "AC-000003",
        "actual": "解冻后对水面区域 (100,60)-(400,160) 连续取值三次（间隔 1 秒）：相邻两帧分别有 272 / 269 个像素发生变化（占 30000 的约 0.9%），变化集中在波浪纹理上，没有整幅跳动或闪烁。",
        "method": "用 canvas getImageData 对同一水面区域间隔 1 秒连续取样三次，统计相邻帧差异像素数量并观察其占比。",
        "evidence": "本次测量的返回值 {diff_1v2: 272, diff_2v3: 269, waterRegion: 30000}",
        "result": "通过",
    },
    # ---- REQ-000004 r1 / cycle 2 ----
    {
        "requirement_id": "REQ-000004",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000070",
        "condition_id": "AC-000012",
        "actual": "线上页面共 10 个资源请求，来源全部为页面自身 origin（starchen-cycler.github.io 下的相对路径），外部域名请求 0 个。",
        "method": "读取 performance.getEntriesByType('resource')，逐条比对是否属于 location.origin。",
        "evidence": "本次测量的返回值 {totalRequests: 10, external: [], sameOriginOnly: true}",
        "result": "通过",
    },
    {
        "requirement_id": "REQ-000004",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000070",
        "condition_id": "AC-000013",
        "actual": "按住右键移动，连续三轮各 5 秒：平均帧率均为 82.5 fps，>50ms 长帧均为 0 次。",
        "method": "每轮先 __probe.resetStats()，按住右键 5 秒后读 __probe.fps() 与 __probe.longFrames()，共三轮。",
        "evidence": "本次测量返回值 {runs:[{fps:82.5,longFrames:0},{fps:82.5,longFrames:0},{fps:82.5,longFrames:0}]}",
        "result": "通过",
    },
    {
        "requirement_id": "REQ-000004",
        "revision": 1,
        "cycle": 2,
        "implemented_event_id": "EVT-000070",
        "condition_id": "AC-000014",
        "actual": "画布 2D 上下文 imageSmoothingEnabled = false，CSS image-rendering = crisp-edges，且绘制使用最近邻放大，像素边缘为硬边。",
        "method": "读取 canvas.getContext('2d').imageSmoothingEnabled 与 getComputedStyle(canvas).imageRendering。",
        "evidence": "本次测量返回值 {imageSmoothingEnabled: false, imageRendering: 'crisp-edges'}；另见 evidence/req7_scene_seven.png 中的硬边像素",
        "result": "通过",
    },
]


def call(args, payload):
    proc = subprocess.run(["cmd", "/c", "reqledger"] + args + ["--file", LEDGER, "--stdin"],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, (json.loads(out) if out.startswith("{") else {"_raw": out})


def main():
    _, doc = call(["show"], {"type": "ledger"})
    rev = doc["document_revision"]
    print("start doc_rev:", rev)

    for r in RECORDS:
        payload = {
            "operation_id": f"crab-retest-{r['requirement_id']}-{r['condition_id']}",
            "agent": "octie-agent",
            "reason": "CHG-000005 重验义务：按实测数据登记本交付的执行结果",
            "expected_revision": rev,
            "data": {
                "baseline_id": BASELINE,
                "requirement_id": r["requirement_id"],
                "revision": r["revision"],
                "cycle": r["cycle"],
                "condition_id": r["condition_id"],
                "delivery_id": DELIVERY,
                "implemented_event_id": r["implemented_event_id"],
                "evidence": r["evidence"],
                "actual": r["actual"],
                "method": r["method"],
                "result": r["result"],
            },
        }
        code, body = call(["acceptance", "record"], payload)
        ok = body.get("type") == "success"
        print(f"{r['requirement_id']} {r['condition_id']}: exit={code} type={body.get('type')} "
              f"doc_rev={body.get('document_revision')} id={(body.get('object') or {}).get('id')}")
        if not ok:
            print("  issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:700])
            return 1
        rev = body["document_revision"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
