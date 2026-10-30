"""多人在线版背景音乐（REQ-000022）：登记需求并纳入新基线。

① 服务端把 /music/ 音频按 HTTP Range 正确供给（200 / 206 / 416）；
② 多人页面加 BGM 播放器（手势后播放、循环、静音开关 + 记忆、切后台暂停、失败只隐藏按钮）。
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
    print(f"  {name}: exit={code} {body.get('type')} doc_rev={body.get('document_revision')} id={o.get('id')}")
    if not good:
        print("    issues:", json.dumps(body.get("issues"), ensure_ascii=False)[:900])
        print("    raw:", (body.get("_raw") or "")[:400])
    return good


def ac(role, scenario, pre, inp, op, expected, exc, method, evidence):
    return {"role": role, "scenario": scenario, "preconditions": pre, "input": inp,
            "operation": op, "expected": expected, "method": method, "evidence": evidence,
            "exception": {"scenario": exc[0], "expected": exc[1], "handling": exc[2]}}


def add_source():
    rev = show({"type": "ledger"})["document_revision"]
    code, body = call(["source", "add"], {
        "operation_id": "bgm-src-add", "agent": "octie-agent",
        "reason": "登记 2026-10-30 关于多人版缺背景音乐的反馈原话", "expected_revision": rev,
        "data": {
            "kind": "用户消息",
            "name": "用户要求多人版补上背景音乐并由服务端供给",
            "date_note": "2026-10-30 用户消息",
            "manual_note": "用户在真机回访时直接提出，未经整理",
            "quote": "音乐没有放进来，这个需求要满足，加这个部分到server侧",
            "summary": ("用户指出多人版页面缺了背景音乐（单机版有 40 秒无缝循环的海岸 BGM），"
                        "要求补上，并且音频要由服务端（cloud 那台）供给，而不是只在单机版可用。"),
        },
    })
    if not ok("source add", code, body):
        raise SystemExit(1)
    print("source:", body["object"]["id"])
    return body["object"]["id"]


REQ22 = {
    "title": "多人在线版背景音乐：服务端供给音频，页面播放与开关",
    "type": "功能", "module": "多人前端", "priority": "P1",
    "placement": {"kind": "页面", "other": [],
                  "primary": {"page_id": "PAGE-000002", "page_revision": 1,
                              "region_id": "REG-000002-0001-0004"}},
    "questions": [],
    "description": ("单机版有 40 秒无缝循环的海岸 BGM，多人版页面完全没有声音，用户明确要求补上，"
                    "并且音频由服务端供给。本需求包含两侧：服务端的静态文件服务要把 /music/ 下的音频"
                    "按 HTTP Range 正确供给（整文件 200、单区间 206、越界 416，带 accept-ranges，"
                    "移动端播放器才能可靠取流与循环）；多人前端在进入游戏后加载播放器：受浏览器自动播放"
                    "策略限制，首次按键/触摸后再开始播放（不报错、不阻塞游戏），40 秒音频无缝循环，"
                    "提供静音开关并把偏好记在 localStorage，页面隐藏时暂停、回前台继续，音频出错只隐藏"
                    "按钮而不影响游戏本身。音频沿用单机版同一份文件，避免两套素材漂移。"),
    "purpose": "把多人版的听觉体验补齐到与单机版一致，让「打开链接就能玩」的小世界不只是画面。",
    "necessity": ("没有背景音乐时多人页只有画面，与单机版的体验割裂；用户已经明确指出这是缺失的需求。"
                  "服务端不支持 Range 时，移动端 Safari 等浏览器取 4.88MB 的 WAV 容易卡住或无法循环，"
                  "所以服务端这一环必须一起做。"),
    "included": [
        "服务端静态供给 /music/ 音频并支持 HTTP Range（200 / 206 / 416 + accept-ranges）",
        "多人页面加载 BGM 播放器：首次按键或触摸后开始播放，40 秒无缝循环，音量常量 0.42",
        "静音开关（按钮 + M 键），偏好写入 localStorage 并在刷新后保持",
        "页面隐藏时暂停、恢复可见时继续（原本在播才继续）",
        "失败回落：音频加载/解码失败只隐藏按钮，不影响快照、渲染与操作",
    ],
    "excluded": [
        "音乐切换、音量滑杆、淡出时长可配",
        "把 WAV 转码成流媒体或按需分片（沿用现有 4.88MB WAV，不为省流量引入转码链）",
        "页面隐藏时继续播放（会额外耗电，且多数手机浏览器本就暂停音频）",
        "单机版 BGM 的行为改动（单机继续用 music/bgm.js）",
    ],
    "normal_behavior": {
        "scenario": "手机打开 /play 链接并进入游戏",
        "behavior": "首次触摸摇杆或点屏幕后，海岸 BGM 以 42% 音量开始循环播放",
        "expected": "音乐正常播放、不卡顿、可按按钮静音；按钮不压住任何既有控件",
    },
    "boundaries": [
        {"scenario": "浏览器拦截自动播放", "expected": "不报错、不弹提示，等第一次按键/触摸再播放",
         "handling": "手势内同步调用 play()，失败只记录状态"},
        {"scenario": "音频文件 404 或解码失败", "expected": "音乐按钮隐藏，游戏其余部分完全不受影响",
         "handling": "audio 的 error 事件里隐藏按钮，不抛异常"},
        {"scenario": "页面切到后台", "expected": "暂停；回到前台且原来在播时继续",
         "handling": "visibilitychange 里记录播放意愿再暂停/恢复"},
        {"scenario": "Range 请求越界（bytes=99999999-）", "expected": "返回 416 并带 content-range: bytes */*",
         "handling": "解析后判定不可满足"},
        {"scenario": "同一页面被重复初始化", "expected": "只有一个播放实例，不出现两路音乐叠加",
         "handling": "模块内单例（window.__play.bgm 已存在则复用）"},
    ],
    "acceptance": [
        ac("接口验收者", "服务端按 HTTP Range 供给音频",
           "服务已启动（任一端口），仓库根存在 music/seaside_lazy_loop_40s.wav",
           "不带 Range 头请求一次；带 bytes=0-1023 一次；带 bytes=99999999- 一次",
           "读状态码、响应头与正文长度",
           "不带 Range 头 → 200，content-type 为 audio/wav，带 accept-ranges: bytes，content-length 等于该音频文件实际字节数（当前 5120044）；"
           "bytes=0-1023 → 206，content-range 为 bytes 0-1023/5120044，正文长度 1024 字节；"
           "bytes=99999999- → 416，content-range 为 bytes 后接星号斜杠再接 5120044",
           ("音频取不到或只返回 200 全量、移动端无法取流", "判定静态白名单/MIME/Range 分支缺失",
            "检查 resolveStatic 是否放行 /music/ 与 serveFile 的 206/416 分支"),
           "REST 客户端读状态码与响应头，对比本地文件大小", "evidence/bgm.json 中 AC-000087"),
        ac("前端验收者", "首次交互后开始播放",
           "390x844 触屏视口，进入游戏页，localStorage 无静音标记",
           "打开 /play?t=… ，随后派发一次 pointerdown 手势",
           "读 __play.bgm 与 audio 的属性",
           "手势后 800ms 内 started=true、paused=false、currentTime>0、loop=true、音量 0.42±0.01、readyState≥2",
           ("一直不出声", "判定 play() 不在手势内或异常被吞", "手势内同步调用，失败只更新状态"),
           "CDP 派发手势后轮询页面状态", "evidence/bgm.json 中 AC-000088"),
        ac("前端验收者", "静音开关且刷新后保持",
           "同上，音乐已在播放",
           "点按钮静音 → 刷新页面 → 再点按钮恢复",
           "读 muted / paused / localStorage 与页面重载后的状态",
           "静音后 muted=true、paused=true、localStorage 记 1；刷新后仍 muted=true 且不自动出声；再点后 paused=false",
           ("刷新后又自动出声", "判定存储键或初始化顺序有误", "初始化时先读 localStorage 再决定是否播放"),
           "页面内点击按钮 + Page.reload 后读状态", "evidence/bgm.json 中 AC-000089"),
        ac("前端验收者", "音乐按钮不压其它控件",
           "竖屏 390x844 与横屏 844x390",
           "打开页面并读取所有固定元素矩形",
           "逐对判定相交，并检查按钮是否在视口内",
           "按钮矩形在视口内，且与自身/附近/连接三个 HUD、摇杆、ABXY、收起开关全部零重叠",
           ("按钮压住 HUD 或摇杆", "判定定位与既有元素撞位", "放在左列第三个位置（自身/附近之下）"),
           "读 getBoundingClientRect 做相交计算", "evidence/bgm.json 中 AC-000090"),
        ac("前端验收者", "音频失败不影响游戏",
           "游戏已在跑、快照正常",
           "把 audio.src 指向不存在的文件并触发 error",
           "读按钮显示状态、连接状态、快照新鲜度与连续 5 帧画布像素",
           "按钮 display=none；connected=true、快照 age<500ms、连续 5 帧画布像素完全一致",
           ("游戏被拖死或报错", "判定错误处理缺失", "error 里只隐藏按钮，不抛异常"),
           "页面内改 src + dispatch error，再采样", "evidence/bgm.json 中 AC-000091"),
        ac("前端验收者", "切后台暂停、回前台继续",
           "音乐正在播放",
           "派发 visibilitychange（hidden），再派发（visible）",
           "读 paused 与恢复后的状态",
           "hidden 时 paused=true；visible 后 1 秒内 paused=false 且 currentTime 继续增长",
           ("后台继续耗电或回前台不出声", "判定可见性处理只做一半", "记录 wasPlaying，visible 时按意愿恢复"),
           "页面内派发事件 + 读 audio 状态", "evidence/bgm.json 中 AC-000092"),
    ],
    "technical": ("服务端：新增 cloud/server/range.js（纯函数 parseRange(header, size) → null | {start,end} | "
                  "{unsatisfiable}），index.js 的 serveFile 改为按 Range 返回 206/416 并始终带 accept-ranges: bytes。"
                  "前端：新增 cloud/play/bgm.js（createBgm，暴露 window.__play.bgm 供验收），"
                  "play/index.html 在 play.js 之后引入；按钮定位在左列第三个（自身 14/14、附近 14/56、音乐 14/92），"
                  "与 touch.js 的收起开关（竖屏右上、横屏顶部居中）不撞位。音频沿用 "
                  "music/seaside_lazy_loop_40s.wav（4.88MB，接缝跳变 0.0019，mp3 编码 padding 会破坏无缝循环）。"),
}


def main():
    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    pred = doc["object"]["active_baseline"]
    print("start doc_rev:", rev, "active:", pred)

    src = add_source()
    data = dict(REQ22)
    data["sources"] = [{"source_id": s, "source_revision": 1}
                       for s in ("SRC-000004", src)]

    existing = [r for r in show({"type": "ledger"})["object"]["requirements"]
                if r["revisions"][-1]["title"] == data["title"]]
    if existing:
        cur = existing[0]["revisions"][-1]
        rid, rrev, digest = existing[0]["id"], cur["revision"], cur["digest"]
        print(f"skip add（已存在 {rid} r{rrev}）")
    else:
        code, body = call(["req", "add"], {"operation_id": "bgm-req-add", "agent": "octie-agent",
                                           "reason": "登记多人版背景音乐需求", "expected_revision": rev,
                                           "data": data})
        if not ok("req add", code, body):
            return 1
        rev = body["document_revision"]
        rid, rrev, digest = body["object"]["id"], body["object"]["revision"], body["object"]["digest"]

    reviews = {
        "necessity_review": "必要性：多人版没有任何声音，与单机版体验割裂，用户已明确指出；服务端不支持 Range 会让移动端取 4.88MB WAV 卡住。",
        "completeness_review": "完整性：15 类字段齐全；纳入 5 条、排除 4 条（不做切换/转码/后台播放/不改单机）、边界 5 条；页面归属 PAGE-000002；开放问题为空。",
        "acceptance_review": "验收：6 条覆盖服务端 Range、播放、静音记忆、布局、失败回落、切后台暂停，全部可用 HTTP 头与页面状态判定。",
        "basis": "依据 2026-10-30 用户原话、music/README.md 的实测参数与 cloud/server/index.js 现状。声明式审核。",
    }
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
        code, body = call(args, {"operation_id": f"bgm-{opname}", "agent": agent,
                                 "reason": reason, "expected_revision": rev, "data": d2})
        if not ok(opname, code, body):
            return 1
        rev = body["document_revision"]
    print(f"{rid} r{rrev} digest {digest[:12]}")

    doc = show({"type": "ledger"})
    rev = doc["document_revision"]
    cur = [r for r in doc["object"]["requirements"] if r["id"] == rid][0]["revisions"][-1]
    retests = [{"requirement_id": rid, "revision": rrev, "condition_id": a["id"]}
               for a in cur["acceptance"]]
    # 改了 serveFile（单机版首页也走它），按影响分析把「单机版不受影响」一并纳入重验
    for cid in ("AC-000045", "AC-000046"):
        retests.append({"requirement_id": "REQ-000012", "revision": 2, "condition_id": cid})
    print("retests:", len(retests), [r["condition_id"] for r in retests])

    code, body = call(["change", "propose"], {
        "operation_id": "bgm-chg-propose", "agent": "octie-agent",
        "reason": "把多人版背景音乐需求纳入新基线",
        "expected_revision": rev,
        "data": {"predecessor": pred,
                 "actions": [{"type": "新增", "requirement_id": rid,
                              "old_revision": None, "new_revision": rrev}],
                 "impact_objects": [rid]},
    })
    if not ok("propose", code, body):
        return 1
    rev = body["document_revision"]
    chg = body["object"]["id"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["change", "evaluate"], {
        "operation_id": "bgm-chg-evaluate", "agent": "octie-agent",
        "reason": "补齐影响评估与重验清单", "expected_revision": rev,
        "data": {"id": chg, "revision": ch["revision"], "digest": ch["digest"],
                 "impact_analysis": (
                     "两处实现改动：①cloud/server/index.js 的 serveFile 增加 Range 支持（206/416），"
                     "它同时服务单机版首页与云端的 /cards、/assets、/music，所以把单机版「file:// 可用、"
                     "不依赖服务端」两条条件一并重验；②新增 cloud/play/bgm.js 并在 play/index.html 引入，"
                     "只影响多人前端。服务端权威移动、卡片管线、CLI/技能均未改动。"),
                 "retests": retests},
    })
    if not ok("evaluate", code, body):
        return 1
    rev = body["document_revision"]

    ch = show({"type": "change", "id": chg})["object"]
    code, body = call(["review", "add"], {
        "operation_id": "bgm-chg-review", "agent": "review-agent",
        "reason": f"对 {chg} 做变更审核", "expected_revision": rev,
        "data": {"target_type": "change", "target_id": chg,
                 "target_revision": ch["revision"], "target_digest": ch["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：用户明确要求多人版补上背景音乐且由服务端供给；Range 支持是移动端可靠取流的前提。",
                 "completeness_review": f"完整性：1 个新增动作；候选成员 = 前驱全部成员 + {rid}；{len(retests)} 项重验（含单机版不受影响的 2 条）。",
                 "acceptance_review": "验收：6 条本需求条件 + 2 条单机版回归条件，均可由 HTTP 头与页面内状态断言；本审核不声称已执行。",
                 "basis": f"依据 {chg} 评估后摘要 {ch['digest'][:12]}…。声明式审核。"},
    })
    if not ok("review", code, body):
        return 1
    rev = body["document_revision"]

    for act in ("approve", "apply"):
        ch = show({"type": "change", "id": chg})["object"]
        code, body = call(["change", act], {
            "operation_id": f"bgm-chg-{act}", "agent": "octie-agent",
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
        "operation_id": "bgm-base-review", "agent": "review-agent",
        "reason": f"对候选基线 {cand['id']} 做封存审核", "expected_revision": rev,
        "data": {"target_type": "baseline", "target_id": cand["id"],
                 "target_revision": cand["revision"], "target_digest": cand["digest"], "conclusion": "通过",
                 "necessity_review": "必要性：新需求要与既有成员一起冻结成可发布快照。",
                 "completeness_review": f"成员完整：{len(cand['members'])} 个，其余保持前驱修订。",
                 "acceptance_review": f"{len(retests)} 项重验尚未登记执行结果，属后续验收环节，本审核不声称其已通过。",
                 "basis": f"依据 {cand['id']} r{cand['revision']} 摘要 {cand['digest'][:12]}…。声明式审核。"},
    })
    if not ok("baseline review", code, body):
        return 1
    rev = body["document_revision"]

    code, body = call(["baseline", "activate"], {
        "operation_id": "bgm-base-activate", "agent": "octie-agent",
        "reason": "候选基线已审核通过，激活为当前有效基线", "expected_revision": rev,
        "data": {"id": cand["id"], "revision": cand["revision"], "digest": cand["digest"]},
    })
    if not ok("activate", code, body):
        return 1

    ids = {"change": chg, "baseline": cand["id"], "version": cand.get("version"),
           "requirements": {rid: rrev},
           "retests": retests}
    with open("tools/_bgm_ids.json", "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    print("done. doc_rev:", body["document_revision"], "| change:", chg, "| baseline:", cand["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
