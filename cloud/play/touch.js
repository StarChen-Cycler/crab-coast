'use strict';
/* 多人版触屏控件层（T1）
 *
 * 与单机版 `touch-controls.js` **同一套参数与手感**，只是把「写死调 __input」
 * 改成「回调注入」，好让多人版把意图发给服务端而不是本地角色。
 *
 * 用法：
 *   const tc = window.createTouchControls({
 *     mount: document.body,
 *     onIntent: (dir) => sendIntent(dir),        // dir: up|down|left|right|null
 *     onCollapse: (collapsed) => fit(),          // 折叠后需要重算画布
 *   });
 *
 * 参数来源：单机版契约（见 ASSET-PIPELINE.md 2.6 与 touch-controls.js）。
 * 多人版没有尺寸轮询，因此 ABXY 四键一律禁用占位，不绑定任何功能。
 */
(() => {
  if (window.createTouchControls) return;   // 重复引入直接返回

  // ---- 具名常量：数值均来自单机版已验证的实现 ----
  const DEAD_PX = 10;                        // 死区：小于此推杆距离不产生方向
  const KNOB_MAX_PX = 44;                    // 摇杆头最大位移
  const STICK_SIZE_PX = 132;                 // 摇杆底座直径
  const KNOB_SIZE_PX = 58;                   // 摇杆头直径
  const KNOB_OFFSET_PX = (STICK_SIZE_PX - KNOB_SIZE_PX) / 2;  // 居中偏移
  const ABXY_SIZE_PX = 210;                  // 菱形外接盒
  const BTN_SIZE_PX = 62;
  const A_SIZE_PX = 74;
  const BAND_PORTRAIT_PX = 236;              // 竖屏底部预留的操作带高度
  const SHORT_LANDSCAPE_MAX_H = 560;         // 矮屏判定阈值
  const ABXY_SCALE_SHORT = 0.78;             // 矮屏横屏缩放（与单机版一致）
  const STICK_SCALE_SHORT = 0.84;
  const REPEAT_MOVE_MS = 1000;               // 前端续期间隔（服务端 TTL 3000ms 的 1/3）

  const hasTouchStart = 'ontouchstart' in window;
  const coarse = matchMedia('(pointer: coarse)').matches;
  const forceTouch = /[?&]touch=1/i.test(location.search);

  function dirFrom(dx, dy) {
    if (Math.hypot(dx, dy) < DEAD_PX) return null;
    return Math.abs(dx) >= Math.abs(dy)
      ? (dx > 0 ? 'right' : 'left')
      : (dy > 0 ? 'down' : 'up');
  }

  function injectStyle() {
    if (document.getElementById('touch-layer-style')) return;
    const style = document.createElement('style');
    style.id = 'touch-layer-style';
    style.textContent = `
      html.touch-mode { --touch-band: ${BAND_PORTRAIT_PX}px; }
      @media (orientation: landscape) { html.touch-mode { --touch-band: 0px; } }
      html.touch-mode.touch-ui-collapsed { --touch-band: 0px; }
      /* 画布容器在操作带之上居中 */
      html.touch-mode #stage { bottom: var(--touch-band, 0px); }

      #touch-ui { position: fixed; inset: 0; pointer-events: none; z-index: 12;
                  touch-action: manipulation; user-select: none; -webkit-user-select: none;
                  -webkit-touch-callout: none; -webkit-tap-highlight-color: transparent; }

      #stick-base { position: absolute;
                    left: calc(20px + env(safe-area-inset-left, 0px));
                    bottom: calc(22px + env(safe-area-inset-bottom, 0px));
                    width: ${STICK_SIZE_PX}px; height: ${STICK_SIZE_PX}px; border-radius: 50%;
                    background: rgba(243, 231, 207, 0.14);
                    border: 2px solid rgba(243, 231, 207, 0.42);
                    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.22);
                    backdrop-filter: blur(2px); pointer-events: auto; touch-action: none; }
      #stick-knob { position: absolute; left: ${KNOB_OFFSET_PX}px; top: ${KNOB_OFFSET_PX}px;
                    width: ${KNOB_SIZE_PX}px; height: ${KNOB_SIZE_PX}px; border-radius: 50%;
                    background: rgba(243, 231, 207, 0.30);
                    border: 2px solid rgba(243, 231, 207, 0.55);
                    transition: transform 0.06s linear; pointer-events: none; }

      #abxy { position: absolute;
              right: calc(16px + env(safe-area-inset-right, 0px));
              bottom: calc(18px + env(safe-area-inset-bottom, 0px));
              width: ${ABXY_SIZE_PX}px; height: ${ABXY_SIZE_PX}px;
              transform-origin: bottom right; }
      .abxy-btn { position: absolute; width: ${BTN_SIZE_PX}px; height: ${BTN_SIZE_PX}px;
                  border-radius: 50%; display: grid; place-items: center;
                  color: rgba(243, 231, 207, 0.55);
                  background: radial-gradient(circle at 50% 45%,
                              rgba(6, 26, 34, 0.30) 55%, rgba(6, 26, 34, 0.62) 100%);
                  border: 2px dashed rgba(243, 231, 207, 0.40);
                  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.28);
                  pointer-events: auto; touch-action: none; padding: 0;
                  -webkit-appearance: none; appearance: none;
                  font: 600 18px/1 "Segoe UI", system-ui, sans-serif; }
      #btn-y { left: 74px; top: 0; }
      #btn-x { left: 12px; top: 74px; }
      #btn-b { left: 136px; top: 74px; }
      #btn-a { left: 68px; top: 142px; width: ${A_SIZE_PX}px; height: ${A_SIZE_PX}px; }

      #touch-toggle { position: absolute;
                      right: calc(18px + env(safe-area-inset-right, 0px)); top: 58px;
                      padding: 7px 12px; border-radius: 10px; display: flex;
                      align-items: center; gap: 6px; cursor: pointer;
                      font: 13px/1 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
                      color: #f3e7cf; background: rgba(6, 26, 34, 0.62);
                      border: 1px solid rgba(240, 226, 199, 0.22);
                      backdrop-filter: blur(4px); pointer-events: auto; touch-action: none;
                      -webkit-appearance: none; appearance: none; }
      /* 横屏：顶部只放得下一行，开关移到左上与右上音乐位置对称，避免被 ABXY 顶住 */
      @media (orientation: landscape) {
        #touch-toggle { left: calc(18px + env(safe-area-inset-left, 0px));
                        right: auto; top: calc(16px + env(safe-area-inset-top, 0px)); }
      }
      @media (orientation: landscape) and (max-height: ${SHORT_LANDSCAPE_MAX_H}px) {
        #abxy { transform: scale(${ABXY_SCALE_SHORT}); }
        #stick-base { transform: scale(${STICK_SCALE_SHORT}); transform-origin: bottom left; }
      }

      #touch-ui.collapsed #stick-base,
      #touch-ui.collapsed #abxy { display: none; }
    `;
    document.head.appendChild(style);
  }

  function createTouchControls(opts = {}) {
    const { mount = document.body, onIntent = () => {}, onCollapse = () => {} } = opts;
    if (!forceTouch && !coarse && !hasTouchStart) return null;   // 桌面不挂载

    injectStyle();
    document.documentElement.classList.add('touch-mode');

    const ui = document.createElement('div');
    ui.id = 'touch-ui';
    ui.innerHTML = `
      <div id="stick-base"><div id="stick-knob"></div></div>
      <div id="abxy">
        <button class="abxy-btn" id="btn-y" type="button" disabled>Y</button>
        <button class="abxy-btn" id="btn-x" type="button" disabled>X</button>
        <button class="abxy-btn" id="btn-b" type="button" disabled>B</button>
        <button class="abxy-btn" id="btn-a" type="button" disabled>A</button>
      </div>
      <button id="touch-toggle" type="button">⌄ 收起按键</button>
    `;
    mount.appendChild(ui);

    const base = ui.querySelector('#stick-base');
    const knob = ui.querySelector('#stick-knob');
    const toggle = ui.querySelector('#touch-toggle');

    let dragging = false;
    let pointerId = null;
    let touchId = null;
    let lastDir = null;
    let collapsed = false;

    function emit(dir) {
      if (dir === lastDir) return;
      lastDir = dir;
      onIntent(dir);
    }

    function applyPoint(clientX, clientY) {
      const r = base.getBoundingClientRect();
      const dx = clientX - (r.left + r.width / 2);
      const dy = clientY - (r.top + r.height / 2);
      const len = Math.hypot(dx, dy) || 1;
      const k = Math.min(1, KNOB_MAX_PX / len);
      knob.style.transform = `translate(${dx * k}px, ${dy * k}px)`;
      emit(dirFrom(dx, dy));
    }

    function reset() {
      dragging = false;
      pointerId = null;
      touchId = null;
      knob.style.transform = 'translate(0px, 0px)';
      emit(null);
    }

    // ---- 触摸通道（有 touch 事件时优先，与 pointer 通道不叠加）----
    if (hasTouchStart) {
      base.addEventListener('touchstart', (e) => {
        if (touchId !== null) return;
        const t = e.changedTouches[0];
        if (!t) return;
        e.preventDefault();
        dragging = true;
        touchId = t.identifier;
        applyPoint(t.clientX, t.clientY);
      }, { passive: false });

      document.addEventListener('touchmove', (e) => {
        if (touchId === null) return;
        for (const t of e.changedTouches) {
          if (t.identifier !== touchId) continue;
          e.preventDefault();
          applyPoint(t.clientX, t.clientY);
          return;
        }
      }, { passive: false });

      for (const type of ['touchend', 'touchcancel']) {
        document.addEventListener(type, (e) => {
          if (touchId === null) return;
          for (const t of e.changedTouches) {
            if (t.identifier !== touchId) continue;
            reset();
            return;
          }
        }, { passive: true });
      }
    }

    // ---- pointer 通道（鼠标/触控笔；触摸产生的 pointer 事件跳过）----
    const skipTouchPointer = (e) => hasTouchStart && e.pointerType === 'touch';

    base.addEventListener('pointerdown', (e) => {
      if (skipTouchPointer(e) || dragging) return;
      e.preventDefault();
      dragging = true;
      pointerId = e.pointerId;
      try { base.setPointerCapture(pointerId); } catch { /* ignore */ }
      applyPoint(e.clientX, e.clientY);
    });
    base.addEventListener('pointermove', (e) => {
      if (skipTouchPointer(e) || !dragging || touchId !== null) return;
      if (e.pointerId !== pointerId) return;
      applyPoint(e.clientX, e.clientY);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      base.addEventListener(type, (e) => {
        if (skipTouchPointer(e) || touchId !== null) return;
        if (e.pointerId != null && e.pointerId !== pointerId) return;
        reset();
      });
    }

    // ---- ABXY：全部禁用占位（多人版无尺寸轮询，不编造功能）----
    for (const btn of ui.querySelectorAll('.abxy-btn')) {
      btn.classList.add('disabled');
      btn.addEventListener('pointerdown', (e) => e.preventDefault());
      btn.addEventListener('touchstart', (e) => e.preventDefault(), { passive: false });
    }

    // ---- 收起 / 显示 ----
    function setCollapsed(next) {
      const on = !!next;
      if (on === collapsed) return;
      collapsed = on;
      ui.classList.toggle('collapsed', on);
      document.documentElement.classList.toggle('touch-ui-collapsed', on);
      toggle.textContent = on ? '☰ 显示按键' : '⌄ 收起按键';
      if (on) reset();                 // 收起时别让动物继续走
      onCollapse(on);
    }
    function bindPress(el, fn) {
      if (hasTouchStart) {
        el.addEventListener('touchstart', (e) => { e.preventDefault(); fn(); }, { passive: false });
      }
      el.addEventListener('pointerdown', (e) => {
        if (skipTouchPointer(e)) return;
        e.preventDefault();
        fn();
      });
    }
    bindPress(toggle, () => setCollapsed(!collapsed));

    // 页面隐藏时松开，避免一直在走
    window.addEventListener('pagehide', () => reset());

    return {
      get collapsed() { return collapsed; },
      setCollapsed,
      reset,
      destroy() {
        reset();
        ui.remove();
        document.documentElement.classList.remove('touch-mode', 'touch-ui-collapsed');
      },
      // 验收探针
      _debug: { base, knob, toggle, DEAD_PX, KNOB_MAX_PX, REPEAT_MOVE_MS },
    };
  }

  window.createTouchControls = createTouchControls;
})();
