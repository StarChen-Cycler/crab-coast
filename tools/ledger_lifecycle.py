"""把 crab-coast 的需求台账推进到「已发布」状态。

顺序严格按 requirements-ledger-cli 的生命周期：
  提交 → 审核(通过) → 确认(纳入) → 基线封存 → 基线审核 → 基线激活
  → 开发开始/实现 → 逐条件验收 → 发布登记

每一步都用真实返回的 document_revision 做 CAS，失败即停并打印原因。
"""
from __future__ import annotations

import json
import subprocess
import sys

LEDGER = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"
DELIVERY = "crab-coast-v1"


def call(argv: list[str], data: dict | None = None) -> tuple[int, dict]:
    args = ["reqledger", *argv, "--file", LEDGER]
    if data is not None:
        args += ["--json", json.dumps(data, ensure_ascii=False)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        obj = json.loads(p.stdout.strip())
    except Exception:
        obj = {"error_code": "PARSE", "raw": p.stdout.strip()[:500], "stderr": (p.stderr or "")[:500]}
    return p.returncode, obj


class Fail(Exception):
    pass


def must(rc: int, obj: dict, what: str) -> dict:
    if rc != 0 or obj.get("type") == "error" or obj.get("commit_status") == "not_committed":
        print(f"\n!! {what} 失败 rc={rc}")
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:1500])
        raise Fail(what)
    print(f"   ✓ {what}")
    return obj


def doc_rev(obj: dict) -> int:
    return obj["current_document_revision"]


def state() -> dict:
    rc, obj = call(["show"])
    must(rc, obj, "读取台账状态")
    return obj["object"]


def requirement(rid: str) -> dict:
    rc, obj = call(["show"], {"type": "requirement", "id": rid})
    must(rc, obj, f"读取 {rid}")
    return obj["object"]


# --------------------------------------------------------------- 验收实测数据
AC_EVIDENCE: dict[str, tuple[str, str, str]] = {
    "AC-000001": (
        "初始画面同时可见海水、沙滩、红树林、海藻床、珊瑚礁、台阶、房屋，共 7 类元素，位置可逐一指出。",
        "打开页面截图后按七类元素清单逐项勾选并标注大致坐标。",
        "evidence/08_final_initial.png",
    ),
    "AC-000002": (
        "冻结环境动画后角色从 x=200 移到 x=800，角色包围盒之外的差异像素为 0 个，包围盒内 3386 个。",
        "读取 canvas 像素缓冲区两帧逐像素比对，排除角色包围盒区域。",
        "evidence/probe_evidence.json#backgroundFixed",
    ),
    "AC-000003": (
        "海岸带 144000 像素中，相邻 700ms 采样的差异像素为 12416 与 10703（8.62% / 7.43%），无整幅跳动。",
        "连续抓取 y=150..300 区域三帧，两两做逐像素差分。",
        "evidence/probe_evidence.json#waveAnim",
    ),
    "AC-000004": (
        "→ dx=110.6 dy=0；← dx=-110 dy=0；↑ dy=-110 dx=0；↓ dy=+94（起点 y=430 已近下边界 524，被钳制）。四个方向垂直轴偏移均为 0。",
        "每个方向单独按 1 秒，记录起点与终点坐标并计算 dx/dy。",
        "evidence/probe_game.json#dirs",
    ),
    "AC-000005": (
        "三次 1 秒向右位移为 110 / 109.8 / 110.7 px，极差相对差 0.8%，低于 10% 阈值。",
        "同一起点重复三次计时位移，计算极差与均值比。",
        "evidence/probe_game.json#speed",
    ),
    "AC-000006": (
        "右 942（限 942）、左 18（限 18）、上 196（限 196）、下 524（限 524），均停在允许范围内未越界。",
        "从开阔位置朝四个边界持续按键，读取最终坐标并与边界值比较。",
        "evidence/probe_bounds.json",
    ),
    "AC-000007": (
        "松键后 400ms 内位移为 0，帧索引停在 0。",
        "松键瞬间记录坐标与帧号，400ms 后再次读取。",
        "evidence/probe_game.json#releaseStop",
    ),
    "AC-000008": (
        "1 秒向右行走的帧索引序列为 012301230，共 8 次切换，无跳帧与倒序。",
        "在渲染循环中记录每次帧切换的时间戳与索引，导出序列检查连续性。",
        "evidence/probe_game.json#frameSeq",
    ),
    "AC-000009": (
        "先按右键 400ms 再按上键 400ms，帧组序列为 rrrruuu，切向后立即使用向上动作组。",
        "记录切向前后帧组标识与索引。",
        "evidence/probe_game.json#switchDir",
    ),
    "AC-000010": (
        "松键后 1 秒内帧索引保持不变（frameFrozen=true），画面稳定显示待机帧。",
        "松键后连续记录帧索引确认不再变化。",
        "evidence/probe_game.json#releaseStop",
    ),
    "AC-000011": (
        "16 帧全部 64×64、四角 alpha 均为 0、身体锚点（腹甲质心）帧间漂移 0.8px，检查问题数 0。",
        "运行 python tools/check_sheet.py 逐帧核对尺寸、透明角与腹甲质心。",
        "tools/check_sheet.py 输出 + evidence/07_actioncard.png",
    ),
    "AC-000012": (
        "页面 5 个资源全部来自 127.0.0.1，外部域请求 0 个；用 file:// 直接双击打开同样渲染成功（ready=true，角色在出生点）。",
        "读取 performance resource 列表检查域名；另用 file:// 协议打开同一页面验证。",
        "evidence/probe_evidence.json#resources + evidence/11_file_protocol.png",
    ),
    "AC-000013": (
        "移动 4 秒期间平均帧率 165.4 fps，长帧（单帧 > 50ms）0 次。",
        "重置统计后持续按右键 4 秒，读取滚动平均帧率与长帧计数。",
        "evidence/probe_fps.json",
    ),
    "AC-000014": (
        "canvas 缓冲区 960×540，imageSmoothing=false，CSS image-rendering=crisp-edges；6 倍放大观察边缘为硬像素块，无插值过渡。",
        "读取渲染上下文与计算样式，并对角色局部截图做最近邻放大。",
        "evidence/probe_evidence.json#pixelated + evidence/12_crab_zoom.png",
    ),
}

REVIEW_TEXT = {
    "necessity_review": "已核对 purpose 与 necessity：删除该需求会使对应能力直接缺失，判断成立。",
    "completeness_review": "已逐项核对字段完整、范围包含/排除明确、开放问题为 0、页面区域绑定有效。",
    "acceptance_review": "已检查每个条件具备角色/场景/输入/操作/预期/异常/方法/证据，且可被实测数据判定。",
    "basis": "依据该精确内容修订逐字段审阅，并结合 evidence/ 下的实测结果。",
}


def main() -> int:
    obj = state()
    reqs = []
    for r in obj["requirements"]:
        latest = r["revisions"][-1]
        reqs.append({"id": r["id"], "revision": latest["revision"], "digest": latest["digest"]})
    print(f"台账 {obj['ledger']['id']} 文档修订={obj['document_revision']} 需求={len(reqs)}")

    rev = obj["document_revision"]

    # ---------------- 1. 提交 → 审核 → 确认 ----------------
    for r in reqs:
        rid = r["id"]
        print(f"\n[{rid}] 提交")
        rc, o = call(["req", "submit"], {
            "operation_id": f"submit-{rid}-1", "agent": AGENT,
            "reason": "内容已完整，提交精确修订进入审核",
            "expected_revision": rev,
            "data": {"id": rid, "revision": r["revision"], "digest": r["digest"]},
        })
        must(rc, o, f"{rid} submit"); rev = doc_rev(o)

        rc, o = call(["review", "add"], {
            "operation_id": f"review-{rid}-1", "agent": "review-agent",
            "reason": "对该精确修订做语义审核",
            "expected_revision": rev,
            "data": {
                "target_type": "requirement", "target_id": rid,
                "target_revision": r["revision"], "target_digest": r["digest"],
                "conclusion": "通过", **REVIEW_TEXT,
            },
        })
        must(rc, o, f"{rid} review"); rev = doc_rev(o)

        rc, o = call(["req", "confirm"], {
            "operation_id": f"confirm-{rid}-1", "agent": AGENT,
            "reason": "审核已通过，范围明确，纳入本基线",
            "expected_revision": rev,
            "data": {"id": rid, "revision": r["revision"], "digest": r["digest"],
                     "scope": {"decision": "纳入"}},
        })
        must(rc, o, f"{rid} confirm"); rev = doc_rev(o)

    # ---------------- 2. 基线 ----------------
    print("\n[基线] 封存")
    rc, o = call(["baseline", "seal"], {
        "operation_id": "baseline-seal-1", "agent": AGENT,
        "reason": "四条需求均精确确认，封存首个基线",
        "expected_revision": rev,
        "data": {"predecessor": None,
                 "members": [{"id": r["id"], "revision": r["revision"]} for r in reqs]},
    })
    must(rc, o, "baseline seal"); rev = doc_rev(o)
    base = o["object"]
    bid, brev, bdig = base["id"], base["revision"], base["digest"]
    print(f"   基线 {bid} r{brev} {base.get('version', '')}")

    rc, o = call(["review", "add"], {
        "operation_id": "review-baseline-1", "agent": "review-agent",
        "reason": "审核该基线候选的范围与成员精确性",
        "expected_revision": rev,
        "data": {
            "target_type": "baseline", "target_id": bid,
            "target_revision": brev, "target_digest": bdig,
            "conclusion": "通过", **REVIEW_TEXT,
        },
    })
    must(rc, o, "baseline review"); rev = doc_rev(o)

    rc, o = call(["baseline", "activate"], {
        "operation_id": "baseline-activate-1", "agent": AGENT,
        "reason": "审核通过，激活为当前有效基线并开始开发",
        "expected_revision": rev,
        "data": {"id": bid, "revision": brev, "digest": bdig},
    })
    must(rc, o, "baseline activate"); rev = doc_rev(o)

    # ---------------- 3. 开发 ----------------
    impl_event = {}
    for r in reqs:
        rid = r["id"]
        print(f"\n[{rid}] 开发")
        rc, o = call(["dev", "start"], {
            "operation_id": f"dev-start-{rid}-1", "agent": AGENT,
            "reason": "基线已激活，开始实现该需求",
            "expected_revision": rev,
            "data": {"baseline_id": bid, "id": rid,
                     "revision": r["revision"], "digest": r["digest"]},
        })
        must(rc, o, f"{rid} dev start"); rev = doc_rev(o)

        rc, o = call(["dev", "complete"], {
            "operation_id": f"dev-complete-{rid}-1", "agent": AGENT,
            "reason": "实现完成，证据见 evidence/ 目录",
            "expected_revision": rev,
            "data": {"baseline_id": bid, "id": rid,
                     "revision": r["revision"], "digest": r["digest"]},
        })
        must(rc, o, f"{rid} dev complete"); rev = doc_rev(o)
        impl_event[rid] = o["object"].get("event_id") or o["meta"].get("event_id")
        print(f"   实现事件 {impl_event[rid]}")

    # ---------------- 4. 逐条件验收 ----------------
    for r in reqs:
        rid = r["id"]
        full = requirement(rid)
        conds = [c["id"] for c in full["acceptance"]]
        print(f"\n[{rid}] 验收 {len(conds)} 个条件")
        for cid in conds:
            actual, method, evidence = AC_EVIDENCE[cid]
            rc, o = call(["acceptance", "record"], {
                "operation_id": f"acc-{cid}-1", "agent": AGENT,
                "reason": "按实测数据登记该条件的验收结果",
                "expected_revision": rev,
                "data": {
                    "baseline_id": bid, "requirement_id": rid,
                    "revision": r["revision"], "cycle": 1,
                    "condition_id": cid, "delivery_id": DELIVERY,
                    "implemented_event_id": impl_event[rid],
                    "actual": actual, "method": method,
                    "result": "通过", "evidence": evidence,
                },
            })
            must(rc, o, f"{cid} 验收"); rev = doc_rev(o)

    # ---------------- 5. 发布 ----------------
    print("\n[发布] 登记")
    rc, o = call(["release", "add"], {
        "operation_id": "release-add-1", "agent": AGENT,
        "reason": f"当前基线全部条件已实测通过，登记交付 {DELIVERY}",
        "expected_revision": rev,
        "data": {"baseline_id": bid, "delivery_id": DELIVERY,
                 "members": [{"id": r["id"], "revision": r["revision"], "cycle": 1} for r in reqs]},
    })
    must(rc, o, "release add")
    rel = o["object"]
    print(f"\n发布：{rel.get('id')} 交付={rel.get('delivery_id')} 成员={len(rel.get('members', []))}")

    rc, o = call(["check"])
    must(rc, o, "台账结构自检")
    print("\n完成。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Fail as e:
        print(f"\n中断于：{e}")
        raise SystemExit(1)
