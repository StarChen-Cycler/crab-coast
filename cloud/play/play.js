'use strict';
/* 多人前端（REQ-000011 / REQ-000013）
   流程：token → 查卡片 → 有卡进游戏 / 无卡显示拖拽上传 → 上传成功后进游戏
   实时：WebSocket 10Hz 快照；输入只发意图，位置由服务端定。 */

(() => {
  const q = new URLSearchParams(location.search);
  const token = q.get('t');
  const cv = document.getElementById('world');
  const ctx = cv.getContext('2d');
  const selfHud = document.getElementById('self-hud');
  const nearHud = document.getElementById('near-hud');
  const linkHud = document.getElementById('link-hud');
  const dz = document.getElementById('dropzone');
  const dzBox = document.getElementById('dz-box');
  const dzErr = document.getElementById('dz-err');
  const dzFile = document.getElementById('dz-file');

  const CARD_ORDER = ['down', 'left', 'right', 'up'];
  const FRAME = 48;
  const FOOT_OFFSET = 43;        // 卡片里脚底线在第 43 行（与 shared/const.js CARD.footLine 一致）
  const VIEW_MIN_PX = 120;       // 视口异常（隐藏标签页等）时的兜底尺寸
  const REFIT_POLL_MS = 400;     // 浏览器工具栏收放不派发 resize，靠轮询补一次重算
  // 连接自愈（REQ-000019）：10Hz 快照，正常间隔 100ms；2.5 秒没有快照就当半开连接处理
  const STALE_MS = 2500;
  const WATCHDOG_MS = 1000;
  const RECONNECT_MIN_GAP_MS = 1000;   // 重建节流：反复旋屏/抖动不产生连接风暴
  // 插值渲染（REQ-000020）：按实测到达间隔 EMA 推进，钳到 [60,300]ms，不做外推
  const INTERP_MIN_MS = 60;
  const INTERP_MAX_MS = 300;
  const INTERP_EMA = 0.35;
  const MAX_FRAME_STEP_PX = 12;  // 单帧位移上限（防丢包后一次跳很远）

  // 世界尺寸：启动时从 /api/v1/world 拿，取不到就用默认值（与 shared/const.js 一致）
  let worldW = 960;
  let worldH = 540;
  // 相机窗口：w/h = 画布 CSS 尺寸（1 逻辑像素 = 1 CSS 像素）；
  // vw/vh = 实际可见的世界范围（超过世界时取世界尺寸）；ox/oy = 世界在画布内的居中留白
  const camera = { x: 0, y: 0, w: 960, h: 540, vw: 960, vh: 540, ox: 0, oy: 0 };
  let drawnIds = [];             // 本帧真正绘制出来的 id（AC-000073 / AC-000085 用）
  let renderSelf = { x: 500, y: 412 };   // 插值后的自己（绘制与相机都用它）
  let started = false;           // startGame() 之后才启用连接自愈
  let animalId = null;
  let bg = null;
  let cardImg = null;
  let cardOf = {};            // id → Image
  let ws = null;
  let retry = 0;
  let stopped = false;
  let keepTimer = null;
  const KEEPALIVE_MS = 1000;
  let snapshot = null;
  let lastSnapAt = 0;
  let intent = null;
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

  function fail(msg) {
    linkHud.textContent = msg;
    linkHud.classList.add('bad');
  }

  function api(path, opts = {}) {
    const h = Object.assign({}, opts.headers);
    if (opts.body !== undefined) h['content-type'] = 'application/json';
    h.authorization = `Bearer ${token}`;
    return fetch(path, { method: opts.method || 'GET', headers: h,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body) });
  }

  // ---------------- 启动 ----------------
  async function boot() {
    if (!token) { fail('链接缺少 token'); return; }
    selfHud.textContent = '检查动作卡…';
    // 只拿得到 token，所以用 me 这个别名（服务端按 token 解析成真实 id）
    const r = await api('/api/v1/animals/me/card-status');
    if (r.status === 401) { fail('token 无效或已被轮换'); return; }
    if (!r.ok) { fail(`卡片状态查询失败（${r.status}）`); return; }
    const st = await r.json();
    animalId = st.animalId;
    if (st.hasCard) { await startGame(); } else { showDropzone(); }
  }

  function showDropzone() {
    dz.classList.add('show');
    document.getElementById('self-hud').textContent = `${animalId || ''} 等待动作卡`;
  }

  async function startGame() {
    dz.classList.remove('show');
    await loadWorld();
    bg = await loadImage('/assets/bg_base.png');
    fit();
    mountTouchControls();
    started = true;
    connect();
    requestAnimationFrame(loop);
  }

  /** 世界尺寸与半径上限（服务端仍是权威；这里只用于相机与半径推导）。 */
  async function loadWorld() {
    try {
      const r = await fetch('/api/v1/world');
      if (!r.ok) return;
      const j = await r.json();
      if (j && j.w > 0 && j.h > 0) { worldW = j.w; worldH = j.h; }
    } catch { /* 拿不到就用默认值，不阻塞进游戏 */ }
  }

  function loadImage(src) {
    return new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => res(img);
      img.onerror = () => rej(new Error('图片加载失败：' + src));
      img.src = src;
    });
  }

  // ---------------- WebSocket（REQ-000011 / 000019 / 000021） ----------------
  // 浏览器拿的是全量快照，没有半径参数可调；重连也不再只靠 onclose——
  // 手机切后台/旋屏会留下「半开连接」：没有 close 事件、也没有数据。
  function connect() {
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?t=${encodeURIComponent(token)}`);
    ws.onopen = () => {
      retry = 0;
      lastSnapAt = performance.now();
      linkHud.textContent = '已连接';
      linkHud.classList.remove('bad');
      if (intent) sendIntent(intent);
    };
    ws.onmessage = (m) => {
      let msg;
      try { msg = JSON.parse(m.data); } catch { return; }
      if (msg.type === 'snapshot') { absorbSnapshot(msg); }
    };
    ws.onclose = (ev) => {
      // 被更新的会话取代：不自作主张重连，否则两个标签页会互相顶掉
      if (ev && ev.code === 1008 && /replace/i.test(ev.reason || '')) {
        stopped = true;
        stopKeepalive();
        linkHud.textContent = '已在别处被接管';
        linkHud.classList.add('bad');
        return;
      }
      if (stopped) return;
      // 主动重建（forceReconnect）已经排好了新连接，这里不要再排一次
      if (reconnectPending) return;
      linkHud.textContent = '重连中…';
      linkHud.classList.add('bad');
      retry = Math.min(retry + 1, 6);
      setTimeout(connect, Math.min(500 * 2 ** (retry - 1), 8000));
    };
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
  }

  /** 显式重建连接：幂等 + 1s 节流，不依赖 onclose（半开连接往往没有 close 事件）。 */
  let reconnectPending = false;
  let lastReconnectAt = -Infinity;
  let reconnectCount = 0;
  function forceReconnect(reason) {
    if (stopped) return false;
    const now = performance.now();
    if (reconnectPending) return false;                       // 已经在重建
    if (now - lastReconnectAt < RECONNECT_MIN_GAP_MS) return false;  // 节流
    if (!ws && !token) return false;
    lastReconnectAt = now;
    reconnectPending = true;
    reconnectCount++;
    console.info('[play] reconnect:', reason);
    try { if (ws) ws.close(); } catch { /* ignore */ }
    ws = null;
    linkHud.textContent = '重连中…';
    linkHud.classList.add('bad');
    setTimeout(() => { reconnectPending = false; connect(); }, 0);
    return true;
  }

  /** 连接体检：可见性恢复、pageshow、online、切回前台时都调一次。 */
  function checkLiveness(reason) {
    if (stopped) return;
    const dead = !ws || ws.readyState === 2 || ws.readyState === 3;
    const stale = performance.now() - lastSnapAt > STALE_MS;
    if (dead) { lastReconnectAt = -Infinity; forceReconnect(reason + ':dead'); }
    else if (stale) forceReconnect(reason + ':stale');
  }

  // 看门狗：半开连接没有 close 事件，只能靠「有没有数据」判断
  setInterval(() => {
    if (!started || stopped || !token) return;
    if (performance.now() - lastSnapAt > STALE_MS) checkLiveness('watchdog');
  }, WATCHDOG_MS);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') checkLiveness('visible');
  });
  window.addEventListener('pageshow', (e) => { if (e.persisted) { lastReconnectAt = -Infinity; checkLiveness('pageshow'); } });
  window.addEventListener('online', () => { lastReconnectAt = -Infinity; checkLiveness('online'); });
  window.addEventListener('focus', () => checkLiveness('focus'));

  // ---------------- 插值（REQ-000020） ----------------
  // 服务端 10Hz 快照 + 位置取整：直接画会每 100ms 跳 11px。这里在两次快照之间线性插值，
  // 渲染始终落在「上一帧渲染位置 → 新快照位置」之间的 alpha 上（不做外推、不做预测）。
  const interp = new Map();      // id -> { fromX, fromY, toX, toY, startAt }
  let snapInterval = 100;        // 快照到达间隔的 EMA（ms）
  let prevSnapArrival = 0;

  function lerpTarget(id, tx, ty, now) {
    const cur = interp.get(id);
    if (!cur) {                                  // 首见：直接置位，不做「从 (0,0) 飞过来」
      interp.set(id, { fromX: tx, fromY: ty, toX: tx, toY: ty, startAt: now });
      return;
    }
    // from 用「当前渲染值」，保证不跳变
    const p = sampleInterp(cur, now);
    let dx = tx - p.x;
    let dy = ty - p.y;
    const d = Math.hypot(dx, dy);
    if (d > MAX_FRAME_STEP_PX) {                 // 丢包/瞬移：限幅，避免一帧跨很远
      dx = (dx / d) * MAX_FRAME_STEP_PX;
      dy = (dy / d) * MAX_FRAME_STEP_PX;
    }
    cur.fromX = p.x; cur.fromY = p.y;
    cur.toX = p.x + dx; cur.toY = p.y + dy;
    cur.startAt = now;
  }

  function sampleInterp(it, now) {
    const span = Math.max(1, snapInterval);
    const a = clamp((now - it.startAt) / span, 0, 1);
    return { x: it.fromX + (it.toX - it.fromX) * a, y: it.fromY + (it.toY - it.fromY) * a };
  }

  function renderPos(id, now) {
    const it = interp.get(id);
    return it ? sampleInterp(it, now) : null;
  }

  /** 收到快照：更新插值目标 + 记录到达间隔（供 alpha 计时）。 */
  function absorbSnapshot(msg) {
    const now = performance.now();
    if (prevSnapArrival) {
      const dt = now - prevSnapArrival;
      snapInterval = Math.round(
        clamp(snapInterval * (1 - INTERP_EMA) + clamp(dt, INTERP_MIN_MS, INTERP_MAX_MS) * INTERP_EMA,
          INTERP_MIN_MS, INTERP_MAX_MS));
    }
    prevSnapArrival = now;
    lastSnapAt = now;
    snapshot = msg;
    const seen = new Set();
    lerpTarget(msg.self.id, msg.self.x, msg.self.y, now);
    seen.add(msg.self.id);
    for (const n of msg.nearby) { lerpTarget(n.id, n.x, n.y, now); seen.add(n.id); }
    for (const id of interp.keys()) if (!seen.has(id)) interp.delete(id);   // 离开世界的移除
    if (stopped) return;
    linkHud.textContent = '已连接';
    linkHud.classList.remove('bad');
  }


  // 按住期间每 1 秒续期一次，使服务端的 3 秒 TTL 只作用于真正失联的来源
  function startKeepalive() {
    if (keepTimer) return;
    keepTimer = setInterval(() => {
      if (intent && ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ type: 'intent', dir: intent }));
      }
    }, KEEPALIVE_MS);
  }
  function stopKeepalive() {
    if (keepTimer) { clearInterval(keepTimer); keepTimer = null; }
  }

  function sendIntent(dir) {
    intent = dir;
    if (dir) startKeepalive(); else stopKeepalive();
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: 'intent', dir }));
  }

  // 离开页面时主动松开，别让动物一直走
  window.addEventListener('pagehide', () => { if (intent) sendIntent(null); });

  // 触屏控件层（与单机版同一套手感）：摇杆产生意图，折叠/展开后重算画布
  let touchCtl = null;
  function mountTouchControls() {
    if (touchCtl || typeof window.createTouchControls !== 'function') return;
    touchCtl = window.createTouchControls({
      onIntent: (dir) => sendIntent(dir),
      onCollapse: () => fit(),
    });
  }

  // ---------------- 输入 ----------------
  const KEY = { ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
                ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right' };
  window.addEventListener('keydown', (e) => {
    const d = KEY[e.code];
    if (!d) return;
    e.preventDefault();
    sendIntent(d);
  });
  window.addEventListener('keyup', (e) => {
    if (!KEY[e.code]) return;
    e.preventDefault();
    sendIntent(null);
  });


  // ---------------- 相机与渲染（REQ-000018） ----------------
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  /** 纯函数：自己位置 + 画布尺寸 → 相机。实现与验收共用这一份逻辑，
   *  世界边界处相机停住（clamp），视野大于世界时取世界尺寸并在画布内居中。 */
  function cameraTarget(x, y, w, h) {
    const vw = Math.min(w, worldW);
    const vh = Math.min(h, worldH);
    return {
      x: clamp(x - vw / 2, 0, Math.max(0, worldW - vw)),
      y: clamp(y - vh / 2, 0, Math.max(0, worldH - vh)),
      vw, vh,
      ox: Math.floor((w - vw) / 2),
      oy: Math.floor((h - vh) / 2),
    };
  }

  function applyCamera(x, y) {
    Object.assign(camera, cameraTarget(x, y, camera.w, camera.h));
  }

  /** 世界坐标 → 画布坐标（与背景用同一份整数取整，避免「人比地面快一像素」）。 */
  function worldToScreen(x, y) {
    return {
      x: Math.round(x) - Math.round(camera.x) + camera.ox,
      y: Math.round(y) - Math.round(camera.y) + camera.oy,
    };
  }

  function bandPx() {
    return parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--touch-band')
    ) || 0;
  }

  function fit() {
    // 竖屏底部会预留操作带（--touch-band），可用高度要跟着扣掉
    const w = Math.max(VIEW_MIN_PX, Math.floor(innerWidth));
    const h = Math.max(VIEW_MIN_PX, Math.floor(innerHeight - bandPx()));
    // 相机窗口 = 可用视口；位图 1 像素 = CSS 1 像素，放大交给 CSS 的 image-rendering: pixelated
    camera.w = w;
    camera.h = h;
    if (cv.width !== w) cv.width = w;
    if (cv.height !== h) cv.height = h;
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
    applyCamera(renderSelf.x, renderSelf.y);
  }

  // 旋屏、收起/展开控件、工具栏收放都可能改变可用视口：尺寸变了重算相机。
  // 快照已改成全量（REQ-000021），换尺寸不再需要重新握手，也就不会因此断流。
  function refit() {
    const before = { w: camera.w, h: camera.h };
    fit();
    if (camera.w === before.w && camera.h === before.h) return;
  }

  window.addEventListener('resize', refit);
  window.addEventListener('orientationchange', refit);
  setInterval(() => {
    const w = Math.max(VIEW_MIN_PX, Math.floor(innerWidth));
    const h = Math.max(VIEW_MIN_PX, Math.floor(innerHeight - bandPx()));
    if (w !== camera.w || h !== camera.h) refit();
  }, REFIT_POLL_MS);

  // ---------------- 绘制 ----------------
  async function animalImage(id) {
    if (cardOf[id]) return cardOf[id];
    try { cardOf[id] = await loadImage(`/cards/${id}.png`); } catch { cardOf[id] = null; }
    return cardOf[id];
  }

  /** 画一只动物；返回是否真的画上去了（卡片没加载完 / 完全在画面外都是 false）。 */
  function drawAnimal(a, now) {
    const img = cardOf[a.id];
    if (!img) { animalImage(a.id); return false; }
    const row = Math.max(0, CARD_ORDER.indexOf(a.facing));
    const frame = a.moving ? Math.floor(now / (1000 / 8)) % 4 : 0;
    const rp = renderPos(a.id, now) || { x: a.x, y: a.y };   // 插值位置（REQ-000020）
    const p = worldToScreen(rp.x, rp.y);
    const dx = Math.round(p.x - FRAME / 2);
    const dy = Math.round(p.y - FOOT_OFFSET);
    // 完全在画布外的直接跳过（纯绘制优化；可见性由快照决定，快照是全量的）
    if (dx + FRAME < 0 || dx > camera.w || dy + FRAME < 0 || dy > camera.h) return false;
    ctx.drawImage(img, frame * FRAME, row * FRAME, FRAME, FRAME, dx, dy, FRAME, FRAME);
    return true;
  }

  function loop(now) {
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, camera.w, camera.h);
    if (snapshot) {
      const s = snapshot.self;
      renderSelf = renderPos(s.id, now) || { x: s.x, y: s.y };
      applyCamera(renderSelf.x, renderSelf.y);   // 相机跟插值后的自己走，边界处自己停住
      if (bg) ctx.drawImage(bg, Math.round(camera.x), Math.round(camera.y),
        camera.vw, camera.vh, camera.ox, camera.oy, camera.vw, camera.vh);
      drawnIds = [];
      for (const n of snapshot.nearby) if (drawAnimal(n, now)) drawnIds.push(n.id);
      drawAnimal(s, now);
      const rx = Math.round(renderSelf.x);
      const ry = Math.round(renderSelf.y);
      selfHud.textContent = `${s.id} ${s.name} · (${rx}, ${ry}) · ${s.facing}`;
      const n = snapshot.nearby.length;
      nearHud.textContent = n ? `世界里 ${n} 只：${snapshot.nearby[0].name} ${snapshot.nearby[0].distance}px` : '世界里只有你';
      // 被淘汰（stopped）时保留「已在别处被接管」的提示，不要被"重连中"覆盖
      if (!stopped && now - lastSnapAt > STALE_MS) { linkHud.textContent = '重连中…'; linkHud.classList.add('bad'); }
    } else if (bg) {
      ctx.drawImage(bg, Math.round(camera.x), Math.round(camera.y),
        camera.vw, camera.vh, camera.ox, camera.oy, camera.vw, camera.vh);
    }
    requestAnimationFrame(loop);
  }

  // ---------------- 上传（无卡时） ----------------
  const MANIFEST = { frame: 48, cols: 4, rows: 4, rowOrder: CARD_ORDER, footLine: 43, fps: 8 };

  function readFile(f) {
    return new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result);
      fr.onerror = () => rej(new Error('读取文件失败'));
      fr.readAsDataURL(f);
    });
  }

  async function upload(files) {
    dzErr.textContent = '';
    const png = files.find((f) => /\.png$/i.test(f.name) || f.type === 'image/png');
    const json = files.find((f) => /\.json$/i.test(f.name));
    if (!png) { dzErr.textContent = '需要一个 card.png'; return; }
    let manifest = MANIFEST;
    if (json) {
      try { manifest = JSON.parse(await json.text()); }
      catch { dzErr.textContent = 'manifest.json 不是合法 JSON'; return; }
    }
    dzErr.textContent = '上传中…';
    const dataUrl = await readFile(png);
    const body = { pngBase64: String(dataUrl), manifest };
    const id = animalId || 'me';
    const r = await api(`/api/v1/animals/${id}/card`, { method: 'POST', body });
    const out = await r.json().catch(() => ({}));
    if (!r.ok) {
      dzErr.textContent = '上传被拒绝：\n' + ((out.errors || [out.message || r.status]).join('\n'));
      return;
    }
    cardOf = {};
    await startGame();
    if (ws && ws.readyState === 1) sendIntent(intent);
  }

  dzBox.addEventListener('dragover', (e) => { e.preventDefault(); dzBox.classList.add('over'); });
  dzBox.addEventListener('dragleave', () => dzBox.classList.remove('over'));
  dzBox.addEventListener('drop', (e) => {
    e.preventDefault();
    dzBox.classList.remove('over');
    upload(Array.from(e.dataTransfer.files || []));
  });
  document.getElementById('dz-pick').addEventListener('click', () => dzFile.click());
  dzFile.addEventListener('change', () => upload(Array.from(dzFile.files || [])));

  window.__play = {
    get snapshot() { return snapshot; },
    get animalId() { return animalId; },
    get connected() { return !!ws && ws.readyState === 1; },
    get dropzoneVisible() { return dz.classList.contains('show'); },
    sendIntent,
    // 相机探针（AC-000070…073 / 000085）：绘制用的同一个 camera 对象 + 纯函数
    get camera() {
      return {
        x: camera.x, y: camera.y, w: camera.w, h: camera.h,
        vw: camera.vw, vh: camera.vh, ox: camera.ox, oy: camera.oy,
        worldW, worldH,
        drawnIds: drawnIds.slice(),
        // 插值诊断（AC-000080…083）
        renderSelf: { x: renderSelf.x, y: renderSelf.y },
        snapInterval,
        interpSize: interp.size,
        // 连接诊断（AC-000076…079）
        lastSnapAgeMs: Math.round(performance.now() - lastSnapAt),
        reconnectCount,
        stopped,
      };
    },
    worldToScreen,
    cameraTarget,               // 纯函数：四向边界与「视野大于世界」的单元断言
    renderPos,                  // 当前帧的插值位置（逐帧采样用）
    // 测试钩子：主动断开 WebSocket，用来验证自动重连（AC-000044）
    _drop() { if (ws) ws.close(); },
    // 测试钩子：模拟半开连接——不派发 close，也不再有任何数据（AC-000078）
    _halfOpen() {
      if (!ws) return false;
      try { ws.onmessage = null; ws.onclose = null; ws.onerror = null; } catch { /* ignore */ }
      return true;
    },
    // 测试钩子：把连接标记成死状态但不触发 close（模拟 iOS 挂起）
    _killSilently() {
      if (!ws) return false;
      try { ws.onmessage = null; ws.onclose = null; } catch { /* ignore */ }
      lastSnapAt = performance.now() - STALE_MS - 500;
      return true;
    },
    get touch() { return touchCtl; },
    _uploadForTest: (b64) => upload([new File([Uint8Array.from(atob(b64.split(',')[1] || b64), (c) => c.charCodeAt(0))], 'card.png', { type: 'image/png' })]),
  };

  boot().catch((e) => fail('启动失败：' + e.message));
})();
