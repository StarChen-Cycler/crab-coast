"""把乐谱 JSON 渲染成可无缝循环的 WAV（海边休闲风）。

无缝循环的做法：**所有写入都按「循环长度取模」**——
音符的释放尾巴、回声尾巴一旦越过 40.0 秒的末尾，会自动绕回开头，
所以不需要淡入淡出，接缝处天然连续。

音色（合成，不采样）：
  lead : 方波 + 一阶低通 + ADSR
  bass : 三角波 + 正弦低八度
  arp  : 正弦/三角短音（衰减快）
  perc : 白噪声包络（42 闭镲 / 70 沙锤）

用法：python tools/make_music.py [score.json] [out.wav]
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent          # 本文件在 music/ 里
SCORE = ROOT / "seaside_score.json"
OUT = ROOT / "seaside_loop.wav"

SR = 32000            # 采样率（够用且文件不大）
PEAK = 0.89           # 归一化峰值


# ---------------------------------------------------------------- 基础波形
def midi_to_freq(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12.0)


def adsr(n: int, a: float, d: float, s: float, r: float, sr: int = SR) -> np.ndarray:
    """简单 ADSR 包络；n 是总样本数（含释放段）。"""
    env = np.zeros(n, dtype=np.float32)
    na, nd, nr = int(a * sr), int(d * sr), int(r * sr)
    na = max(1, na)
    nd = max(1, nd)
    nr = max(1, nr)
    ns = max(1, n - na - nd - nr)
    i = 0
    env[i:i + na] = np.linspace(0, 1, na, dtype=np.float32); i += na
    env[i:i + nd] = np.linspace(1, s, nd, dtype=np.float32); i += nd
    env[i:i + ns] = s; i += ns
    tail = n - i
    if tail > 0:
        env[i:i + tail] = np.linspace(s, 0, tail, dtype=np.float32)
    return env


def one_pole_lp(x: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    a = np.exp(-2 * np.pi * cutoff_hz / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


# ---------------------------------------------------------------- 合成
def render_note(buf: np.ndarray, start: int, n: int, wave_fn, gain: float) -> None:
    """把一段音写进循环缓冲区（取模环绕）。"""
    N = len(buf)
    idx = (start + np.arange(n)) % N
    np.add.at(buf, idx, wave_fn(n) * gain)


def synth_lead(freq: float, dur_s: float, sr: int = SR) -> np.ndarray:
    n = int((dur_s + 0.12) * sr)
    t = np.arange(n) / sr
    sq = np.sign(np.sin(2 * np.pi * freq * t)).astype(np.float32)
    tri = (2 / np.pi * np.arcsin(np.sin(2 * np.pi * freq * t))).astype(np.float32)
    x = 0.62 * sq + 0.38 * tri
    x = one_pole_lp(x, 3600)
    return x * adsr(n, 0.006, 0.09, 0.62, 0.12)


def synth_bass(freq: float, dur_s: float, sr: int = SR) -> np.ndarray:
    n = int((dur_s + 0.08) * sr)
    t = np.arange(n) / sr
    tri = (2 / np.pi * np.arcsin(np.sin(2 * np.pi * freq * t))).astype(np.float32)
    sub = np.sin(2 * np.pi * freq / 2 * t).astype(np.float32)
    x = 0.7 * tri + 0.3 * sub
    x = one_pole_lp(x, 900)
    return x * adsr(n, 0.008, 0.12, 0.55, 0.08)


def synth_arp(freq: float, dur_s: float, sr: int = SR) -> np.ndarray:
    n = int((dur_s + 0.06) * sr)
    t = np.arange(n) / sr
    x = (0.7 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)).astype(np.float32)
    x = one_pole_lp(x, 5200)
    env = np.exp(-t * 14.0).astype(np.float32)
    return x * env * adsr(n, 0.004, 0.02, 0.9, 0.05)


def synth_hat(dur_s: float, rng: np.random.Generator, sr: int = SR) -> np.ndarray:
    n = int(dur_s * sr)
    t = np.arange(n) / sr
    noise = rng.standard_normal(n).astype(np.float32)
    # 用差分做简易高通，去掉低频"砰"
    noise = np.diff(noise, prepend=0.0).astype(np.float32)
    return noise * np.exp(-t * 90.0).astype(np.float32)


def synth_shaker(dur_s: float, rng: np.random.Generator, sr: int = SR) -> np.ndarray:
    n = int(dur_s * sr)
    t = np.arange(n) / sr
    noise = rng.standard_normal(n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0).astype(np.float32)
    env = (1 - np.exp(-t * 260.0)) * np.exp(-t * 26.0)
    return noise * env.astype(np.float32)


# ---------------------------------------------------------------- 混响（环绕）
def wrap_delay(x: np.ndarray, delay_s: float, fb: float, wet: float) -> np.ndarray:
    """带回声：延迟线同样按循环长度取模，尾巴会绕回开头，接缝不断。"""
    N = len(x)
    d = max(1, int(delay_s * SR))
    idx = (np.arange(N) - d) % N
    y = x.copy()
    echo = x[idx] * wet
    y += echo
    echo2 = x[(np.arange(N) - 2 * d) % N] * wet * fb
    y += echo2
    return y


def main() -> None:
    score_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SCORE
    out_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else OUT
    score = json.loads(score_path.read_text(encoding="utf-8"))

    bpm = float(score["bpm"])
    bars = int(score["bars"])
    bpb = int(score.get("beatsPerBar", 4))
    spb = 60.0 / bpm
    total_beats = bars * bpb
    N = int(round(total_beats * spb * SR))
    print(f"{bpm} BPM · {bars} 小节 · {bpb}/4 · {total_beats} 拍 · {N / SR:.3f} 秒 · {N} 采样")

    rng = np.random.default_rng(20261028)
    buf = np.zeros(N, dtype=np.float32)

    gains = {"lead": 0.30, "bass": 0.34, "arp": 0.16, "perc": 0.13}
    counts = {}
    for tr in score["tracks"]:
        name = tr["name"]
        notes = tr.get("notes") or []
        counts[name] = len(notes)
        g = gains.get(name, 0.2)
        for nt in notes:
            start = int(round(float(nt["start"]) * spb * SR))
            dur_s = float(nt["dur"]) * spb
            m = int(nt["midi"])
            if name == "perc":
                if m == 42:
                    sig = synth_hat(0.06, rng)
                else:
                    sig = synth_shaker(0.09, rng)
            elif name == "bass":
                sig = synth_bass(midi_to_freq(m), dur_s)
            elif name == "arp":
                sig = synth_arp(midi_to_freq(m), dur_s)
            else:
                sig = synth_lead(midi_to_freq(m), dur_s)
            render_note(buf, start, len(sig), lambda n, s=sig: s, g)

    print("音符数:", counts)

    # 主旋律加一点环绕回声（八分音符）
    buf = wrap_delay(buf, spb * 0.5, 0.35, 0.12) + buf * 0.82

    # 软限幅 + 归一化
    buf = np.tanh(buf * 1.1).astype(np.float32)
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = (buf / peak * PEAK).astype(np.float32)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(buf * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    size_mb = out_path.stat().st_size / 1024 / 1024
    name = out_path.name if ROOT not in out_path.parents else str(out_path.relative_to(ROOT))
    print(f"已写出 {name}  {N / SR:.3f}s  {size_mb:.2f} MB")

    # 接缝自检：首尾各取 2ms，比较电平差（不要求相等，只求没有突变到静音）
    head = buf[:64]
    tail = buf[-64:]
    print(f"接缝检查：首段 RMS {np.sqrt(np.mean(head**2)):.4f} / 末段 RMS {np.sqrt(np.mean(tail**2)):.4f}")


if __name__ == "__main__":
    main()
