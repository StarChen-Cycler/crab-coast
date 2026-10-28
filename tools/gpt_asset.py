"""用 Edge + ChatGPT 生成一张图并落盘。

流程（与用户要求一致）：
  1. 新开一个 ChatGPT 会话；
  2. 把 tools/prompts/<name>.txt 的内容打进去并回车；
  3. 轮询等待——只要「停止/暂停」按钮还在，就说明还在生成，继续等；
     停止按钮消失且出现「发送」按钮、并检测到图片，才算完成；
  4. 把最大那张图导出为 PNG 写到 assets/gpt/<out>。

用法：
  python tools/gpt_asset.py 01_scene scene_ref.png [--timeout 300]
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDGE = Path(r"C:\Users\LENOVO\.agents\skills\edge-cdp-automation\scripts\edge.js")
JS = ROOT / "tools" / "js"
OUTDIR = ROOT / "assets" / "gpt"


def edge(*args: str, page: str | None = None, capture: bool = True) -> str:
    env_page = page if page is not None else ""
    cmd = ["node", str(EDGE), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "PAGE": env_page})
    if capture:
        return (p.stdout or "") + (p.stderr or "")
    return ""


def tabs(page: str = "") -> list[dict]:
    out = edge("ls", page=page)
    items = []
    for line in out.splitlines():
        m = re.match(r"^\[(\d+)\]\s+(\S+)", line.strip())
        if m:
            items.append({"idx": int(m.group(1)), "url": m.group(2)})
    return items


def evalfile(name: str, page: str) -> str:
    return edge("evalfile", str(JS / name), page=page).strip()


def main() -> int:
    name = sys.argv[1]
    out_name = sys.argv[2]
    timeout = 300
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    prompt = (ROOT / "tools" / "prompts" / f"{name}.txt").read_text(encoding="utf-8").strip()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # 1. 新会话
    print("[1] 打开新会话")
    edge("new", "https://chatgpt.com/", page="")
    time.sleep(5)
    page = None
    for t in tabs():
        if t["url"].rstrip("/") == "https://chatgpt.com":
            page = str(t["idx"])
    if page is None:
        print("找不到新会话标签页")
        return 1
    print(f"    使用标签页 [{page}]")

    # 2. 输入并发送
    info = json.loads(evalfile("composer.js", page))
    if not info.get("found"):
        print("找不到输入框")
        return 1
    edge("at", str(info["x"]), str(info["y"]), page=page)
    edge("type", prompt, page=page)
    edge("key", "Enter", page=page)
    print("[2] 已发送，开始等待生成")

    # 3. 轮询
    t0 = time.time()
    seen_image = False
    stable = 0
    last_imgs = 0
    while time.time() - t0 < timeout:
        time.sleep(4)
        try:
            st = json.loads(evalfile("gen_state.js", page))
        except Exception:
            st = {}
        elapsed = int(time.time() - t0)
        if st.get("imageCount", 0) > last_imgs:
            last_imgs = st["imageCount"]
            seen_image = True
            print(f"    [{elapsed:3d}s] 检测到图片 {st['images']}")
        # 完成判定：不再生成 + 有发送键 + 图片数量稳定
        if not st.get("generating") and st.get("sendEnabled") and seen_image:
            stable += 1
            if stable >= 2:
                print(f"    [{elapsed:3d}s] 生成完成（停止键消失且发送键出现）")
                break
        else:
            stable = 0
            if elapsed % 20 < 4:
                print(f"    [{elapsed:3d}s] 生成中… 停止键={st.get('stopButtons')} 图={st.get('imageCount')}")
    else:
        print("超时：仍然没有拿到完整图片")
        return 1

    # 4. 导出
    data_url = evalfile("dump_image.js", page)
    if data_url == "NONE":
        print("导出失败：没有可用图片")
        return 1
    raw = base64.b64decode(data_url.split(",", 1)[1])
    out = OUTDIR / out_name
    out.write_bytes(raw)
    from PIL import Image
    im = Image.open(out)
    print(f"[4] 已保存 {out}  {im.size}  {len(raw)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
