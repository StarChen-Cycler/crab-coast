"""逐条件验收（17 条）+ 发布 REL-000002 / crab-coast-v2。

每条验收的 cycle 与实现事件都按「需求ID + 内容修订」取：
  REQ-000001 r1 cycle2 EVT-000064
  REQ-000002 r1 cycle2 EVT-000066
  REQ-000003 r2 cycle1 EVT-000068
  REQ-000004 r1 cycle2 EVT-000070
  REQ-000005 r1 cycle1 EVT-000072
"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
BID = "BASE-000002"
DELIVERY = "crab-coast-v2"

PLAN = {
    "REQ-000001": {"revision": 1, "cycle": 2, "event": "EVT-000064"},
    "REQ-000002": {"revision": 1, "cycle": 2, "event": "EVT-000066"},
    "REQ-000003": {"revision": 2, "cycle": 1, "event": "EVT-000068"},
    "REQ-000004": {"revision": 1, "cycle": 2, "event": "EVT-000070"},
    "REQ-000005": {"revision": 1, "cycle": 1, "event": "EVT-000072"},
}

EVIDENCE = {
    "AC-000001": ("画面同时可见海水、沙滩、红树林、海藻床、珊瑚礁、台阶与栈道、高脚屋，共 7 类元素（当前背景为 AI 生成图）。",
                  "打开页面截图后按七类元素清单逐项核对。", "evidence/20_v2_initial.png"),
    "AC-000002": ("冻结环境动画后把角色从 x=200 移到 x=800，角色包围盒之外的差异像素为 0。",
                  "读取 canvas 像素两帧逐像素比对，排除角色包围盒。", "本轮实测 bgDiffOutside = 0"),
    "AC-000003": ("水面带（y 150–300）在 700ms 间隔内变化 0.663% 像素；水面闪光点 473 个、岸线碎浪点 135 个持续闪烁，无整幅跳变。",
                  "连续抓取水面区域两帧做逐像素差。", "本轮实测 waterRatioPct = 0.663，waterPoints = 473"),
    "AC-000004": ("四向各按 600ms：→ dx=+66.7 dy=0；← dx=-66 dy=0；↑ dy=-66 dx=0；↓ dy=+66.6 dx=0；朝向分别为 front/front/left/left。",
                  "每方向单独计时，记录起终点坐标与朝向。", "本轮实测 dirs"),
    "AC-000005": ("三次 1 秒向右位移均为 110 px，极差 0%，速度稳定在 110 px/s。",
                  "同一起点重复三次计时位移。", "本轮实测 speeds = 110/110/110"),
    "AC-000006": ("主沙滩是单一连通区（1511 格，像素范围 x 80–768、y 240–528）；四向持续移动后落点始终满足 canStand，未越出该区域。",
                  "对可走网格从出生点做 BFS 求连通区域，并在运行时检查落点可站立性。", "本轮实测 region = 1511 格 / [80,768,240,528]"),
    "AC-000007": ("四向均在松开按键后 stopped = true，帧索引回到 0。",
                  "松键后读取 moving 与 frame。", "probe_v2_full 输出 dirs[].stopped 均为 true"),
    "AC-000008": ("按住右键 1 秒，帧索引序列为 1230123，按 8 fps 连续循环，无跳帧与倒序。",
                  "在渲染循环中记录帧切换序列。", "本轮实测 frameSeq = 1230123"),
    "AC-000009": ("向右行走后改按向上，朝向由 front 切换为 left（侧视行），切换即时生效。",
                  "记录切向前后的朝向与所用行。", "本轮实测 dirs：Up 时 face=left"),
    "AC-000010": ("松开方向键后 frame 保持 0，动画停止推进。",
                  "松键后读取帧索引。", "本轮实测 stopped.frame = 0"),
    "AC-000011": ("自检脚本输出：16 帧全部 48×48、四角 alpha=0、同方向中心恒为 23.5、脚底基线 43、调色板 32 色、问题数 0。",
                  "运行 python tools/check_sheet.py（帧尺寸从 scene.json 读取）。", "tools/check_sheet.py 输出 + evidence/33_side_scale_preview.png"),
    "AC-000012": ("页面只请求本地资源（scene.js、main.js、bg_base.png、crab_sheet.png、music/bgm.js 与音频），无任何外部域名；用 file:// 直接打开同样可运行。",
                  "检查 Network 请求域名，并用 file:// 打开验证。", "本轮资源清单 + 早前 file:// 验证 evidence/11_file_protocol.png"),
    "AC-000013": ("移动期间平均帧率 164.8 fps。",
                  "持续按方向键时读取滚动平均帧率。", "本轮实测 fps = 164.8"),
    "AC-000014": ("canvas 的 imageSmoothingEnabled 为 false，CSS image-rendering 为 crisp-edges，放大后像素为硬边。",
                  "读取渲染上下文与计算样式。", "本轮实测 smoothing=false, css=crisp-edges"),
    "AC-000015": ("音频元素 duration 为 40（整 40.000 秒），loop 属性为 true。",
                  "读取 window.__bgm.audio 的 duration 与 loop。", "本轮实测 duration=40, loop=true"),
    "AC-000016": ("首尾采样跳变 0.0019，普通相邻采样差值 p99.9 为 0.413，比值 0.005，循环处无咔哒。",
                  "读取 PCM 计算接缝跳变与相邻差值分布。", "本轮脚本测量 0.0019 / 0.413"),
    "AC-000017": ("调用静音后 muted=true 且 audio.muted=true；再切回后两者同时为 false，按钮文案随状态变化，状态写入 localStorage。",
                  "调用 __bgm.setMuted 并读取状态。", "本轮实测 before=false / afterMute=true / afterUnmute=false"),
}


def call(argv, data=None):
    args = ["reqledger"] + argv + ["--file", F]
    if data is not None:
        args += ["--json", json.dumps(data, ensure_ascii=False)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        return p.returncode, json.loads(p.stdout.strip())
    except Exception:
        return p.returncode, {"raw": p.stdout.strip()[:400], "err": p.stderr[:300]}


def must(rc, obj, what):
    if rc != 0 or obj.get("type") == "error" or obj.get("commit_status") == "not_committed":
        print(f"\n!! {what} 失败 rc={rc}")
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:1500])
        raise SystemExit(1)
    print(f"   ✓ {what}")
    return obj


def main():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    r = o["current_document_revision"]

    rc, o = call(["show"], {"type": "requirement", "id": "REQ-000001"})
    # 逐需求拿条件列表
    total = 0
    for rid, info in PLAN.items():
        rc, o = call(["show"], {"type": "requirement", "id": rid})
        must(rc, o, f"读 {rid}")
        for ac in o["object"]["acceptance"]:
            cid = ac["id"]
            actual, method, ev = EVIDENCE[cid]
            rc, o = call(["acceptance", "record"], {
                "operation_id": f"acc2-{cid}", "agent": AGENT,
                "reason": "按本轮实测数据登记验收结果",
                "expected_revision": r,
                "data": {
                    "baseline_id": BID, "requirement_id": rid,
                    "revision": info["revision"], "cycle": info["cycle"],
                    "condition_id": cid, "delivery_id": DELIVERY,
                    "implemented_event_id": info["event"],
                    "actual": actual, "method": method, "result": "通过", "evidence": ev,
                },
            })
            must(rc, o, f"{cid}"); r = o["current_document_revision"]; total += 1

    print(f"\n共登记 {total} 条验收")

    members = [{"id": rid, "revision": info["revision"], "cycle": info["cycle"]}
               for rid, info in PLAN.items()]
    rc, o = call(["release", "add"], {
        "operation_id": "release-add-2", "agent": AGENT,
        "reason": f"V1.1 基线全部条件实测通过，登记交付 {DELIVERY}",
        "expected_revision": r,
        "data": {"baseline_id": BID, "delivery_id": DELIVERY, "members": members},
    })
    must(rc, o, "release add")
    rel = o["object"]
    print(f"\n发布：{rel.get('id')} 交付={rel.get('delivery_id')} 成员={len(rel.get('members', []))}")


if __name__ == "__main__":
    main()
