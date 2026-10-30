'use strict';
/* 背景音乐端到端验收（REQ-000022 / AC-000087…092，另回归单机版 AC-000045/046）
 *
 * 服务端：/music/ 音频按 Range 供给（200 全量 / 206 单区间 / 416 越界）
 * 页面（390x844 触屏 + 844x390 横屏）：
 *   AC-000088 手势后开始播放（loop/音量/currentTime）
 *   AC-000089 静音开关 + 刷新后仍静音
 *   AC-000090 按钮与所有既有控件零重叠、在视口内
 *   AC-000091 音频失败只隐藏按钮，游戏不受影响
 *   AC-000092 切后台暂停、回前台继续
 * 单机版（file://）：AC-000045 四向移动与尺寸切换、AC-000046 无 http(s) 资源请求
 *
 * 注意：真实的"用户手势"必须用 CDP Input.dispatchMouseEvent（受信任事件），
 * 页面内 dispatchEvent 拿不到用户激活，play() 会被自动播放策略拒绝。
 *
 * 用法：node tools/e2e_bgm.js        （在 cloud/ 下；CDP_PORT 默认 9222）
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8950 + Math.floor(Math.random() * 40);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'bgm-e2e-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-bgm-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'bgm.json');
const REPO = path.join(__dirname, '..', '..');
const WAV_REL = '/music/seaside_lazy_loop_40s.wav';
const WAV_LOCAL = path.join(REPO, 'music', 'seaside_lazy_loop_40s.wav');
const SINGLE_FILE_URL = 'file:///' + path.join(REPO, 'index.html').replace(/\\/g, '/');

const VOLUME_WANT = 0.42;       // 与 cloud/play/bgm.js 的 BGM_VOLUME 一致
const VOLUME_TOL = 0.01;
const PLAY_WAIT_MS = 900;       // 手势后等待（含 320ms 淡入）
const TAP_OFFSETS = [[195, 300], [220, 420]];   // 画布内的安全点击点（避开 HUD 与控件）

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const map = [];
function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
  map.push({ condition_id: condId, assertion: name, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} [${condId}] ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

// ---------- PNG（造卡片） ----------
const CRC = (() => { const t = new Int32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c; } return t; })();
const crc32 = (b) => { let c = -1; for (const x of b) c = CRC[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ -1) >>> 0; };
const chunk = (type, data) => {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
};
function cardPng() {
  const w = 192, h = 192;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = y * (w * 4 + 1) + 1 + x * 4;
      const body = (x % 48) > 10 && (x % 48) < 38 && (y % 48) > 10 && (y % 48) < 38;
      raw[o + 3] = body ? 255 : 0;
      if (body) { raw[o] = 200; raw[o + 1] = 90; raw[o + 2] = 60; }
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

// ---------- CDP ----------
async function cdpVersion() { return (await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`)).json(); }
function wsConnect(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, { perMessageDeflate: false, maxPayload: 64 * 1024 * 1024 });
    ws.on('open', () => resolve(ws));
    ws.on('error', reject);
    setTimeout(() => reject(new Error('CDP 连接超时：' + url)), 5000);
  });
}
function rpc(ws) {
  let id = 0;
  const pending = new Map();
  ws.on('message', (raw) => {
    let msg; try { msg = JSON.parse(raw.toString()); } catch { return; }
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    }
  });
  return (method, params = {}) => new Promise((resolve, reject) => {
    const mid = ++id;
    pending.set(mid, { resolve, reject });
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
}

async function openTarget(browserRpc) {
  const { targetId } = await browserRpc('Target.createTarget', { url: 'about:blank' });
  await sleep(300);
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const t = list.find((x) => x.id === targetId);
  if (!t) throw new Error('找不到新建的 target');
  return { targetId, wsUrl: t.webSocketDebuggerUrl };
}

async function evaluate(call, fn, arg) {
  const res = await call('Runtime.evaluate', {
    expression: `(${fn.toString()})(${JSON.stringify(arg === undefined ? null : arg)})`,
    awaitPromise: true, returnByValue: true,
  });
  if (res.exceptionDetails) throw new Error('页面求值异常：' + JSON.stringify(res.exceptionDetails).slice(0, 300));
  return res.result.value;
}

/** 受信任点击（只有它才能解锁自动播放） */
async function trustedClick(call, x, y) {
  await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' });
  await call('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}

// ---------- 页面内取数 ----------
const PAGE_STATE = function () {
  const p = window.__play;
  const b = p && p.bgm;
  const rect = (sel) => {
    const e = document.querySelector(sel);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right),
             b: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height),
             display: cs.display };
  };
  return {
    viewport: [innerWidth, innerHeight],
    ready: !!(p && p.snapshot),
    connected: p ? p.connected : false,
    snapAge: p ? Math.round(p.camera.lastSnapAgeMs) : null,
    bgm: b ? b.state() : null,
    stored: (() => { try { return localStorage.getItem('crab-coast:bgm-muted'); } catch { return null; } })(),
    rects: {
      btn: rect('#bgm-btn'), self: rect('#self-hud'), near: rect('#near-hud'), link: rect('#link-hud'),
      stick: rect('#stick-base'), abxy: rect('#abxy'), toggle: rect('#touch-toggle'),
    },
  };
};

const PAGE_SET_VISIBILITY = function (state) {
  const key = state === 'hidden' ? 'hidden' : 'visible';
  try {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => key });
  } catch { return { ok: false }; }
  document.dispatchEvent(new Event('visibilitychange'));
  return { ok: true, visibilityState: document.visibilityState };
};

const PAGE_SIMULATE_ERROR = async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const p = window.__play;
  const b = p && p.bgm;
  if (!b) return { ok: false };
  b.audio.src = '/music/__does_not_exist__.wav';
  b.audio.load();
  await sleep(600);
  const btn = document.getElementById('bgm-btn');
  const cv = document.getElementById('world');
  const frames = [];
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => requestAnimationFrame(r));
    frames.push(cv.toDataURL());
  }
  return {
    ok: true,
    btnDisplay: btn ? getComputedStyle(btn).display : null,
    failed: b.failed,
    connected: p.connected,
    snapAge: Math.round(p.camera.lastSnapAgeMs),
    framesIdentical: frames.every((f) => f === frames[0]),
  };
};

const PAGE_SINGLE = function () {
  return {
    hasCrab: !!window.__crab,
    hasProbe: !!window.__probe,
    crab: window.__crab || null,
    httpResources: (performance.getEntriesByType('resource') || [])
      .map((e) => e.name).filter((n) => /^https?:/i.test(n)),
  };
};

async function waitPageReady(call, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const st = await evaluate(call, PAGE_STATE);
    if (st.ready) return st;
    await sleep(150);
  }
  return evaluate(call, PAGE_STATE);
}

function overlaps(a, b) {
  if (!a || !b || a.display === 'none' || b.display === 'none') return false;
  return !(a.r <= b.l || b.r <= a.l || a.b <= b.t || b.b <= a.t);
}

async function main() {
  const wavSize = fs.statSync(WAV_LOCAL).size;

  // ================= 服务端 Range（AC-000087） =================
  let child;
  try {
    let version;
    try { version = await cdpVersion(); } catch {
      console.error(`无法连接 CDP ${CDP_PORT}：请先启动带 --remote-debugging-port=${CDP_PORT} 的 Edge/Chrome 再重跑。`);
      process.exit(3);
    }
    const bws = await wsConnect(version.webSocketDebuggerUrl);
    const browserRpc = rpc(bws);

    child = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
      env: { ...process.env, PORT: String(PORT), DATA_DIR, REGISTER_CODE: CODE },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const childOut = [];
    child.stdout.on('data', (d) => childOut.push(d.toString()));
    child.stderr.on('data', (d) => childOut.push(d.toString()));
    let up = false;
    for (let i = 0; i < 80 && !up; i++) { await sleep(150); try { up = (await fetch(BASE + '/healthz')).ok; } catch { /* wait */ } }
    if (!up) { console.error('服务没起来\n' + childOut.join('')); process.exit(1); }

    // --- 200 全量 ---
    const full = await fetch(BASE + WAV_REL);
    const fullBuf = Buffer.from(await full.arrayBuffer());
    const fullH = Object.fromEntries(full.headers.entries());
    check('AC-000087', '音频可整文件取回：200 + audio/wav + accept-ranges + content-length 等于文件大小',
      full.status === 200 && fullH['content-type'] === 'audio/wav'
      && fullH['accept-ranges'] === 'bytes' && Number(fullH['content-length']) === wavSize
      && fullBuf.length === wavSize,
      { status: full.status, type: fullH['content-type'], acceptRanges: fullH['accept-ranges'],
        contentLength: Number(fullH['content-length']), wavSize, bytes: fullBuf.length });

    // --- 206 单区间 ---
    const part = await fetch(BASE + WAV_REL, { headers: { Range: 'bytes=0-1023' } });
    const partBuf = Buffer.from(await part.arrayBuffer());
    const partH = Object.fromEntries(part.headers.entries());
    check('AC-000087', 'Range bytes=0-1023 → 206 + content-range 正确 + 正文 1024 字节',
      part.status === 206 && partH['content-range'] === `bytes 0-1023/${wavSize}`
      && partBuf.length === 1024 && partH['accept-ranges'] === 'bytes',
      { status: part.status, contentRange: partH['content-range'], bytes: partBuf.length });

    // --- 416 越界 ---
    const bad = await fetch(BASE + WAV_REL, { headers: { Range: 'bytes=99999999-' } });
    const badH = Object.fromEntries(bad.headers.entries());
    check('AC-000087', 'Range bytes=99999999- → 416 + content-range: bytes */大小',
      bad.status === 416 && badH['content-range'] === `bytes */${wavSize}`,
      { status: bad.status, contentRange: badH['content-range'] });

    // ================= 页面（AC-000088…092） =================
    const reg = await (await fetch(BASE + '/api/v1/register', {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-register-code': CODE },
      body: JSON.stringify({ name: 'BgmProbe' }),
    })).json();
    const upCard = await fetch(`${BASE}/api/v1/animals/${reg.animalId}/card`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${reg.token}` },
      body: JSON.stringify({ pngBase64: cardPng().toString('base64'),
        manifest: { frame: 48, cols: 4, rows: 4, rowOrder: C.CARD.rowOrder, footLine: 43, fps: 8 } }),
    });
    if (!upCard.ok) throw new Error('上传卡片失败：' + (await upCard.text()));
    const playUrl = `${BASE}/play?t=${encodeURIComponent(reg.token)}`;

    let { targetId, wsUrl } = await openTarget(browserRpc);
    let pws = await wsConnect(wsUrl);
    let call = rpc(pws);
    await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await call('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
    await call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
    await call('Page.navigate', { url: playUrl });
    try { await call('Page.bringToFront'); } catch { /* 可选 */ }
    let st = await waitPageReady(call);
    await sleep(600);

    // --- AC-000090 布局（竖屏） ---
    const portraitRects = st.rects;
    const pairs = [['btn', 'self'], ['btn', 'near'], ['btn', 'link'], ['btn', 'stick'], ['btn', 'abxy'], ['btn', 'toggle']];
    const overlapPortrait = pairs.filter(([a, b]) => overlaps(portraitRects[a], portraitRects[b])).map(([a, b]) => `${a}×${b}`);
    const insidePortrait = !!portraitRects.btn && portraitRects.btn.l >= 0 && portraitRects.btn.t >= 0
      && portraitRects.btn.r <= st.viewport[0] && portraitRects.btn.b <= st.viewport[1];

    // --- AC-000088 手势后播放 ---
    await trustedClick(call, TAP_OFFSETS[0][0], TAP_OFFSETS[0][1]);
    await sleep(PLAY_WAIT_MS);
    st = await evaluate(call, PAGE_STATE);
    const b = st.bgm || {};
    check('AC-000088', '手势后 900ms 内开始播放：started / paused=false / currentTime>0 / loop / 音量 0.42',
      b.started === true && b.playing === true && b.currentTime > 0 && b.loop === true
      && Math.abs(b.volume - VOLUME_WANT) <= VOLUME_TOL && b.readyState >= 2,
      { bgm: b, want: { volume: VOLUME_WANT } });

    // --- AC-000092 切后台暂停 / 回前台继续 ---
    const hidden = await evaluate(call, PAGE_SET_VISIBILITY, 'hidden');
    await sleep(350);
    const stHidden = await evaluate(call, PAGE_STATE);
    const tBefore = (stHidden.bgm || {}).currentTime || 0;
    const visible = await evaluate(call, PAGE_SET_VISIBILITY, 'visible');
    await sleep(1000);
    const stVisible = await evaluate(call, PAGE_STATE);
    check('AC-000092', 'hidden 时暂停；visible 后 1 秒内继续播放且 currentTime 增长',
      hidden.ok === true && (stHidden.bgm || {}).playing === false
      && (stVisible.bgm || {}).playing === true && (stVisible.bgm || {}).currentTime > tBefore,
      { hidden: { playing: (stHidden.bgm || {}).playing, t: tBefore },
        visible: { playing: (stVisible.bgm || {}).playing, t: (stVisible.bgm || {}).currentTime },
        visibleState: visible.visibilityState });

    // --- AC-000089 静音 + 刷新后保持 ---
    const btnRect = st.rects.btn;
    await trustedClick(call, btnRect.l + Math.round(btnRect.w / 2), btnRect.t + Math.round(btnRect.h / 2));
    await sleep(400);
    const stMuted = await evaluate(call, PAGE_STATE);
    await call('Page.reload', { ignoreCache: false });
    await sleep(2600);
    const stReload = await waitPageReady(call);
    await sleep(400);
    // 刷新后先派发一次手势（真机上用户总会点一下）：仍应保持静音、不出声
    await trustedClick(call, TAP_OFFSETS[1][0], TAP_OFFSETS[1][1]);
    await sleep(600);
    const stReloadAfterTap = await evaluate(call, PAGE_STATE);
    const btnRect2 = stReloadAfterTap.rects.btn;
    await trustedClick(call, btnRect2.l + Math.round(btnRect2.w / 2), btnRect2.t + Math.round(btnRect2.h / 2));
    await sleep(PLAY_WAIT_MS);
    const stUnmuted = await evaluate(call, PAGE_STATE);
    check('AC-000089', '点按钮静音（paused + localStorage）；刷新后仍静音不出声；再点恢复播放',
      (stMuted.bgm || {}).muted === true && (stMuted.bgm || {}).playing === false && stMuted.stored === '1'
      && (stReloadAfterTap.bgm || {}).muted === true && (stReloadAfterTap.bgm || {}).playing === false
      && (stUnmuted.bgm || {}).muted === false && (stUnmuted.bgm || {}).playing === true,
      { afterClick: { muted: (stMuted.bgm || {}).muted, playing: (stMuted.bgm || {}).playing, stored: stMuted.stored },
        afterReload: { muted: (stReload.bgm || {}).muted, stored: stReload.stored },
        afterReloadTap: { muted: (stReloadAfterTap.bgm || {}).muted, playing: (stReloadAfterTap.bgm || {}).playing },
        afterUnmute: { muted: (stUnmuted.bgm || {}).muted, playing: (stUnmuted.bgm || {}).playing } });

    // --- AC-000090 布局总判定（竖屏 + 横屏） ---
    await call('Emulation.setDeviceMetricsOverride', { width: 844, height: 390, deviceScaleFactor: 1, mobile: true });
    await sleep(700);
    const land = await evaluate(call, PAGE_STATE);
    const overlapLand = pairs.filter(([a, b]) => overlaps(land.rects[a], land.rects[b])).map(([a, b]) => `${a}×${b}`);
    const insideLand = !!land.rects.btn && land.rects.btn.l >= 0 && land.rects.btn.t >= 0
      && land.rects.btn.r <= land.viewport[0] && land.rects.btn.b <= land.viewport[1];
    check('AC-000090', '竖屏与横屏：音乐按钮都在视口内，且与三个 HUD / 摇杆 / ABXY / 收起开关零重叠',
      insidePortrait && insideLand && overlapPortrait.length === 0 && overlapLand.length === 0,
      { portrait: { viewport: st.viewport, btn: portraitRects.btn, overlaps: overlapPortrait, inside: insidePortrait },
        landscape: { viewport: land.viewport, btn: land.rects.btn, overlaps: overlapLand, inside: insideLand } });

    // --- AC-000091 音频失败只隐藏按钮 ---
    const err = await evaluate(call, PAGE_SIMULATE_ERROR);
    check('AC-000091', '音频加载失败：按钮隐藏，connected 仍为 true、快照新鲜、连续 5 帧画面一致',
      err.ok === true && err.btnDisplay === 'none' && err.failed === true
      && err.connected === true && err.snapAge < 500 && err.framesIdentical === true,
      err);

    pws.close();
    await browserRpc('Target.closeTarget', { targetId });

    // ================= 单机版回归（AC-000045 / AC-000046） =================
    ({ targetId, wsUrl } = await openTarget(browserRpc));
    pws = await wsConnect(wsUrl);
    call = rpc(pws);
    await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 900, height: 560, deviceScaleFactor: 1, mobile: false });
    await call('Emulation.setTouchEmulationEnabled', { enabled: false });
    await call('Page.navigate', { url: SINGLE_FILE_URL });
    try { await call('Page.bringToFront'); } catch { /* 可选 */ }
    await sleep(2500);
    const single0 = await evaluate(call, PAGE_SINGLE);
    const moved = await evaluate(call, async () => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const before = { x: window.__crab.x, size: window.__crab.size };
      window.__probe.press('ArrowRight');
      await sleep(500);
      window.__probe.release('ArrowRight');
      await sleep(120);
      const afterMove = { x: window.__crab.x, size: window.__crab.size };
      for (let i = 0; i < 3; i++) { window.__probe.press('KeyT'); await sleep(80); window.__probe.release('KeyT'); await sleep(160); }
      const afterSizes = { size: window.__crab.size };
      return { before, afterMove, afterSizes };
    });
    const single1 = await evaluate(call, PAGE_SINGLE);
    check('AC-000045', 'file:// 单机版：方向键使角色移动、T 键切换尺寸仍然正常',
      single0.hasCrab === true && single0.hasProbe === true
      && moved.afterMove.x > moved.before.x
      && moved.afterSizes.size !== moved.afterMove.size,
      { start: single0.crab && { x: single0.crab.x, size: single0.crab.size }, moved, end: single1.crab });
    check('AC-000046', 'file:// 单机版页面没有任何 http(s) 资源请求',
      single1.httpResources.length === 0,
      { httpResources: single1.httpResources });

    pws.close();
    await browserRpc('Target.closeTarget', { targetId });

    fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
    fs.writeFileSync(EVIDENCE, JSON.stringify({
      when: new Date().toISOString(), cdpPort: CDP_PORT, port: PORT,
      wav: { path: WAV_REL, size: wavSize },
      total: results.length, failed: results.filter((r) => !r.pass).length,
      results, mapping: map,
    }, null, 2), 'utf8');
    const failed = results.filter((r) => !r.pass);
    console.log(`${results.length - failed.length}/${results.length} 通过 → evidence/bgm.json`);
    if (failed.length) process.exitCode = 1;
    try { bws.close(); } catch { /* ignore */ }
  } catch (e) {
    console.error('探针异常：' + (e && e.stack || e));
    process.exitCode = 1;
  } finally {
    try { if (child) child.kill(); } catch { /* ignore */ }
    await sleep(150);
    try { fs.rmSync(DATA_DIR, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main();
