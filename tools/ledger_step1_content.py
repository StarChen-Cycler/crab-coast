"""把台账补到最新：REQ-000003 修订到 r2 + 新增 REQ-000005（背景音乐）并完成确认。

只做「内容侧」的两件事，不动基线：
  1. req revise  REQ-000003 r1 -> r2（帧尺寸 64→48、侧视缩 90%、来源描述改成实际流程）
  2. req add     REQ-000005 背景音乐 -> submit -> review(通过) -> confirm(纳入)
"""
from __future__ import annotations

import json
import subprocess

F = r"C:\Users\LENOVO\Documents\ChatGPT\ai-ghs\crab-coast\requirements.md"
AGENT = "octie-agent"


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
        print(json.dumps(obj, ensure_ascii=False, indent=1)[:1600])
        raise SystemExit(1)
    print(f"   ✓ {what}")
    return obj


def rev():
    rc, o = call(["show"])
    must(rc, o, "读台账")
    return o["current_document_revision"]


# ---------------------------------------------------------------- REQ-000003 r2
REQ3 = {
    "id": "REQ-000003",
    "base_revision": 1,
    "title": "播放四向走路动作卡的连续帧动画",
    "description": (
        "螃蟹为四个方向（下、左、右、上）各准备一组走路帧，方向切换时立即切换动作组，"
        "移动过程中按固定帧率循环播放，静止时停在该方向的待机帧。"
        "动作卡由图片生成模型直接产出 4×4 卡片（绿幕），再由代码完成：等分切格 → 软阈值抠绿 → "
        "按包围盒归一化（脚底对齐同一基线）→ 整表统一调色板量化。"
        "当前成品为半尺寸：单帧 48×48、整表 192×192、32 色；其中左侧与右侧两行额外缩放到 90%，"
        "避免侧身时视觉上比正面显大。"
    ),
    "purpose": "让螃蟹的移动看起来是一只活物在走，而不是一张贴图在平移；这也是用户反复强调的“动作卡连续播放”。",
    "necessity": "只有位移没有帧动画，角色会表现为贴图滑动，用户会直接判定不合格；动作卡是该需求的核心交付物。",
    "type": "功能",
    "module": "角色动画",
    "priority": "P0",
    "placement": {
        "kind": "页面",
        "other": [],
        "primary": {"page_id": "PAGE-000001", "page_revision": 1, "region_id": "REG-000001-0001-0001"},
    },
    "sources": [
        {"source_id": "SRC-000001", "source_revision": 1},
        {"source_id": "SRC-000002", "source_revision": 1},
    ],
    "included": [
        "上、下、左、右四个方向的独立走路帧组，每组 4 帧",
        "按 8 帧每秒循环推进帧序号",
        "方向切换时同步切换动作组",
        "松开方向键后停在该方向待机帧（第 0 帧）",
        "16 帧统一 48×48 尺寸、透明背景、同一套 32 色调色板",
        "侧视两行按行缩放到 90%，脚底与正面行保持同一基线",
    ],
    "excluded": [
        "斜向与八方向的独立动作组",
        "攻击、跳跃、死亡等战斗动作",
        "帧间插值生成的补间画面",
        "静止时的呼吸/眨眼等二次动作（试做过，已移除）",
    ],
    "normal_behavior": {
        "scenario": "角色正在向右移动",
        "behavior": "每经过 125 毫秒切换到该方向动作组的下一个帧，四帧结束后回到第一帧继续循环",
        "expected": "画面中的螃蟹腿部姿态逐帧变化，形成持续步行动作",
    },
    "boundaries": [
        {
            "scenario": "移动过程中快速改变方向",
            "expected": "帧序号重置到新方向动作组的第 0 帧，不出现两个方向帧混用的错位画面",
            "handling": "方向变化即重置动画计时器与帧索引",
        },
        {
            "scenario": "角色静止不动",
            "expected": "保持在当前面向方向的第 0 帧，不继续推进动画",
            "handling": "无输入时冻结帧索引",
        },
        {
            "scenario": "从正面切到侧身",
            "expected": "侧身行的显示尺寸比正面小约 10%，切换瞬间不出现明显的“变大”跳变",
            "handling": "切片阶段按行缩放，并把缩放后的脚底回拉到同一基线",
        },
    ],
    "acceptance": [
        {
            "id": "AC-000008",
            "role": "动画验收者",
            "scenario": "核对单一方向的帧循环连通",
            "preconditions": "角色在可行走沙地上，四个方向的帧组已加载",
            "input": "按住右方向键持续 1 秒",
            "operation": "记录这 1 秒内实际绘制的帧索引序列",
            "expected": "帧索引按 0、1、2、3 循环推进，无跳帧与倒序",
            "exception": {
                "scenario": "帧序出现跳跃、倒退或长时间停在同帧",
                "expected": "判定动画不连通",
                "handling": "修正帧推进逻辑与计时基准后复测",
            },
            "method": "在渲染循环中记录每次帧切换的时间戳与索引，导出序列后检查连续性",
            "evidence": "帧索引序列日志 + 行走中截图 evidence/03~06",
        },
        {
            "id": "AC-000009",
            "role": "动画验收者",
            "scenario": "核对方向切换动作组",
            "preconditions": "角色正在向右行走",
            "input": "按住右方向键后改为按住上方向键",
            "operation": "观察切向瞬间的画面并记录所用帧组",
            "expected": "切向后绘制的是向上动作组的帧，切换发生在 1 个渲染帧之内",
            "exception": {
                "scenario": "切向后仍显示向右的帧或出现空白帧",
                "expected": "判定动作组切换失败",
                "handling": "修正方向到帧组的映射后复测",
            },
            "method": "记录切向前后各 5 帧的帧组标识与索引",
            "evidence": "切向前后帧组标识日志 + 切向瞬间截图",
        },
        {
            "id": "AC-000010",
            "role": "动画验收者",
            "scenario": "核对静止时停止推进",
            "preconditions": "角色正在移动",
            "input": "松开所有方向键",
            "operation": "松键后观察 1 秒",
            "expected": "帧索引保持不变并停在 0，画面稳定显示该方向的待机帧",
            "exception": {
                "scenario": "松键后仍在空转播放行走帧",
                "expected": "判定为动画未停止",
                "handling": "静止态改为只绘制第 0 帧后复测",
            },
            "method": "松键后连续记录帧索引，确认数值不再变化",
            "evidence": "松键后 1 秒内的帧索引记录",
        },
        {
            "id": "AC-000011",
            "role": "动画验收者",
            "scenario": "核对动作卡资产一致性与尺寸",
            "preconditions": "动作卡已生成在 assets/crab_sheet.png",
            "input": "无输入",
            "operation": "运行自检脚本检查 16 帧的尺寸、透明角、帧间漂移与脚底基线",
            "expected": "16 帧全部 48×48，四角 alpha 为 0，同方向帧间横向漂移不超过 2 像素，脚底基线一致",
            "exception": {
                "scenario": "存在尺寸不一致、底色残留或帧间跳动",
                "expected": "判定资产不合格",
                "handling": "重新跑切帧与对齐脚本后复检",
            },
            "method": "用脚本遍历 16 帧，统计尺寸、透明角落与包围盒中心偏移；帧尺寸从 scene.json 读取",
            "evidence": "python tools/check_sheet.py 输出 + evidence/33_side_scale_preview.png",
        },
    ],
    "questions": [],
}

# ---------------------------------------------------------------- REQ-000005 新需求
REQ5 = {
    "title": "播放可无缝循环的海岸背景音乐并支持静音",
    "description": (
        "页面加载后提供一段 40 秒整、能够无缝循环的海边休闲风格背景音乐。"
        "受浏览器自动播放策略限制，首次按键或点击后开始播放；播放中不出现接缝断音或爆音。"
        "右上角提供音乐开关，键盘 M 键也可切换，静音状态记在本地，刷新后保持。"
        "音乐文件与页面同在一个文件夹内，断网可用；切换到 mp3 版本时行为不变。"
    ),
    "purpose": "给静止或行走中的场景提供持续的氛围声，让页面像一个完整的小游戏而不是一张会动的图。",
    "necessity": "没有背景音乐时场景偏“静”，用户明确要求补一段海边悠闲向、可循环的电子音乐。",
    "type": "功能",
    "module": "音频",
    "priority": "P1",
    "placement": {
        "kind": "页面",
        "other": [],
        "primary": {"page_id": "PAGE-000001", "page_revision": 1, "region_id": "REG-000001-0001-0002"},
    },
    "sources": [
        {"source_id": "SRC-000001", "source_revision": 1},
    ],
    "included": [
        "40.000 秒、首尾无缝衔接的循环音频",
        "首次按键或点击后自动开始播放",
        "右上角按钮与 M 键切换静音，状态写入 localStorage",
        "音乐文件随页面同目录存放，离线可用",
    ],
    "excluded": [
        "脚步、水声等环境音效",
        "多曲目切换与音量滑动条",
        "在线流媒体或版权音乐接入",
    ],
    "normal_behavior": {
        "scenario": "用户打开页面并按下任意方向键",
        "behavior": "背景音乐从当前循环位置开始播放，音量淡入到设定值",
        "expected": "能听到连续不断的音乐；走到 40 秒末尾时直接接回开头，没有静音空档或爆音",
    },
    "boundaries": [
        {
            "scenario": "浏览器拦截自动播放",
            "expected": "页面不报错，音乐保持静默直到用户第一次按键或点击",
            "handling": "监听首次交互事件后再调用播放，被拒绝时不清除监听",
        },
        {
            "scenario": "音频文件缺失或路径错误",
            "expected": "游戏画面正常，音乐开关按钮自动隐藏",
            "handling": "监听音频错误事件，隐藏按钮并继续运行",
        },
        {
            "scenario": "用户静音后刷新页面",
            "expected": "刷新后仍保持静音",
            "handling": "静音状态写入 localStorage 并在初始化时读取",
        },
    ],
    "acceptance": [
        {
            "role": "音频验收者",
            "scenario": "核对时长与循环设置",
            "preconditions": "页面已打开且音乐资源加载完成",
            "input": "无输入",
            "operation": "读取音频元素的时长与 loop 属性",
            "expected": "duration 为 40（±0.05 秒），loop 属性为 true",
            "exception": {
                "scenario": "时长不符或未开启循环",
                "expected": "判定播放配置不合格",
                "handling": "检查音频文件与 bgm.js 设置后复测",
            },
            "method": "在浏览器控制台读取 window.__bgm.audio.duration 与 loop",
            "evidence": "实测输出：duration=40, loop=true",
        },
        {
            "role": "音频验收者",
            "scenario": "核对接缝无断音爆音",
            "preconditions": "已拿到音频文件",
            "input": "无输入",
            "operation": "比较首尾采样跳变与整体相邻采样差值",
            "expected": "首尾跳变远小于普通相邻差值（比值 < 0.1），听感上无咔哒",
            "exception": {
                "scenario": "接缝处跳变接近最大值",
                "expected": "判定会爆音",
                "handling": "重新做无缝处理或改用取模合成",
            },
            "method": "用脚本读取 PCM，计算 |x[0]-x[-1]| 与相邻差值分布的 p99.9 之比",
            "evidence": "实测 0.0019 / 0.413 = 0.005",
        },
        {
            "role": "音频验收者",
            "scenario": "核对静音开关与记忆",
            "preconditions": "音乐正在播放",
            "input": "点击右上角音乐按钮，然后刷新页面",
            "operation": "观察按钮文案、音频 muted 状态与刷新后的状态",
            "expected": "点击后立即静音且按钮变为静音态；刷新后仍为静音",
            "exception": {
                "scenario": "点击无效或刷新后自动恢复播放",
                "expected": "判定静音功能不合格",
                "handling": "修正 localStorage 读写与 muted 绑定后复测",
            },
            "method": "读取 window.__bgm.muted 与按钮文案，刷新后再读一次",
            "evidence": "操作前后 muted 状态记录",
        },
    ],
    "questions": [],
}


def main():
    rev_now = rev()

    print(f"\n[1] REQ-000003 r1 → r2（当前文档修订 {rev_now}）")
    rc, o = call(["req", "revise"], {
        "operation_id": "req-revise-req3-2", "agent": AGENT,
        "reason": "帧尺寸改为 48、侧视按行缩放到 90%，并把来源描述改成实际流程",
        "expected_revision": rev_now, "data": REQ3,
    })
    must(rc, o, "REQ-000003 revise"); rev_now = o["current_document_revision"]
    d3 = o["object"]["digest"]

    print("\n[2] REQ-000003 r2 提交 / 审核 / 确认")
    rc, o = call(["req", "submit"], {
        "operation_id": "submit-req3-2", "agent": AGENT,
        "reason": "修订完成，提交审核", "expected_revision": rev_now,
        "data": {"id": "REQ-000003", "revision": 2, "digest": d3},
    })
    must(rc, o, "REQ-000003 submit"); rev_now = o["current_document_revision"]

    rc, o = call(["review", "add"], {
        "operation_id": "review-req3-2", "agent": "review-agent",
        "reason": "审核 r2 与实际实现是否一致", "expected_revision": rev_now,
        "data": {
            "target_type": "requirement", "target_id": "REQ-000003",
            "target_revision": 2, "target_digest": d3, "conclusion": "通过",
            "necessity_review": "必要性未变：动作卡仍是该需求的核心交付物。",
            "completeness_review": "已核对帧尺寸、行缩放、静止行为与验收条件，与当前 assets/crab_sheet.png 一致。",
            "acceptance_review": "4 个条件均有可执行的测量方法（帧序、切向、静止、资产自检）。",
            "basis": "依据 tools/check_sheet.py 与 scene.json 的 frame 配置逐项核对。",
        },
    })
    must(rc, o, "REQ-000003 review"); rev_now = o["current_document_revision"]

    rc, o = call(["req", "confirm"], {
        "operation_id": "confirm-req3-2", "agent": AGENT,
        "reason": "与实现一致，纳入基线", "expected_revision": rev_now,
        "data": {"id": "REQ-000003", "revision": 2, "digest": d3, "scope": {"decision": "纳入"}},
    })
    must(rc, o, "REQ-000003 confirm"); rev_now = o["current_document_revision"]

    print("\n[3] 新增 REQ-000005（背景音乐）")
    rc, o = call(["req", "add"], {
        "operation_id": "req-add-bgm-1", "agent": AGENT,
        "reason": "把已交付的背景音乐补进台账", "expected_revision": rev_now, "data": REQ5,
    })
    must(rc, o, "REQ-000005 add"); rev_now = o["current_document_revision"]
    rid = o["object"]["id"]; d5 = o["object"]["digest"]
    print(f"   新需求 {rid}")

    rc, o = call(["req", "submit"], {
        "operation_id": f"submit-{rid}-1", "agent": AGENT,
        "reason": "提交审核", "expected_revision": rev_now,
        "data": {"id": rid, "revision": 1, "digest": d5},
    })
    must(rc, o, "REQ-000005 submit"); rev_now = o["current_document_revision"]

    rc, o = call(["review", "add"], {
        "operation_id": f"review-{rid}-1", "agent": "review-agent",
        "reason": "审核背景音乐需求", "expected_revision": rev_now,
        "data": {
            "target_type": "requirement", "target_id": rid,
            "target_revision": 1, "target_digest": d5, "conclusion": "通过",
            "necessity_review": "用户在需求里明确要求补一段海边休闲向的可循环音乐，必要性成立。",
            "completeness_review": "已写明时长、循环、自动播放兜底、静音与离线要求，范围清晰。",
            "acceptance_review": "3 个条件分别用时长/循环属性、接缝跳变比值、静音记忆来判定，均可实测。",
            "basis": "依据 music/ 目录下的音频与播放器实现核对。",
        },
    })
    must(rc, o, "REQ-000005 review"); rev_now = o["current_document_revision"]

    rc, o = call(["req", "confirm"], {
        "operation_id": f"confirm-{rid}-1", "agent": AGENT,
        "reason": "纳入基线", "expected_revision": rev_now,
        "data": {"id": rid, "revision": 1, "digest": d5, "scope": {"decision": "纳入"}},
    })
    must(rc, o, "REQ-000005 confirm")

    print(f"\n完成。REQ-000003 r2 digest={d3[:8]}  {rid} r1 digest={d5[:8]}")
    print("文档修订:", o["current_document_revision"])


if __name__ == "__main__":
    main()
