/* 触屏控件：左侧半透明摇杆（四向）+ 右侧 ABXY
 *
 * - 摇杆：推杆方向按主导轴映射成上/下/左/右（游戏本身只支持四向，不做斜向）
 * - A 键：形状轮询（等同键盘 T：大 96 ↔ 中 48 ↔ 小 24，到两端反弹），
 *         键面下方实时显示当前形状（大/中/小）
 * - B / X / Y：先占位，禁用态（半透明、点了没反应），后续再接功能
 *
 * 只在触屏设备或 URL 带 ?touch=1 时挂载，桌面不干扰键鼠。
 * 挂载后给 <html> 加 .touch-mode：隐藏键盘提示条（摇杆已取代它）。
 * 对外：window.__touch = { visible, dir, hide(), show() }
 */
(() => {
  'use strict';

  const forceTouch = /[?&]touch=1/i.test(location.search);
  const coarse = matchMedia('(pointer: coarse)').matches;
  if (!forceTouch && !coarse) return;

  const DEAD = 10;        // 死区（px）
  const R_MAX = 44;       // 摇杆最大位移

  document.documentElement.classList.add('touch-mode');

  const style = document.createElement('style');
  style.textContent = `
    /* 只在触屏模式注入，所以可以直接盖掉键盘提示 */
    .hud { display: none !important; }

    /* 竖屏：底部留给控件的"操作带"，画布在它上面的区域里居中，
       免得场景贴着摇杆、上面空一大块。横屏画布本来就受限高度，不预留。 */
    html.touch-mode { --touch-band: 236px; }
    @media (orientation: landscape) { html.touch-mode { --touch-band: 0px; } }

    #touch-ui { position: fixed; inset: 0; pointer-events: none; z-index: 12;
                touch-action: none; user-select: none; -webkit-user-select: none;
                -webkit-tap-highlight-color: transparent;
                font: 600 20px/1 "Segoe UI", system-ui, sans-serif; }

    /* ---- 左：半透明摇杆 ---- */
    #stick-base { position: absolute; left: calc(20px + env(safe-area-inset-left, 0px));
                  bottom: calc(22px + env(safe-area-inset-bottom, 0px));
                  width: 132px; height: 132px; border-radius: 50%;
                  background: rgba(243, 231, 207, 0.14);
                  border: 2px solid rgba(243, 231, 207, 0.42);
                  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.22);
                  backdrop-filter: blur(2px); pointer-events: auto; touch-action: none; }
    #stick-knob { position: absolute; left: 37px; top: 37px;
                  width: 58px; height: 58px; border-radius: 50%;
                  background: rgba(243, 231, 207, 0.30);
                  border: 2px solid rgba(243, 231, 207, 0.55);
                  transition: transform 0.06s linear; pointer-events: none; }

    /* ---- 右：ABXY 菱形 ---- */
    #abxy { position: absolute; right: calc(16px + env(safe-area-inset-right, 0px));
            bottom: calc(18px + env(safe-area-inset-bottom, 0px));
            width: 210px; height: 210px;
            transform-origin: bottom right; }
    .abxy-btn { position: absolute; width: 62px; height: 62px; border-radius: 50%;
                display: grid; place-items: center; gap: 0; pointer-events: auto;
                color: #f7efdd;
                /* 内暗外亮的一圈，压在亮沙滩和暗水面上都看得见 */
                background: radial-gradient(circle at 50% 45%,
                            rgba(6, 26, 34, 0.30) 55%, rgba(6, 26, 34, 0.62) 100%);
                border: 2px solid rgba(243, 231, 207, 0.55);
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.28);
                touch-action: none; cursor: pointer; padding: 0; }
    .abxy-btn.pressed { background: rgba(240, 160, 92, 0.45);
                        border-color: rgba(245, 211, 140, 0.85); }
    /* 禁用键：不压整体透明度（压在亮沙滩上会整块消失），
       只把字调暗、描边留一圈，看得出"有键但没接功能" */
    .abxy-btn.disabled { color: rgba(243, 231, 207, 0.50);
                         border-color: rgba(243, 231, 207, 0.40);
                         border-style: dashed; }
    .abxy-btn .sub { font: 700 11px/1 "Segoe UI", system-ui, sans-serif;
                     color: rgba(245, 211, 140, 0.95); margin-top: 1px; }
    #btn-y { left: 74px; top: 0; }
    #btn-x { left: 12px; top: 74px; }
    #btn-b { left: 136px; top: 74px; }
    /* A 键是形状轮询，键面大一点，好按也好读当时是大/中/小 */
    #btn-a { left: 68px; top: 142px; width: 74px; height: 74px;
             background: rgba(6, 26, 34, 0.5); border-color: rgba(243, 231, 207, 0.42);
             display: flex; flex-direction: column; align-items: center; justify-content: center; }
    #btn-a .glyph { font: 700 18px/1 "Segoe UI", system-ui, sans-serif; }

    /* 横屏手机：屏幕矮，控件整体缩一圈，免得把场景全盖住 */
    @media (orientation: landscape) and (max-height: 560px) {
      #abxy { transform: scale(0.78); }
      #stick-base { transform: scale(0.84); transform-origin: bottom left; }
    }
  `;
  document.head.appendChild(style);

  const ui = document.createElement('div');
  ui.id = 'touch-ui';
  ui.innerHTML = `
    <div id="stick-base"><div id="stick-knob"></div></div>
    <div id="abxy">
      <button class="abxy-btn" id="btn-y" type="button">Y</button>
      <button class="abxy-btn" id="btn-x" type="button">X</button>
      <button class="abxy-btn" id="btn-b" type="button">B</button>
      <button class="abxy-btn" id="btn-a" type="button">
        <span class="glyph">A</span><span class="sub">中</span>
      </button>
    </div>
  `;
  document.body.appendChild(ui);

  const base = document.getElementById('stick-base');
  const knob = document.getElementById('stick-knob');
  const input = window.__input;

  let active = false;
  let pid = null;

  function dirFrom(dx, dy) {
    if (Math.hypot(dx, dy) < DEAD) return null;
    return Math.abs(dx) >= Math.abs(dy)
      ? (dx > 0 ? 'right' : 'left')
      : (dy > 0 ? 'down' : 'up');
  }

  function moveKnob(dx, dy) {
    const len = Math.hypot(dx, dy) || 1;
    const k = Math.min(1, R_MAX / len);
    knob.style.transform = `translate(${dx * k}px, ${dy * k}px)`;
  }

  function resetStick() {
    active = false;
    pid = null;
    knob.style.transform = 'translate(0px, 0px)';
    if (input) input.setTouchDir(null);
  }

  function onMove(e) {
    if (!active || e.pointerId !== pid) return;
    const r = base.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2);
    const dy = e.clientY - (r.top + r.height / 2);
    moveKnob(dx, dy);
    if (input) input.setTouchDir(dirFrom(dx, dy));
  }

  base.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    active = true;
    pid = e.pointerId;
    try { base.setPointerCapture(pid); } catch (err) { /* ignore */ }
    onMove(e);
  });
  base.addEventListener('pointermove', onMove);
  base.addEventListener('pointerup', resetStick);
  base.addEventListener('pointercancel', resetStick);
  base.addEventListener('lostpointercapture', resetStick);

  // ---- A 键：形状轮询 ----
  const a = document.getElementById('btn-a');
  const sub = a.querySelector('.sub');

  function paintShape(shape) {
    // shape = '中 48' 这样，取第一个字（大/中/小）
    if (shape && sub) sub.textContent = String(shape).trim().charAt(0);
  }
  paintShape(input && input.shape);
  window.addEventListener('crab:shape', (e) => {
    paintShape(e.detail && e.detail.label);
  });

  a.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    a.classList.add('pressed');
    if (input) input.cycleShape();
    setTimeout(() => a.classList.remove('pressed'), 140);
  });

  // B / X / Y 暂不接功能
  for (const id of ['btn-b', 'btn-x', 'btn-y']) {
    const el = document.getElementById(id);
    el.classList.add('disabled');
    el.addEventListener('pointerdown', (e) => e.preventDefault());
  }

  window.__touch = {
    get visible() { return ui.style.display !== 'none'; },
    get dir() { return input ? input.touchDir : null; },
    get shape() { return sub ? sub.textContent : ''; },
    hide() { ui.style.display = 'none'; },
    show() { ui.style.display = ''; },
  };

  // main.js 先于本文件执行，它首帧算尺寸时 --touch-band 还没定义；
  // 这里补一次，让画布按"扣掉操作带"的可用高度重新适配。
  window.dispatchEvent(new Event('resize'));
})();
