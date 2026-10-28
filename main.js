/* 深圳海岸小世界 —— 用 AI 参考图逼近出来的像素场景 + 四向螃蟹精灵
 *
 * 资产来源：
 *   assets/bg_base.png     AI 场景图降采样到 960×540 并量化到 64 色的结果
 *   assets/crab_sheet.png   AI 4×4 动作卡切格、抠绿、归一化后的 16 帧（单帧 64×64）
 *   assets/scene.js         可走网格（从背景沙地自动提取）、出生点、水面闪光点
 *
 * 运行参数：逻辑画布 960×540，行走 8 fps，移动 110 px/s，rAF + 时间增量。
 */
(() => {
  'use strict';

  const S = window.SCENE;
  const canvas = document.getElementById('scene');
  const ctx = canvas.getContext('2d', { alpha: false });
  const loadingEl = document.getElementById('loading');
  const loadingText = document.getElementById('loading-text');
  const loadingBar = document.getElementById('loading-bar');

  ctx.imageSmoothingEnabled = false;

  const W = S.w;
  const H = S.h;
  const SPEED = S.speed || 110;
  const ANIM_FPS = S.animFps || 8;
  // 同一个角色的两套尺寸（同一套朝向与动画规则）；key T 或左上角按钮切换
  // 数组顺序：大 → 中 → 小；T 键按「反弹」切换（到两头就掉头，不绕回）
  const SIZES = [
    { name: '96', label: '大', src: 'assets/crab_sheet_96.png', w: 96, h: 96, foot: 86, img: null },
    { name: '48', label: '中', src: 'assets/crab_sheet.png',    w: 48, h: 48, foot: 43, img: null },
    { name: '24', label: '小', src: 'assets/crab_sheet_24.png', w: 24, h: 24, foot: 21, img: null },
  ];
  let sizeIdx = 1;   // 默认 48
  const curSize = () => SIZES[sizeIdx];

  const FW = S.frame.w;
  const FH = S.frame.h;
  // 精灵内脚底所在的行（由切片脚本决定）；用它把脚精确落到角色坐标上，
  // 这样换任何帧尺寸都不会出现"悬空/陷地"。
  const FOOT_LINE = (S.frame && S.frame.footLine) || (FH - 10);
  const KEY_DIR = {
    ArrowUp: 'up', KeyW: 'up',
    ArrowDown: 'down', KeyS: 'down',
    ArrowLeft: 'left', KeyA: 'left',
    ArrowRight: 'right', KeyD: 'right',
  };

  // 可走网格
  const CELL = S.grid.cell;
  const COLS = S.grid.cols;
  const ROWS = S.grid.rows;
  const WALK = S.grid.walk;      // 每行一个 '0'/'1' 字符串

  function walkableAt(x, y) {
    const cx = Math.floor(x / CELL);
    const cy = Math.floor(y / CELL);
    if (cx < 0 || cy < 0 || cx >= COLS || cy >= ROWS) return false;
    return WALK[cy][cx] === '1';
  }

  // ---------------------------------------------------------------- 资源
  const assets = {};
  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('资源加载失败：' + src));
      img.src = src;
    });
  }

  async function loadAll() {
    // 两套尺寸都要就位，切换才不会闪
    const list = [
      ['bg', 'assets/bg_base.png'],
      ['crab96', SIZES[0].src],
      ['crab', SIZES[1].src],
      ['crab24', SIZES[2].src],
    ];
    let done = 0;
    await Promise.all(list.map(async ([key, src]) => {
      assets[key] = await loadImage(src);
      done += 1;
      loadingBar.style.width = Math.round((done / list.length) * 100) + '%';
    }));
  }

  // ---------------------------------------------------------------- 输入
  const pressed = [];
  let facing = 'down';
  let moving = false;

  function pushDir(dir) {
    if (!pressed.includes(dir)) pressed.push(dir);
    setActive(pressed[pressed.length - 1]);
  }
  function popDir(dir) {
    const i = pressed.indexOf(dir);
    if (i >= 0) pressed.splice(i, 1);
    if (pressed.length) setActive(pressed[pressed.length - 1]);
  }

  window.addEventListener('keydown', (e) => {
    const dir = KEY_DIR[e.code];
    if (!dir) return;
    e.preventDefault();
    pushDir(dir);
  }, { passive: false });

  window.addEventListener('keyup', (e) => {
    const dir = KEY_DIR[e.code];
    if (!dir) return;
    e.preventDefault();
    popDir(dir);
  }, { passive: false });

  // ---- 角色尺寸切换（48 ↔ 24）----
  function setSize(i) {
    sizeIdx = i;
    if (sizeBtn) {
      sizeBtn.textContent = '尺寸 ' + curSize().label + ' ' + curSize().name;
      sizeBtn.title = '切换角色尺寸（T 键）';
    }
    sizeBtn && sizeBtn.blur();
  }
  let sizeDir = 1;                 // +1 往小，-1 往大；撞到两头就反向
  function toggleSize() {
    let next = sizeIdx + sizeDir;
    if (next < 0 || next >= SIZES.length) {   // 到端点了，掉头
      sizeDir = -sizeDir;
      next = sizeIdx + sizeDir;
    }
    setSize(next);
  }
  function resetSize() { sizeDir = 1; setSize(1); }

  let sizeBtn = null;
  function mountSizeButton() {
    sizeBtn = document.createElement('button');
    sizeBtn.type = 'button';
    sizeBtn.id = 'size-btn';
    sizeBtn.textContent = '尺寸 ' + curSize().label + ' ' + curSize().name;
    sizeBtn.title = '切换角色尺寸（T 键）';
    sizeBtn.style.cssText = [
      'position:fixed', 'left:18px', 'top:64px', 'z-index:11',
      'padding:7px 12px', 'border-radius:10px', 'cursor:pointer',
      'font:13px/1 "Segoe UI","Microsoft YaHei",system-ui,sans-serif',
      'color:#f3e7cf', 'background:rgba(6,26,34,.62)',
      'border:1px solid rgba(240,226,199,.22)', 'backdrop-filter:blur(4px)',
    ].join(';');
    sizeBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleSize(); });
    document.body.appendChild(sizeBtn);
  }

  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyT' && !e.repeat) { e.preventDefault(); toggleSize(); }
  }, { passive: false });

  window.addEventListener('blur', () => { pressed.length = 0; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pressed.length = 0; });

  // ---------------------------------------------------------------- 玩家
  // ---- 朝向状态机（按角度转，不是按键查表）--------------------------
  // 身体朝向角 bodyDeg：0=朝右 90=朝观众 180=朝左 270=背对观众。
  // 前进方向 heading 永远与身体垂直（螃蟹横着走）。
  // 换方向时的规则：
  //   同方向(0°)、掉头(180°) -> 身体朝向不变，只是在同一轴上正/反横移；
  //   转 90°                 -> 身体跟着转 90°，像画圆弧：外侧仍朝外、内侧仍朝内。
  const ANG = { right: 0, down: 90, left: 180, up: 270 };
  const FACE_BY_ANG = { 0: 'right', 90: 'front', 180: 'left', 270: 'back' };
  const FACE_ROW = S.faceRow || { front: 0, left: 1, right: 2, back: 3 };

  const player = {
    x: S.spawn.x,
    y: S.spawn.y,
    dir: 'down',
    heading: ANG.right,   // 面朝观众时，前进方向是横向
    bodyDeg: 90,          // 初始身体正面朝观众
    frame: 0,
    animT: 0,
    half: 11,
    foot: 6,
  };

  function turnTo(dir) {
    const nh = ANG[dir];
    const delta = ((nh - player.heading + 540) % 360) - 180;   // (-180, 180]
    if (Math.abs(delta) === 90) {
      player.bodyDeg = (player.bodyDeg + delta + 360) % 360;   // 身体跟着画 90° 圆弧
    }
    player.heading = nh;
  }

  function faceNow() {
    return FACE_BY_ANG[player.bodyDeg] || 'front';
  }

  // 生效方向变化时立刻按圆弧规则转身（放在输入事件里，避免掉帧漏转）
  function setActive(next) {
    if (next === player.dir) { facing = next; return; }
    facing = next;
    player.dir = next;
    turnTo(next);
  }

  // 脚步区域四个角都必须站在沙地上
  function canStand(x, y) {
    const hw = player.half;
    const ft = player.foot;
    return walkableAt(x - hw, y - ft)
      && walkableAt(x + hw, y - ft)
      && walkableAt(x - hw, y)
      && walkableAt(x + hw, y);
  }

  // ---------------------------------------------------------------- 帧日志（验收用）
  const frameLog = [];
  let logOn = false;
  function logFrame(dir, idx) {
    if (!logOn) return;
    const last = frameLog[frameLog.length - 1];
    if (last && last.dir === dir && last.idx === idx) return;
    frameLog.push({ t: Math.round(performance.now()), dir, idx });
    if (frameLog.length > 5000) frameLog.shift();
  }

  // ---------------------------------------------------------------- 绘制
  function drawWater(t) {
    // 水面闪光：两条叠加——一条底色短划，最亮时上方再补一条更白的光斑，
    // 形成"闪一下"的波光，而不是整片均匀发亮。
    ctx.save();
    for (const w of S.water) {
      const tw = Math.max(0, Math.sin(t * w.speed + w.phase));
      const a = 0.18 + 0.60 * tw;
      if (a < 0.20) continue;
      ctx.fillStyle = `rgba(226,246,250,${a.toFixed(3)})`;
      ctx.fillRect(w.x, w.y, w.len, 1);
      if (tw > 0.72) {
        // 亮点：上移 1px 的白色小光斑 + 更亮的核心
        ctx.fillStyle = `rgba(255,255,255,${(a * 0.55).toFixed(3)})`;
        ctx.fillRect(w.x + 1, w.y - 1, Math.max(2, w.len - 2), 1);
        ctx.fillStyle = `rgba(255,255,255,${Math.min(0.95, a * 1.25).toFixed(3)})`;
        ctx.fillRect(w.x + (w.len >> 1), w.y, 2, 1);
      }
    }
    ctx.restore();

    // 岸线碎浪：贴着画出来的海岸线起伏，模拟一次次推上沙滩的浪
    if (S.surf) {
      ctx.save();
      for (const s of S.surf) {
        const wave = Math.sin(t * s.speed + s.phase);
        if (wave < 0.15) continue;
        const a = 0.10 + 0.55 * wave;
        const dy = Math.round(wave * 2);
        ctx.fillStyle = `rgba(240,253,255,${a.toFixed(3)})`;
        ctx.fillRect(s.x - s.len / 2, s.y + dy, s.len, 1);
        if (wave > 0.75) {
          ctx.fillStyle = `rgba(255,255,255,${(a * 0.5).toFixed(3)})`;
          ctx.fillRect(s.x - s.len / 4, s.y + dy - 1, Math.round(s.len / 2), 1);
        }
      }
      ctx.restore();
    }
  }

  function drawPlayer() {
    const row = FACE_ROW[faceNow()] ?? 0;
    const sz = curSize();
    const sheet = sz.img || assets.crab;
    const col = player.frame;
    ctx.save();
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = '#1c1208';
    ctx.beginPath();
    const sr = Math.max(5, Math.round(sz.w * 0.29));
    ctx.ellipse(Math.round(player.x), Math.round(player.y) + 1, sr, Math.max(2, Math.round(sr * 0.28)), 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.drawImage(
      sheet,
      col * sz.w, row * sz.h, sz.w, sz.h,
      Math.round(player.x - sz.w / 2), Math.round(player.y - sz.foot), sz.w, sz.h
    );
  }

  function render(t) {
    ctx.drawImage(assets.bg, 0, 0, W, H);
    drawWater(t);
    drawPlayer();
  }

  // ---------------------------------------------------------------- 主循环
  let last = performance.now();
  let elapsed = 0;
  let freezeEnv = false;
  let fpsAvg = 60;
  let longFrame = 0;

  function tick(now) {
    const dtRaw = (now - last) / 1000;
    last = now;
    const dt = Math.min(dtRaw, 0.05);
    if (!freezeEnv) elapsed += dt;
    fpsAvg = fpsAvg * 0.92 + (1 / Math.max(dtRaw, 0.0001)) * 0.08;
    if (dtRaw > 0.05) longFrame += 1;

    moving = pressed.length > 0;
    if (moving) {
      player.dir = facing;
      const step = SPEED * dt;
      let nx = player.x;
      let ny = player.y;
      if (facing === 'left') nx -= step;
      else if (facing === 'right') nx += step;
      else if (facing === 'up') ny -= step;
      else if (facing === 'down') ny += step;

      if (canStand(nx, player.y)) player.x = nx;
      if (canStand(player.x, ny)) player.y = ny;

      player.animT += dt;
      const idx = Math.floor(player.animT * ANIM_FPS) % 4;
      if (idx !== player.frame) {
        player.frame = idx;
        logFrame(player.dir, idx);
      }
    } else {
      player.animT = 0;
      player.frame = 0;
    }

    render(elapsed);

    window.__crab = {
      x: +player.x.toFixed(2), y: +player.y.toFixed(2),
      dir: player.dir, face: faceNow(), row: FACE_ROW[faceNow()],
      bodyDeg: player.bodyDeg, heading: player.heading,
      frame: player.frame, size: curSize().name, moving,
    };

    requestAnimationFrame(tick);
  }

  // ---------------------------------------------------------------- 自适应尺寸
  function fit() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let scale = Math.min((vw * 0.98) / W, (vh * 0.94) / H);
    if (scale >= 1) scale = Math.floor(scale * 4) / 4;
    canvas.style.width = Math.round(W * scale) + 'px';
    canvas.style.height = Math.round(H * scale) + 'px';
  }
  window.addEventListener('resize', fit);

  // ---------------------------------------------------------------- 探针
  window.__probe = {
    get ready() { return !!assets.bg; },
    state() {
      return {
        x: +player.x.toFixed(2), y: +player.y.toFixed(2),
        dir: player.dir, face: faceNow(), row: FACE_ROW[faceNow()],
        bodyDeg: player.bodyDeg, heading: player.heading,
        frame: player.frame, size: curSize().name, moving,
        pressed: pressed.slice(),
      };
    },
    setPos(x, y) { player.x = x; player.y = y; },
    press(code) { window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true })); },
    release(code) { window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true })); },
    releaseAll() { pressed.length = 0; },
    log(on) { logOn = on; if (on) frameLog.length = 0; },
    frames() { return frameLog.slice(); },
    fps() { return +fpsAvg.toFixed(1); },
    longFrames() { return longFrame; },
    resetStats() { longFrame = 0; fpsAvg = 60; },
    freeze(on) { freezeEnv = !!on; },
    walkableAt,
    canStand,
    grid: { cell: CELL, cols: COLS, rows: ROWS },
    canvasRect() {
      const r = canvas.getBoundingClientRect();
      return { x: r.x, y: r.y, w: Math.round(r.width), h: Math.round(r.height) };
    },
    assetsLoaded() { return Object.keys(assets); },
  };

  // ---------------------------------------------------------------- 启动
  (async function boot() {
    try {
      await loadAll();
      SIZES[0].img = assets.crab96;
      SIZES[1].img = assets.crab;
      SIZES[2].img = assets.crab24;
      mountSizeButton();
      loadingText.textContent = '准备就绪';
      fit();
      loadingEl.classList.add('hide');
      setTimeout(() => { loadingEl.style.display = 'none'; }, 500);
      requestAnimationFrame(tick);
    } catch (err) {
      loadingText.textContent = String(err && err.message ? err.message : err);
      loadingBar.style.background = '#e5646e';
    }
  })();
})();
