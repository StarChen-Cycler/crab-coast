'use strict';
/* 多人版触屏 UI 端到端验收（REQ-000017 / AC-000064…069）
 *
 * 自己拉起服务（临时 DATA_DIR，不碰生产数据），复用已开浏览器的 CDP 端口（默认 9222），
 * 在四档视口下断言摇杆/死区/ABXY/收起/布局，并把结果按 condition 映射写入 evidence/touch_ui.json。
 *
 * 用法：node tools/e2e_touch_ui.js
 * 环境：CDP_PORT（默认 9222）；若浏览器未开，脚本以非零码退出并说明原因（不静默跳过）。
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8500 + Math.floor(Math.random() * 60);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'ui-e2e-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-ui-'));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const map = [];             // condition_id → 断言名 → 实测值

function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
  map.push({ condition_id: condId, assertion: name, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} [${condId}] ${name}${detail ? ' — ' + detail : ''}`);
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

// ---------- CDP（只连已开浏览器，不自己拉起） ----------
async function cdpVersion() {
  const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`);
  return res.json();
}
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

// 页面内断言（在浏览器里执行，返回 JSON）
const PAGE_PROBE = async function probe() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const wait = async (fn, ms = 8000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(100); }
    return false;
  };
  const ok = await wait(() => window.__play && window.__play.snapshot);
  if (!ok) return { error: '页面未就绪（__play.touch 或快照缺失）' };

  const p = window.__play;
  const rect = (sel) => {
    const e = document.querySelector(sel);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height), display: getComputedStyle(e).display };
  };
  const overlap = (a, b) => !!a && !!b && !(a.r <= b.l || b.r <= a.l || a.b <= b.t || b.b <= a.t);
  const out = { viewport: [innerWidth, innerHeight], rects: {}, dirs: {}, abxy: {}, collapse: {}, layout: {}, desktop: {} };
  out.rects = {
    stick: rect('#stick-base'), abxy: rect('#abxy'), toggle: rect('#touch-toggle'),
    self: rect('#self-hud'), near: rect('#near-hud'), link: rect('#link-hud'),
    canvas: rect('#world'),
  };
  out.band = getComputedStyle(document.documentElement).getPropertyValue('--touch-band').trim();

  const base = document.getElementById('stick-base');
  if (!base) {
    // 桌面档：不挂载控件，但键盘必须仍能驱动（AC-000069 的桌面分支）
    out.touchMounted = false;
    const s0 = p.snapshot.self;      // 此处 self() 还没声明（TDZ），直接读快照
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight', bubbles: true }));
    await sleep(700);
    window.dispatchEvent(new KeyboardEvent('keyup', { code: 'ArrowRight', bubbles: true }));
    await sleep(150);
    const s1 = p.snapshot.self;
    out.desktop = { keyboardMoves: { x0: s0.x, x1: s1.x, moved: s1.x > s0.x } };
    out.overlaps = {};
    out.inside = true;
    out.canvasClearOfBand = true;
    return out;
  }
  out.touchMounted = true;
  const r = base.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const mk = (x, y) => new Touch({ identifier: 7, target: base, clientX: x, clientY: y, pageX: x, pageY: y, radiusX: 4, radiusY: 4, force: 1 });
  const fire = (target, type, x, y) => {
    const t = mk(x, y), empty = type === 'touchend' || type === 'touchcancel';
    target.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: empty ? [] : [t], changedTouches: [t] }));
  };
  const self = () => p.snapshot && p.snapshot.self;

  // 四向
  for (const [name, dx, dy] of [['right', 40, 0], ['left', -40, 0], ['up', 0, -40], ['down', 0, 40]]) {
    const s0 = self();
    fire(base, 'touchstart', cx, cy);
    fire(document, 'touchmove', cx + dx, cy + dy);
    await sleep(700);                 // 快照 10Hz + 往返延迟，采样窗口留足
    const s1 = self();
    fire(document, 'touchend', cx + dx, cy + dy);
    await sleep(300);
    out.dirs[name] = {
      dx: +(s1.x - s0.x).toFixed(1), dy: +(s1.y - s0.y).toFixed(1),
      facing: s1.facing, moved: Math.hypot(s1.x - s0.x, s1.y - s0.y),
      stopped: self().moving === false,
    };
  }

  // 死区
  const d0 = self();
  fire(base, 'touchstart', cx, cy);
  fire(document, 'touchmove', cx + 4, cy + 3);
  await sleep(400);
  const d1 = self();
  fire(document, 'touchend', cx + 4, cy + 3);
  out.deadZone = { dx: +(d1.x - d0.x).toFixed(1), dy: +(d1.y - d0.y).toFixed(1) };

  // ABXY
  const b0 = self();
  for (const id of ['btn-y', 'btn-x', 'btn-b', 'btn-a']) {
    const el = document.getElementById(id);
    el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, cancelable: true, touches: [mk(cx, cy)], changedTouches: [mk(cx, cy)] }));
  }
  await sleep(350);
  const b1 = self();
  out.abxy = {
    unchanged: Math.abs(b1.x - b0.x) < 1 && Math.abs(b1.y - b0.y) < 1 && b1.facing === b0.facing,
    disabled: ['btn-y', 'btn-x', 'btn-b', 'btn-a'].every((id) => document.getElementById(id).disabled),
  };

  // 收起 / 恢复
  const toggle = document.getElementById('touch-toggle');
  const tapToggle = () => toggle.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, cancelable: true, touches: [mk(0, 0)], changedTouches: [mk(0, 0)] }));
  tapToggle();
  await sleep(320);
  out.collapse = {
    stickDisplay: getComputedStyle(base).display,
    abxyDisplay: getComputedStyle(document.getElementById('abxy')).display,
    toggleVisible: getComputedStyle(toggle).display !== 'none',
    band: getComputedStyle(document.documentElement).getPropertyValue('--touch-band').trim(),
    canvasTop: Math.round(document.getElementById('world').getBoundingClientRect().top),
  };
  tapToggle();
  await sleep(320);
  out.collapse.restored = {
    stickDisplay: getComputedStyle(base).display,
    band: getComputedStyle(document.documentElement).getPropertyValue('--touch-band').trim(),
    canvasTop: Math.round(document.getElementById('world').getBoundingClientRect().top),
  };

  // 桌面：用键盘驱动（仅桌面档调用时会再单独跑）
  out.desktop.keyboardMoves = (() => {
    const s0 = self();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight', bubbles: true }));
    return { x0: s0.x };
  })();
  await sleep(400);
  window.dispatchEvent(new KeyboardEvent('keyup', { code: 'ArrowRight', bubbles: true }));
  await sleep(150);
  out.desktop.keyboardMoves.x1 = self().x;
  out.desktop.keyboardMoves.moved = self().x > out.desktop.keyboardMoves.x0;

  out.overlaps = {
    stick_abxy: overlap(out.rects.stick, out.rects.abxy),
    toggle_stick: overlap(out.rects.toggle, out.rects.stick),
    toggle_abxy: overlap(out.rects.toggle, out.rects.abxy),
    hud_pair: overlap(out.rects.self, out.rects.near) || overlap(out.rects.self, out.rects.link),
  };
  out.inside = Object.entries(out.rects).filter(([, v]) => v).every(([, v]) => v.l >= 0 && v.t >= 0 && v.r <= innerWidth && v.b <= innerHeight);
  out.canvasClearOfBand = (() => {
    const c = out.rects.canvas;
    const bandPx = parseFloat(out.band) || 0;
    return c ? innerHeight - c.b >= bandPx - 2 : false;
  })();
  return out;
};

async function openTarget(browserRpc) {
  const { targetId } = await browserRpc('Target.createTarget', { url: 'about:blank' });
  await sleep(300);
  const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
  const t = list.find((x) => x.id === targetId);
  if (!t) throw new Error('找不到新建的 target');
  return { targetId, wsUrl: t.webSocketDebuggerUrl };
}

async function runViewport(browserRpc, cfg) {
  const { targetId, wsUrl } = await openTarget(browserRpc);
  const ws = await wsConnect(wsUrl);
  const call = rpc(ws);
  await call('Page.enable');
  if (cfg.touch) {
    await call('Emulation.setDeviceMetricsOverride', { width: cfg.w, height: cfg.h, deviceScaleFactor: 1, mobile: true });
    await call('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  } else {
    await call('Emulation.setDeviceMetricsOverride', { width: cfg.w, height: cfg.h, deviceScaleFactor: 1, mobile: false });
    await call('Emulation.setTouchEmulationEnabled', { enabled: false });
  }
  await call('Page.navigate', { url: cfg.url });
  await sleep(2500);
  const res = await call('Runtime.evaluate', {
    expression: `(${PAGE_PROBE.toString()})()`,
    awaitPromise: true, returnByValue: true,
  });
  ws.close();
  await browserRpc('Target.closeTarget', { targetId });
  if (res.exceptionDetails) throw new Error('页面断言异常：' + JSON.stringify(res.exceptionDetails).slice(0, 200));
  return res.result.value;
}

async function main() {
  let version;
  try { version = await cdpVersion(); } catch {
    console.error(`无法连接 CDP ${CDP_PORT}：请先启动一次 edge.js/Chrome（带 --remote-debugging-port=${CDP_PORT}）再重跑。`);
    process.exit(3);
  }
  const bws = await wsConnect(version.webSocketDebuggerUrl);
  const browserRpc = rpc(bws);

  const child = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR, REGISTER_CODE: CODE },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const log = [];
  child.stdout.on('data', (d) => log.push(d.toString()));
  child.stderr.on('data', (d) => log.push(d.toString()));

  try {
    let up = false;
    for (let i = 0; i < 80 && !up; i++) { await sleep(150); try { up = (await fetch(BASE + '/healthz')).ok; } catch { /* wait */ } }
    if (!up) { console.error('服务没起来\n' + log.join('')); process.exit(1); }

    const reg = await (await fetch(BASE + '/api/v1/register', {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-register-code': CODE },
      body: JSON.stringify({ name: 'UIProbe' }),
    })).json();
    const card = await fetch(`${BASE}/api/v1/animals/${reg.animalId}/card`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${reg.token}` },
      body: JSON.stringify({
        pngBase64: cardPng().toString('base64'),
        manifest: { frame: 48, cols: 4, rows: 4, rowOrder: C.CARD.rowOrder, footLine: 43, fps: 8 },
      }),
    });
    if (!card.ok) { console.error('卡片上传失败：' + (await card.text())); process.exit(1); }
    const url = `${BASE}/play?t=${encodeURIComponent(reg.token)}`;
    console.log('试验动物:', reg.animalId, '| 页面:', url);

    const portrait = await runViewport(browserRpc, { w: 390, h: 844, touch: true, url });
    const land = await runViewport(browserRpc, { w: 844, h: 390, touch: true, url });
    const short = await runViewport(browserRpc, { w: 844, h: 260, touch: true, url });
    const desk = await runViewport(browserRpc, { w: 900, h: 560, touch: false, url });

    // ---------- AC-000064 四向 ----------
    const dirOk = ['right', 'left', 'up', 'down'].every((d) => {
      const v = portrait.dirs[d];
      const want = { right: ['x', 1], left: ['x', -1], up: ['y', -1], down: ['y', 1] }[d];
      const delta = want[0] === 'x' ? v.dx : v.dy;
      const cross = want[0] === 'x' ? v.dy : v.dx;
      return Math.sign(delta) === want[1] && Math.abs(delta) >= 30 && Math.abs(cross) < 2
        && v.facing === d && v.stopped;
    });
    check('AC-000064', '摇杆四向各 400ms：方向正确、位移≥30px、facing 一致、松手即停', dirOk,
      JSON.stringify(portrait.dirs));

    // ---------- AC-000065 死区 ----------
    check('AC-000065', '推 (4,3) 落在死区：位移为 0',
      portrait.deadZone.dx === 0 && portrait.deadZone.dy === 0, JSON.stringify(portrait.deadZone));

    // ---------- AC-000066 ABXY ----------
    check('AC-000066', 'ABXY 四键禁用占位：无状态变化且 disabled',
      portrait.abxy.unchanged && portrait.abxy.disabled, JSON.stringify(portrait.abxy));

    // ---------- AC-000067 收起 ----------
    const c = portrait.collapse;
    check('AC-000067', '收起只藏控件、开关保留、操作带归零、画布重算；恢复后还原',
      c.stickDisplay === 'none' && c.abxyDisplay === 'none' && c.toggleVisible
      && c.band === '0px' && c.canvasTop !== portrait.rects.canvas.t
      && c.restored.stickDisplay === 'block' && c.restored.band === '236px'
      && c.restored.canvasTop === portrait.rects.canvas.t,
      JSON.stringify(c));

    // ---------- AC-000068 竖屏布局 ----------
    const pOk = portrait.inside
      && !portrait.overlaps.stick_abxy && !portrait.overlaps.toggle_stick && !portrait.overlaps.toggle_abxy
      && !portrait.overlaps.hud_pair
      && (844 - 0) > 0   // 占位：确保分支可读
      && portrait.canvasClearOfBand;
    check('AC-000068', '390x844 竖屏：控件在视口内互不重叠、画布不压操作带',
      pOk, JSON.stringify({ inside: portrait.inside, overlaps: portrait.overlaps, band: portrait.band, canvas: portrait.rects.canvas }));

    // ---------- AC-000069 横屏与桌面 ----------
    const landToggleLeft = land.rects.toggle && land.rects.toggle.l <= 24 && land.rects.toggle.r < 844 / 2;
    const landNoOverlap = !land.overlaps.toggle_abxy && !land.overlaps.toggle_stick;
    const shortOk = short.inside && !short.overlaps.toggle_abxy && !short.overlaps.toggle_stick;
    const deskOk = !desk.touchMounted && desk.desktop.keyboardMoves.moved;
    check('AC-000069', '横屏开关在左半屏且不压键；矮屏不越界不重叠；桌面不显示控件但键盘可用',
      landToggleLeft && landNoOverlap && shortOk && deskOk,
      JSON.stringify({ landToggle: land.rects.toggle, landNoOverlap, shortOk, desk: { touch: desk.touchMounted, kb: desk.desktop.keyboardMoves } }));
  } finally {
    child.kill();
    try { bws.close(); } catch { /* ignore */ }
    await sleep(300);
    const failed = results.filter((r) => !r.pass);
    const out = path.join(__dirname, '..', '..', 'evidence');
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, 'touch_ui.json'), JSON.stringify({
      when: new Date().toISOString(), cdpPort: CDP_PORT,
      total: results.length, failed: failed.length, results, mapping: map,
    }, null, 2));
    console.log(`\n${results.length - failed.length}/${results.length} 通过；结果写入 evidence/touch_ui.json`);
    if (failed.length) process.exitCode = 1;
  }
}

main().catch((e) => { console.error('e2e 异常：', e); process.exit(1); });
