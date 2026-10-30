'use strict';
/* 多人版背景音乐（REQ-000022）。
 *
 * 与单机版 music/bgm.js 同一套行为契约（失败不影响游戏、手势后播放、静音记忆、循环），
 * 但按多人页布局重排：多人页右上角是连接状态胶囊、竖屏右中是「收起按键」，所以音乐按钮
 * 放在左列第三个位置（自身 14/14 → 附近 14/56 → 音乐 14/92），样式与样式表里的 HUD 胶囊一致。
 *
 * 音频由服务端供给（/music/…，服务端支持 Range，见 cloud/server/range.js）：
 *   - 只在进入游戏后才创建 Audio，上传页不会去拉 4.88MB；
 *   - loop=true（40 秒无缝循环，接缝跳变 0.0019）；音量常量 0.42，与单机版听感一致；
 *   - 不用 mp3：编码器 padding 会破坏无缝循环（music/README.md 有实测说明）。
 *
 * 对外接口：window.__bgm / window.__play.bgm = { audio, muted, started, playing, toggle, setMuted }
 */
(() => {
  if (window.createBgm) return;   // 重复引入直接返回

  const BGM_SRC = '/music/seaside_lazy_loop_40s.wav';
  // 与单机版 music/bgm.js 的 TARGET 一致：实测在不盖住音效的前提下听感最自然
  const BGM_VOLUME = 0.42;
  const STORE_KEY = 'crab-coast:bgm-muted';   // 与单机版共用同一个偏好键
  const FADE_MS = 320;                        // 淡入时长，避免"咔哒"
  const FADE_STEP_MS = 16;
  const BTN_ID = 'bgm-btn';
  const LABEL_ON = '🔊 音乐';
  const LABEL_OFF = '🔇 音乐';

  function readMuted() {
    try { return localStorage.getItem(STORE_KEY) === '1'; } catch { return false; }
  }
  function writeMuted(v) {
    try { localStorage.setItem(STORE_KEY, v ? '1' : '0'); } catch { /* 隐私模式忽略 */ }
  }

  function createBgm(opts = {}) {
    if (window.__bgm && window.__bgm.audio) return window.__bgm;   // 单例：不出现两路音乐叠加
    const { mount = document.body, onState = () => {} } = opts;

    const audio = new Audio();
    audio.src = BGM_SRC;
    audio.loop = true;
    audio.preload = 'auto';
    audio.volume = 0;

    let muted = readMuted();
    let started = false;      // play() 至少成功过一次
    let failed = false;       // 加载/解码失败：只隐藏按钮
    let fading = null;
    audio.muted = muted;

    const btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.type = 'button';
    mount.appendChild(btn);

    function emit() {
      onState(api ? api.state() : {});
    }

    function paint() {
      btn.textContent = muted ? LABEL_OFF : LABEL_ON;
      btn.title = (muted ? '已静音' : '播放中') + '（M 切换）';
      btn.classList.toggle('muted', muted);
    }

    function fadeTo(target) {
      if (fading) clearInterval(fading);
      const from = audio.volume;
      const t0 = performance.now();
      fading = setInterval(() => {
        const k = Math.min(1, (performance.now() - t0) / FADE_MS);
        audio.volume = from + (target - from) * k;
        if (k >= 1) { clearInterval(fading); fading = null; }
      }, FADE_STEP_MS);
    }

    /** 尝试播放；被浏览器拦截时返回 false 且不抛（等下一次手势）。 */
    function start() {
      if (failed || muted) return Promise.resolve(false);
      let p;
      try { p = audio.play(); } catch { return Promise.resolve(false); }
      if (!p || typeof p.then !== 'function') return Promise.resolve(true);
      return p.then(() => {
        started = true;
        fadeTo(BGM_VOLUME);
        emit();
        return true;
      }).catch(() => { emit(); return false; });   // NotAllowedError 等：静待下一次手势
    }

    function setMuted(v) {
      muted = !!v;
      audio.muted = muted;
      writeMuted(muted);
      paint();
      if (muted) {
        if (fading) { clearInterval(fading); fading = null; }
        audio.volume = 0;
        audio.pause();
      } else {
        start();
      }
      emit();
    }

    // ---- 手势解锁（自动播放策略）：键盘、指针、触摸都算 ----
    const kick = () => { if (!muted) start(); };
    window.addEventListener('keydown', kick, { passive: true });
    window.addEventListener('pointerdown', kick, { passive: true });
    window.addEventListener('touchstart', kick, { passive: true });

    btn.addEventListener('click', (e) => { e.stopPropagation(); setMuted(!muted); });
    window.addEventListener('keydown', (e) => {
      if (e.code === 'KeyM' && !e.repeat) setMuted(!muted);
    });

    // ---- 切后台暂停、回前台按原意愿恢复 ----
    let wasPlaying = false;
    function onVisibility() {
      if (failed) return;
      if (document.visibilityState === 'hidden') {
        wasPlaying = started && !audio.paused;
        if (wasPlaying) audio.pause();
      } else if (wasPlaying) {
        wasPlaying = false;
        if (!muted) start();
      }
    }
    document.addEventListener('visibilitychange', onVisibility);

    // ---- 失败回落：只隐藏按钮，游戏照常 ----
    audio.addEventListener('error', () => {
      failed = true;
      audio.pause();
      btn.style.display = 'none';
      emit();
    });

    paint();

    const api = {
      audio,
      get muted() { return muted; },
      get started() { return started; },
      get failed() { return failed; },
      get playing() { return !audio.paused && !audio.muted; },
      get src() { return audio.src; },
      toggle: () => setMuted(!muted),
      setMuted,
      state() {
        return {
          muted, started, failed, playing: api.playing,
          volume: audio.volume, loop: audio.loop,
          currentTime: audio.currentTime, readyState: audio.readyState,
          src: audio.src,
        };
      },
      destroy() {
        window.removeEventListener('keydown', kick);
        window.removeEventListener('pointerdown', kick);
        window.removeEventListener('touchstart', kick);
        document.removeEventListener('visibilitychange', onVisibility);
        if (fading) clearInterval(fading);
        audio.pause();
        btn.remove();
        if (window.__bgm === api) delete window.__bgm;
      },
      _debug: { BGM_SRC, BGM_VOLUME, STORE_KEY, BTN_ID },
    };
    window.__bgm = api;
    return api;
  }

  window.createBgm = createBgm;
})();
