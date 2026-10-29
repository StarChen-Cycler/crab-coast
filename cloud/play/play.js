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
    bg = await loadImage('/assets/bg_base.png');
    fit();
    mountTouchControls();
    connect();
    requestAnimationFrame(loop);
  }

  function loadImage(src) {
    return new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => res(img);
      img.onerror = () => rej(new Error('图片加载失败：' + src));
      img.src = src;
    });
  }

  // ---------------- WebSocket ----------------
  function connect() {
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?t=${encodeURIComponent(token)}`);
    ws.onopen = () => {
      retry = 0;
      linkHud.textContent = '已连接';
      linkHud.classList.remove('bad');
      if (intent) sendIntent(intent);
    };
    ws.onmessage = (m) => {
      let msg;
      try { msg = JSON.parse(m.data); } catch { return; }
      if (msg.type === 'snapshot') { snapshot = msg; lastSnapAt = performance.now(); }
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
      linkHud.textContent = '重连中…';
      linkHud.classList.add('bad');
      retry = Math.min(retry + 1, 6);
      setTimeout(connect, Math.min(500 * 2 ** (retry - 1), 8000));
    };
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
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


  // ---------------- 渲染 ----------------
  function fit() {
    // 竖屏底部会预留操作带（--touch-band），可用高度要跟着扣掉
    const band = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--touch-band')
    ) || 0;
    const w = innerWidth;
    const h = Math.max(120, innerHeight - band);
    const s = Math.min(w * 0.98 / 960, h * 0.96 / 540);
    cv.style.width = Math.round(960 * s) + 'px';
    cv.style.height = Math.round(540 * s) + 'px';
  }
  window.addEventListener('resize', fit);

  async function animalImage(id) {
    if (cardOf[id]) return cardOf[id];
    try { cardOf[id] = await loadImage(`/cards/${id}.png`); } catch { cardOf[id] = null; }
    return cardOf[id];
  }

  function drawAnimal(a, now) {
    const img = cardOf[a.id];
    if (!img) { animalImage(a.id); return; }
    const row = Math.max(0, CARD_ORDER.indexOf(a.facing));
    const frame = a.moving ? Math.floor(now / (1000 / 8)) % 4 : 0;
    ctx.drawImage(img, frame * FRAME, row * FRAME, FRAME, FRAME,
      Math.round(a.x - FRAME / 2), Math.round(a.y - 43), FRAME, FRAME);
  }

  function loop(now) {
    ctx.imageSmoothingEnabled = false;
    if (bg) ctx.drawImage(bg, 0, 0, 960, 540);
    if (snapshot) {
      for (const n of snapshot.nearby) drawAnimal(n, now);
      drawAnimal(snapshot.self, now);
      const s = snapshot.self;
      selfHud.textContent = `${s.id} ${s.name} · (${s.x}, ${s.y}) · ${s.facing}`;
      const n = snapshot.nearby.length;
      nearHud.textContent = n ? `附近 ${n} 只：${snapshot.nearby[0].name} ${snapshot.nearby[0].distance}px` : '附近：无';
      // 被淘汰（stopped）时保留「已在别处被接管」的提示，不要被"快照中断"覆盖
      if (!stopped && now - lastSnapAt > 3000) { linkHud.textContent = '快照中断'; linkHud.classList.add('bad'); }
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
    // 测试钩子：主动断开 WebSocket，用来验证自动重连（AC-000044）
    _drop() { if (ws) ws.close(); },
    get touch() { return touchCtl; },
    _uploadForTest: (b64) => upload([new File([Uint8Array.from(atob(b64.split(',')[1] || b64), (c) => c.charCodeAt(0))], 'card.png', { type: 'image/png' })]),
  };

  boot().catch((e) => fail('启动失败：' + e.message));
})();
