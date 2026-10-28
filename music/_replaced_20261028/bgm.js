/* 海岸 BGM 播放器 —— 与音乐文件同放在 music/ 目录，页面只需引一行 script
 *
 * 行为：
 *   1. 自动尝试播放；浏览器拦截自动播放时，等第一次点击/按键再开始（合规，不报错）
 *   2. 右上角按钮或按 M 键切换静音，状态存 localStorage
 *   3. 淡入淡出，切换时不会有咔哒声
 *   4. 音频加载失败（比如路径不对）就自动隐藏按钮，不影响游戏
 *
 * 对外接口：window.__bgm = { audio, toggle(), setMuted(v), muted }
 */
(() => {
  'use strict';

  // 用脚本自身位置定位音频，换目录也不会失效
  var self = document.currentScript;
  var src = 'music/coast_bgm.mp3';
  try {
    if (self && self.src) src = new URL('coast_bgm.mp3', self.src).href;
  } catch (e) { /* 保持默认相对路径 */ }

  var TARGET = 0.45;          // 背景音乐音量
  var STORE_KEY = 'crab-coast:bgm-muted';

  var audio = new Audio();
  audio.src = src;
  audio.loop = true;
  audio.preload = 'auto';
  audio.volume = 0;

  var muted = false;
  try { muted = localStorage.getItem(STORE_KEY) === '1'; } catch (e) { muted = false; }

  // ---------------------------------------------------------------- 按钮
  var btn = document.createElement('button');
  btn.id = 'bgm-btn';
  btn.type = 'button';
  btn.style.cssText = [
    'position:fixed', 'right:18px', 'top:16px', 'z-index:11',
    'display:flex', 'align-items:center', 'gap:6px',
    'padding:7px 12px', 'border-radius:10px', 'cursor:pointer',
    'background:rgba(6,26,34,0.62)', 'border:1px solid rgba(240,226,199,0.22)',
    'color:#f3e7cf', 'font-family:inherit', 'font-size:13px', 'letter-spacing:0.02em',
    'backdrop-filter:blur(4px)', 'user-select:none',
  ].join(';');
  if (document.body) document.body.appendChild(btn);
  else document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(btn); });

  function paint() {
    btn.textContent = muted ? '♪ 音乐 关' : '♪ 音乐 开';
    btn.title = '点击或按 M 键切换背景音乐';
    btn.style.opacity = muted ? '0.62' : '1';
    btn.setAttribute('aria-pressed', String(!muted));
  }

  // ---------------------------------------------------------------- 淡入淡出
  var ramp = null;
  function fade(to, ms) {
    if (ramp) { clearInterval(ramp); ramp = null; }
    var from = audio.volume;
    var dt = 40;
    var n = Math.max(1, Math.round(ms / dt));
    var i = 0;
    ramp = setInterval(function () {
      i += 1;
      audio.volume = Math.max(0, Math.min(1, from + (to - from) * (i / n)));
      if (i >= n) { clearInterval(ramp); ramp = null; audio.volume = to; }
    }, dt);
  }

  function play() {
    if (muted) return;
    var p = audio.play();
    if (p && typeof p.catch === 'function') {
      p.then(function () { fade(TARGET, 900); }).catch(function () { /* 等用户手势 */ });
    } else {
      fade(TARGET, 900);
    }
  }

  function setMuted(v) {
    muted = !!v;
    try { localStorage.setItem(STORE_KEY, muted ? '1' : '0'); } catch (e) { /* 无痕模式 */ }
    paint();
    if (muted) {
      fade(0, 320);
      setTimeout(function () { if (muted) audio.pause(); }, 340);
    } else {
      play();
    }
  }

  function toggle() { setMuted(!muted); }

  btn.addEventListener('click', function (e) { e.stopPropagation(); toggle(); });

  // ---------------------------------------------------------------- 首次手势解锁自动播放
  var unlocked = false;
  function unlock() {
    if (unlocked) return;
    unlocked = true;
    play();
    window.removeEventListener('pointerdown', unlock);
    window.removeEventListener('keydown', unlock);
    window.removeEventListener('touchstart', unlock);
  }
  window.addEventListener('pointerdown', unlock, { passive: true });
  window.addEventListener('touchstart', unlock, { passive: true });
  window.addEventListener('keydown', function (e) {
    if (e.code === 'KeyM' || e.key === 'm' || e.key === 'M') { toggle(); return; }
    unlock();
  });

  // 页面被切到后台时淡出一点，回来再淡回来（省电、不打扰）
  document.addEventListener('visibilitychange', function () {
    if (muted) return;
    if (document.hidden) { fade(0, 220); setTimeout(function () { if (document.hidden) audio.pause(); }, 240); }
    else { audio.play().catch(function () {}); fade(TARGET, 500); }
  });

  audio.addEventListener('error', function () {
    btn.style.display = 'none';       // 没有音乐文件时静默退出，不碍事
  });
  audio.addEventListener('canplay', function () { if (!muted) play(); });

  paint();
  play();

  window.__bgm = {
    audio: audio,
    toggle: toggle,
    setMuted: setMuted,
    get muted() { return muted; },
    get playing() { return !audio.paused && audio.volume > 0.01; },
  };
})();
