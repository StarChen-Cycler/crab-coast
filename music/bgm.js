/* 海岸 BGM 播放器 —— 与音频同放在 music/ 目录，页面只需引一行 script
 *
 * 行为：
 *   1. 先尝试自动播放；被浏览器拦截时，等第一次按键 / 点击再开始（合规、不报错）
 *   2. 右上角按钮或按 M 键切换静音，状态记在 localStorage
 *   3. 淡入淡出，切换时不"咔哒"
 *   4. 音频加载失败就自动隐藏按钮，不影响游戏
 *
 * 对外接口：window.__bgm = { audio, toggle(), setMuted(v), muted }
 */
(() => {
  'use strict';

  // 用脚本自身位置定位音频，整个目录搬走也不会失效
  const self = document.currentScript;
  let src = 'music/seaside_lazy_loop_40s.wav';
  try {
    if (self && self.src) src = new URL('seaside_lazy_loop_40s.wav', self.src).href;
  } catch (e) { /* 保持相对路径 */ }

  const TARGET = 0.42;                 // 背景音乐音量
  const STORE_KEY = 'crab-coast:bgm-muted';
  const FADE_MS = 320;

  const audio = new Audio();
  audio.src = src;
  audio.loop = true;
  audio.preload = 'auto';
  audio.volume = 0;

  let muted = false;
  try { muted = localStorage.getItem(STORE_KEY) === '1'; } catch (e) { muted = false; }
  audio.muted = muted;

  let started = false;
  let fading = null;

  function fadeTo(target, done) {
    if (fading) clearInterval(fading);
    const from = audio.volume;
    const t0 = performance.now();
    fading = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / FADE_MS);
      audio.volume = from + (target - from) * k;
      if (k >= 1) {
        clearInterval(fading);
        fading = null;
        if (done) done();
      }
    }, 16);
  }

  function start() {
    if (started) return;
    started = true;
    const p = audio.play();
    if (p && p.catch) {
      p.catch(() => { started = false; });   // 被拦截：下次手势再试
      p.then(() => { if (!muted) fadeTo(TARGET); });
    }
  }

  // 第一次交互后开始（满足自动播放策略）
  const kick = () => { start(); };
  window.addEventListener('keydown', kick, { passive: true });
  window.addEventListener('pointerdown', kick, { passive: true });

  // ---------------------------------------------------------------- 按钮
  const btn = document.createElement('button');
  btn.id = 'bgm-btn';
  btn.type = 'button';
  btn.style.cssText = [
    'position:fixed', 'right:18px', 'top:16px', 'z-index:11',
    'display:flex', 'align-items:center', 'gap:6px',
    'padding:7px 12px', 'border-radius:10px', 'cursor:pointer',
    'font:13px/1 "Segoe UI","Microsoft YaHei",system-ui,sans-serif',
    'color:#f3e7cf', 'background:rgba(6,26,34,.62)',
    'border:1px solid rgba(240,226,199,.22)', 'backdrop-filter:blur(4px)',
  ].join(';');
  const label = () => {
    btn.textContent = muted ? '🔇 音乐' : '🔊 音乐';
    btn.title = (muted ? '已静音' : '播放中') + '（M 切换）';
  };
  label();
  document.body.appendChild(btn);

  function setMuted(v) {
    muted = !!v;
    audio.muted = muted;
    try { localStorage.setItem(STORE_KEY, muted ? '1' : '0'); } catch (e) { /* ignore */ }
    if (!muted) { start(); fadeTo(TARGET); } else { fadeTo(0); }
    label();
  }

  btn.addEventListener('click', (e) => { e.stopPropagation(); setMuted(!muted); });
  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyM' && !e.repeat) setMuted(!muted);
  });

  audio.addEventListener('error', () => { btn.style.display = 'none'; });

  window.__bgm = {
    audio,
    toggle: () => setMuted(!muted),
    setMuted,
    get muted() { return muted; },
    get started() { return started; },
  };
})();
