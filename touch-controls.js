/* 触屏控件：左侧半透明摇杆（四向）+ 右侧 ABXY
 *
 * - 摇杆：推杆方向按主导轴映射成上/下/左/右（游戏本身只支持四向，不做斜向）
 * - A 键：形状轮询（等同键盘 T：大 96 ↔ 中 48 ↔ 小 24，到两端反弹），
 *         键面下方实时显示当前形状（大/中/小）
 * - B / X / Y：先占位，禁用态（虚线描边、点了没反应），后续再接功能
 *
 * 挂载条件：触屏设备（pointer:coarse 或 ontouchstart/maxTouchPoints）或 URL 带 ?touch=1。
 * 桌面键鼠不受影响。
 *
 * ⚠️ 输入通道（iOS 踩坑后改成双通道，二选一绑定，不叠加）：
 *   iOS Safari 对 Pointer Events / setPointerCapture 的支持是"2020-07 起广泛可用"，
 *   而且浏览器接管手势时会发 pointercancel。所以：
 *     - 有触摸能力的设备 → 绑 touchstart/touchmove/touchend（iOS/Android 全支持），
 *       用 { passive: false } + preventDefault 自己接管手势；
 *     - 没有触摸能力的设备（桌面预览 ?touch=1）→ 绑 pointerdown + 指针捕获。
 *   两条通道**不会同时绑**，否则同一根手指会被处理两次（pointerdown 与 touchstart 都会来）。
 *
 * 对外：window.__touch = { visible, dir, shape, diag(), hide(), show() }
 * 排障：加 ?diag=1 打开左上角诊断面板，实时显示事件流与设备能力。
 */
(() => {
  'use strict';

  const forceTouch = /[?&]touch=1/i.test(location.search);
  const diagOn = /[?&]diag=1/i.test(location.search);
  const coarse = matchMedia('(pointer: coarse)').matches;

  // ⚠️ 只认 `ontouchstart`：`navigator.maxTouchPoints` 在**没有触摸屏**的桌面浏览器上
  // 也可能是 20（实测 Windows Edge），拿它判断触摸能力会让桌面误挂触屏 UI。
  const hasTouchStart = 'ontouchstart' in window;
  const maxTouchPoints = navigator.maxTouchPoints || 0;
  const canTouch = hasTouchStart || maxTouchPoints > 0;

  // 挂载：触屏设备（pointer:coarse / 真有 touch 事件）或 URL 带 ?touch=1
  if (!forceTouch && !coarse && !hasTouchStart) return;

  // 防重复挂载：脚本若被二次求值（真机上出现过），监听器会翻倍，一个手势触发两次
  if (window.__touch) return;

  // 真有 touch 事件时用 touch 通道（iOS/Android 全支持，不受 Pointer Events 版本差异影响）
  const useTouchPath = hasTouchStart;

  const DEAD = 10;        // 死区（px）
  const R_MAX = 44;       // 摇杆最大位移

  document.documentElement.classList.add('touch-mode');

  const style = document.createElement('style');
  style.textContent = `
    /* 只在触屏模式注入，所以可以直接盖掉键盘提示 */
    .hud { display: none !important; }

    /* 触屏下左上角的「尺寸」按钮是多余的：A 键已经负责换形状，键面还显示当前形状 */
    html.touch-mode #size-btn { display: none !important; }

    /* 竖屏：底部留给控件的"操作带"，画布在它上面的区域里居中，
       免得场景贴着摇杆、上面空一大块。横屏画布本来就受限高度，不预留。 */
    html.touch-mode { --touch-band: 236px; }
    @media (orientation: landscape) { html.touch-mode { --touch-band: 0px; } }
    /* 收起虚拟按键后底部不需要操作带，场景在整屏居中 */
    html.touch-mode.touch-ui-collapsed { --touch-band: 0px; }

    /* iOS：页面本身不要吃手势（橡皮筋 / 双击缩放），但**保留双指缩放**。
       所以这里用 manipulation（= pan-x pan-y pinch-zoom），不能用 none ——
       祖先元素上的 none 会连捏合一起禁掉。控件自己那几个仍然单独设 none。 */
    html.touch-mode, html.touch-mode body {
      touch-action: manipulation; overscroll-behavior: none;
    }

    #touch-ui { position: fixed; inset: 0; pointer-events: none; z-index: 12;
                /* 覆盖层不吞缩放：真正设 none 的是下面的摇杆/按键本身 */
                touch-action: manipulation; user-select: none; -webkit-user-select: none;
                -webkit-touch-callout: none; -webkit-tap-highlight-color: transparent;
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
                touch-action: none; cursor: pointer; padding: 0;
                -webkit-appearance: none; appearance: none; }
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

    /* ---- 右上：虚拟按键的显示/隐藏开关（样式与右上角「音乐」按钮对齐）---- */
    #touch-toggle { position: absolute; right: calc(18px + env(safe-area-inset-right, 0px));
                    top: 58px; padding: 7px 12px; border-radius: 10px;
                    display: flex; align-items: center; gap: 6px; cursor: pointer;
                    font: 13px/1 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
                    color: #f3e7cf; background: rgba(6, 26, 34, 0.62);
                    border: 1px solid rgba(240, 226, 199, 0.22);
                    backdrop-filter: blur(4px); pointer-events: auto; touch-action: none;
                    -webkit-appearance: none; appearance: none; }

    /* 收起状态：只藏摇杆和 ABXY，开关自己必须留着，否则没法再打开 */
    #touch-ui.collapsed #stick-base,
    #touch-ui.collapsed #abxy { display: none; }

    /* 横屏手机：屏幕矮，控件整体缩一圈，免得把场景全盖住 */
    @media (orientation: landscape) and (max-height: 560px) {
      #abxy { transform: scale(0.78); }
      #stick-base { transform: scale(0.84); transform-origin: bottom left; }
    }

    /* ---- 排障面板（?diag=1） ---- */
    #touch-diag { position: absolute; left: 8px; top: 8px; max-width: 92vw;
                  padding: 6px 8px; border-radius: 8px;
                  background: rgba(0, 0, 0, 0.72); color: #9fe8ff;
                  font: 10px/1.45 ui-monospace, Menlo, Consolas, monospace;
                  white-space: pre-wrap; word-break: break-all; pointer-events: none; }
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
    <button id="touch-toggle" type="button">⌄ 收起按键</button>
  `;
  document.body.appendChild(ui);

  const base = document.getElementById('stick-base');
  const knob = document.getElementById('stick-knob');

  // ⚠️ 不再在挂载时把 __input 存成常量：main.js 若出错或晚到，那会让摇杆和 A 键
  // 一起静默失效（`if (input)` 全跳过了，控制台还不报错）。改成每次现取。
  const getInput = () => window.__input || null;

  // ---------------- 诊断面板 ----------------
  const events = [];
  let diagEl = null;
  if (diagOn) {
    diagEl = document.createElement('div');
    diagEl.id = 'touch-diag';
    ui.appendChild(diagEl);
  }
  function note(kind, x, y) {
    events.push(x == null ? kind : `${kind}(${Math.round(x)},${Math.round(y)})`);
    if (events.length > 7) events.shift();
    if (diagEl) paintDiag();
  }
  function paintDiag() {
    const inp = getInput();
    diagEl.textContent = [
      `path=${useTouchPath ? 'touch+pointer' : 'pointer'}  input=${inp ? 'ok' : 'MISSING'}`,
      `touchEv=${hasTouchStart ? 1 : 0} maxTP=${maxTouchPoints} coarse=${coarse ? 1 : 0}`,
      `dir=${inp ? inp.touchDir : '-'}  shape=${inp ? inp.shape : '-'}`,
      `vp=${innerWidth}x${innerHeight} dpr=${devicePixelRatio}`,
      `ev: ${events.join(' ') || '(无事件)'}`,
    ].join('\n');
  }
  if (diagEl) paintDiag();

  // ---------------- 摇杆 ----------------
  let dragging = false;
  let pointerId = null;      // pointer 通道
  let touchId = null;        // touch 通道

  function dirFrom(dx, dy) {
    if (Math.hypot(dx, dy) < DEAD) return null;
    return Math.abs(dx) >= Math.abs(dy)
      ? (dx > 0 ? 'right' : 'left')
      : (dy > 0 ? 'down' : 'up');
  }

  function applyPoint(clientX, clientY) {
    const r = base.getBoundingClientRect();
    const dx = clientX - (r.left + r.width / 2);
    const dy = clientY - (r.top + r.height / 2);
    const len = Math.hypot(dx, dy) || 1;
    const k = Math.min(1, R_MAX / len);
    knob.style.transform = `translate(${dx * k}px, ${dy * k}px)`;
    const inp = getInput();
    if (inp) inp.setTouchDir(dirFrom(dx, dy));
    if (diagEl) paintDiag();
  }

  function resetStick() {
    dragging = false;
    pointerId = null;
    touchId = null;
    knob.style.transform = 'translate(0px, 0px)';
    const inp = getInput();
    if (inp) inp.setTouchDir(null);
    if (diagEl) paintDiag();
  }

  if (useTouchPath) {
    // ---- touch 通道（iOS / Android）----
    base.addEventListener('touchstart', (e) => {
      if (touchId !== null) return;                 // 已经在拖了，忽略第二根手指
      const t = e.changedTouches[0];
      if (!t) return;
      e.preventDefault();                           // 自己接管手势，别让页面滚动/缩放
      dragging = true;
      touchId = t.identifier;
      note('touchstart', t.clientX, t.clientY);
      applyPoint(t.clientX, t.clientY);
    }, { passive: false });

    // move/end 绑在 document 上：手指拖出摇杆范围后仍然收得到
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
          note(type);
          resetStick();
          return;
        }
      }, { passive: true });
    }
  }

  // ---- pointer 通道：鼠标 / 触控笔，以及没有 touch 事件的浏览器 ----
  // 有 touch 通道时也要绑：带触摸屏的笔记本上用鼠标照样能拖。
  // 同一次触摸手势浏览器会同时发 touchstart 和 pointerdown(pointerType='touch')，
  // 所以那种 pointer 事件必须跳过，否则一次拖动会被处理两遍。
  const skipTouchPointer = (e) => useTouchPath && e.pointerType === 'touch';

  base.addEventListener('pointerdown', (e) => {
    if (skipTouchPointer(e)) return;
    if (dragging) return;                           // touch 通道已经在拖了
    e.preventDefault();
    dragging = true;
    pointerId = e.pointerId;
    try { base.setPointerCapture(pointerId); } catch (err) { /* ignore */ }
    note('pointerdown', e.clientX, e.clientY);
    applyPoint(e.clientX, e.clientY);
  });
  base.addEventListener('pointermove', (e) => {
    if (skipTouchPointer(e)) return;
    if (!dragging || touchId !== null || e.pointerId !== pointerId) return;
    applyPoint(e.clientX, e.clientY);
  });
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    base.addEventListener(type, (e) => {
      if (skipTouchPointer(e)) return;
      if (!dragging || touchId !== null) return;
      if (e.pointerId != null && e.pointerId !== pointerId) return;
      note(type);
      resetStick();
    });
  }

  // ---------------- A 键：形状轮询 ----------------
  const a = document.getElementById('btn-a');
  const sub = a.querySelector('.sub');

  function paintShape(shape) {
    if (shape && sub) sub.textContent = String(shape).trim().charAt(0);
  }
  paintShape(getInput() && getInput().shape);
  window.addEventListener('crab:shape', (e) => {
    paintShape(e.detail && e.detail.label);
  });

  // 一个按键的"按下"语义：touchstart（touch 通道，preventDefault 掉合成 click）
  // 与 pointerdown（鼠标/触控笔）都绑，触摸产生的 pointerdown 跳过，避免按一次触发两下。
  function bindPress(el, onPress) {
    if (useTouchPath) {
      el.addEventListener('touchstart', (e) => {
        e.preventDefault();
        onPress();
      }, { passive: false });
    }
    el.addEventListener('pointerdown', (e) => {
      if (skipTouchPointer(e)) return;
      e.preventDefault();
      onPress();
    });
  }

  bindPress(a, () => {
    a.classList.add('pressed');
    const inp = getInput();
    if (inp) inp.cycleShape();
    note('A');
    setTimeout(() => a.classList.remove('pressed'), 140);
  });

  // B / X / Y 暂不接功能
  for (const id of ['btn-b', 'btn-x', 'btn-y']) {
    const el = document.getElementById(id);
    el.classList.add('disabled');
    bindPress(el, () => note(id));
  }

  // ---------------- 虚拟按键 显示 / 隐藏 ----------------
  // 收起时只藏摇杆和 ABXY，开关自己留在右上角，否则没法再打开。
  // 不写 localStorage：收起状态若被记住，下次进来一片空白会被当成"坏了"。
  const toggle = document.getElementById('touch-toggle');

  function paintToggle(on) {
    toggle.textContent = on ? '☰ 显示按键' : '⌄ 收起按键';
    toggle.title = on ? '显示虚拟按键' : '隐藏虚拟按键';
  }

  function setCollapsed(v) {
    const on = !!v;
    if (on === ui.classList.contains('collapsed')) return;
    ui.classList.toggle('collapsed', on);
    document.documentElement.classList.toggle('touch-ui-collapsed', on);
    paintToggle(on);
    if (on) resetStick();              // 收起时别让角色继续走
    note(on ? 'hide' : 'show');
    // 操作带高度变了（竖屏 236 ↔ 0），让画布重新适配
    window.dispatchEvent(new Event('resize'));
  }
  paintToggle(false);
  bindPress(toggle, () => setCollapsed(!ui.classList.contains('collapsed')));

  window.__touch = {
    // 指「摇杆 + ABXY 是否可见」，与右上角开关同义（开关自己一直可见）
    get visible() { return !ui.classList.contains('collapsed'); },
    get collapsed() { return ui.classList.contains('collapsed'); },
    get dir() { const i = getInput(); return i ? i.touchDir : null; },
    get shape() { return sub ? sub.textContent : ''; },
    get path() { return useTouchPath ? 'touch+pointer' : 'pointer'; },
    diag() {
      const i = getInput();
      return {
        path: useTouchPath ? 'touch+pointer' : 'pointer',
        inputReady: !!i,
        hasTouchStart, canTouch, coarse, maxTouchPoints,
        dir: i ? i.touchDir : null,
        shape: i ? i.shape : null,
        collapsed: ui.classList.contains('collapsed'),
        events: events.slice(),
        viewport: [innerWidth, innerHeight],
        dpr: devicePixelRatio,
      };
    },
    // 与右上角开关同一条路径，避免出现"API 说隐藏了但开关文案没变"
    hide() { setCollapsed(true); },
    show() { setCollapsed(false); },
  };

  // main.js 先于本文件执行，它首帧算尺寸时 --touch-band 还没定义；
  // 这里补一次，让画布按"扣掉操作带"的可用高度重新适配。
  window.dispatchEvent(new Event('resize'));
})();
