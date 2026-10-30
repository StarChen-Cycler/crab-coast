'use strict';
/* 全量可见性实测（REQ-000021 / AC-000084…086，含 AC-000073 复验）
 *
 * 真机反馈「走得远了其它角色会消失」。这里验证三件事：
 *   AC-000084 两只动物相距 > RADIUS_MAX(400) 时，双方 WS 快照都包含对方，且 world.scope='all'
 *   AC-000085 页面绘制集合 ⊆ 快照集合（缺失 0）：视野内的都在画，视野外的仍在快照里
 *   AC-000086 Agent 的 /state 仍按半径过滤（默认 200 / 上限 400），不受全量下发影响
 *   AC-000073 复验：绘制集合 ⊆ nearby（缺失 0）
 *
 * 取数：A 用 CDP 打开真实页面（拿到 drawnIds 与 camera），B 用裸 WS 客户端（同一套快照协议）。
 * 用法：node tools/probe_visible.js        （在 cloud/ 下；CDP_PORT 默认 9222）
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8800 + Math.floor(Math.random() * 60);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'visible-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-visible-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'visible.json');
const RADIUS_MAX = 400;          // config.js 默认上限，用来判断「足够远」

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const map = [];
function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
  map.push({ condition_id: condId, assertion: name, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} [${condId}] ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

// ---------- PNG ----------
const CRC = (() => { const t = new Int32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c; } return t; })();
const crc32 = (b) => { let c = -1; for (const x of b) c = CRC[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ -1) >>> 0; };
const chunk = (type, data) => {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
};
function cardPng(rgb) {
  const w = 192, h = 192;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = y * (w * 4 + 1) + 1 + x * 4;
      const body = (x % 48) > 10 && (x % 48) < 38 && (y % 48) > 10 && (y % 48) < 38;
      raw[o + 3] = body ? 255 : 0;
      if (body) { raw[o] = rgb[0]; raw[o + 1] = rgb[1]; raw[o + 2] = rgb[2]; }
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

// ---------- REST ----------
async function rest(method, p, { token, body, headers } = {}) {
  const h = Object.assign({}, headers);
  if (body !== undefined) h['content-type'] = 'application/json';
  if (token) h.authorization = `Bearer ${token}`;
  const r = await fetch(BASE + p, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
  let json = null;
  try { json = await r.json(); } catch { /* 非 JSON */ }
  return { status: r.status, json };
}

async function register(name, rgb) {
  const r = await rest('POST', '/api/v1/register', { body: { name }, headers: { 'x-register-code': CODE } });
  if (r.status !== 200) throw new Error(`注册 ${name} 失败：${r.status}`);
  const a = r.json;
  const up = await rest('POST', `/api/v1/animals/${a.animalId}/card`, {
    token: a.token,
    body: { pngBase64: cardPng(rgb).toString('base64'),
            manifest: { frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
                        rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps } },
  });
  if (up.status !== 200) throw new Error(`上传卡片失败：${up.status}`);
  return a;
}

/** 裸 WS：拿一条真实快照（与浏览器同一套协议）。 */
function wsSnapshot(token, timeoutMs = 6000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws?t=${encodeURIComponent(token)}`);
    const timer = setTimeout(() => { try { ws.close(); } catch { /* ignore */ } reject(new Error('等快照超时')); }, timeoutMs);
    ws.on('message', (raw) => {
      let msg; try { msg = JSON.parse(raw.toString('utf8')); } catch { return; }
      if (msg.type !== 'snapshot') return;
      clearTimeout(timer);
      ws.close();
      resolve(msg);
    });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

/** 走一段路（用 API 意图），返回结束位置。 */
async function walk(reg, dir, ms) {
  await rest('POST', `/api/v1/animals/me/intent`, { token: reg.token, body: { dir } });
  await sleep(ms);
  await rest('POST', `/api/v1/animals/me/intent`, { token: reg.token, body: { dir: null } });
  await sleep(150);
  const st = await rest('GET', '/api/v1/animals/me/state', { token: reg.token });
  return st.json.self;
}

// ---------- 页面内取数 ----------
const PAGE_VISIBLE = async function (cfg) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();
  while (Date.now() - t0 < 15000) {
    if (window.__play && window.__play.snapshot) break;
    await sleep(100);
  }
  const p = window.__play;
  if (!p || !p.snapshot) return { error: '页面未就绪' };
  await sleep(400);
  const c = p.camera;
  const s = p.snapshot.self;
  return {
    viewport: [innerWidth, innerHeight],
    self: { id: s.id, x: s.x, y: s.y },
    cam: { x: c.x, y: c.y, w: c.w, h: c.h, vw: c.vw, vh: c.vh, ox: c.ox, oy: c.oy },
    nearby: p.snapshot.nearby.map((n) => ({ id: n.id, x: n.x, y: n.y, d: n.distance })),
    drawn: c.drawnIds.slice(),
    worldScope: p.snapshot.world.scope,
    worldRadius: p.snapshot.world.radius,
  };
};

async function main() {
  let version;
  try { version = await cdpVersion(); } catch {
    console.error(`无法连接 CDP ${CDP_PORT}：请先启动带 --remote-debugging-port=${CDP_PORT} 的 Edge/Chrome 再重跑。`);
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

    const A = await register('VisA', [200, 90, 60]);
    const B = await register('VisB', [60, 140, 200]);
    const C = await register('VisC', [140, 200, 80]);   // 视野内的邻居，避免「视野内没有动物」的空断言
    console.log('A:', A.animalId, '| B:', B.animalId, '| C:', C.animalId);

    // 打开 A 的页面
    const { targetId } = await browserRpc('Target.createTarget', { url: 'about:blank' });
    await sleep(300);
    const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    const target = list.find((x) => x.id === targetId);
    const ws = await wsConnect(target.webSocketDebuggerUrl);
    const call = rpc(ws);
    await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await call('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
    await call('Page.navigate', { url: `${BASE}/play?t=${encodeURIComponent(A.token)}` });
    await sleep(2500);

    // 把两只动物拉远：A 往左、B 往右（世界可走区限制，实测量级 ~485px > RADIUS_MAX）；
    // 再把 C 放到 A 的视野里，保证「视野内全部绘制」这条不是空断言。
    const aPos = await walk(A, 'left', 3000);
    const bPos = await walk(B, 'right', 2000);
    const cPos = await walk(C, 'left', 1800);
    const dist = Math.hypot(aPos.x - bPos.x, aPos.y - bPos.y);
    const distC = Math.hypot(aPos.x - cPos.x, aPos.y - cPos.y);
    console.log(`A↔B ${dist.toFixed(0)}px，A↔C ${distC.toFixed(0)}px（A ${aPos.x},${aPos.y} / B ${bPos.x},${bPos.y} / C ${cPos.x},${cPos.y}）`);

    // AC-000084 双方快照互见
    const snapA = await wsSnapshot(A.token);
    const snapB = await wsSnapshot(B.token);
    const aSeesB = snapA.nearby.some((n) => n.id === B.animalId);
    const bSeesA = snapB.nearby.some((n) => n.id === A.animalId);
    check('AC-000084', '相距 > RADIUS_MAX 时双方 WS 快照都包含对方，world.scope=all',
      dist > RADIUS_MAX && aSeesB && bSeesA
      && snapA.world.scope === 'all' && snapB.world.scope === 'all',
      { distance: Math.round(dist), radiusMax: RADIUS_MAX, aSeesB, bSeesA,
        scopeA: snapA.world.scope, scopeB: snapB.world.scope, nearbyA: snapA.nearby.map((n) => n.id) });

    // AC-000085 / AC-000073 页面绘制集合
    const res = await call('Runtime.evaluate', {
      expression: `(${PAGE_VISIBLE.toString()})(${JSON.stringify({})})`,
      awaitPromise: true, returnByValue: true,
    });
    ws.close();
    await browserRpc('Target.closeTarget', { targetId });
    if (res.exceptionDetails) throw new Error('页面探针异常：' + JSON.stringify(res.exceptionDetails).slice(0, 300));
    const pg = res.result.value;
    if (pg.error) throw new Error(pg.error);

    const nearbyIds = pg.nearby.map((n) => n.id);
    const ghost = pg.drawn.filter((id) => !nearbyIds.includes(id));           // 画了但没收到
    const inView = pg.nearby.filter((n) =>
      n.x >= pg.cam.x - 24 && n.x <= pg.cam.x + pg.cam.vw + 24
      && n.y >= pg.cam.y - 43 && n.y <= pg.cam.y + pg.cam.vh + 6);
    const missingDrawn = inView.filter((n) => !pg.drawn.includes(n.id));       // 视野内却没画
    check('AC-000085', '页面绘制集合 ⊆ 快照集合；视野内的动物全部绘制（缺失 0）；远方那只仍在快照里',
      ghost.length === 0 && missingDrawn.length === 0 && inView.length >= 1 && pg.worldScope === 'all'
      && nearbyIds.includes(B.animalId) && pg.drawn.includes(C.animalId),
      { drawn: pg.drawn, nearby: nearbyIds, ghost, missingDrawn,
        inView: inView.map((n) => n.id), farIdInNearby: nearbyIds.includes(B.animalId),
        nearIdDrawn: pg.drawn.includes(C.animalId), scope: pg.worldScope });

    check('AC-000073', '复验：绘制集合 ⊆ nearby，缺失为 0（快照全量后依然成立）',
      ghost.length === 0 && pg.worldScope === 'all',
      { drawn: pg.drawn, nearby: nearbyIds, missing: ghost.length });

    // AC-000086 Agent 侧半径语义不变
    const st0 = await rest('GET', '/api/v1/animals/me/state', { token: A.token });
    const st1 = await rest('GET', '/api/v1/animals/me/state?radius=10000', { token: A.token });
    const d0 = st0.json.world, d1 = st1.json.world;
    const ids0 = st0.json.nearby.map((n) => n.id);
    const ids1 = st1.json.nearby.map((n) => n.id);
    check('AC-000086', '/state 仍按半径过滤：默认 200、传 10000 回显 400；近的（106px）在内、远的（487px）在外',
      d0.radius === 200 && d0.scope === 'radius' && d1.radius === 400 && d1.scope === 'radius'
      && ids0.includes(C.animalId) && !ids0.includes(B.animalId)
      && ids1.includes(C.animalId) && !ids1.includes(B.animalId),
      { defRadius: d0.radius, defScope: d0.scope, defNearby: ids0,
        bigRadius: d1.radius, bigScope: d1.scope, bigNearby: ids1,
        distanceFar: Math.round(dist), distanceNear: Math.round(distC) });

    fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
    fs.writeFileSync(EVIDENCE, JSON.stringify({
      when: new Date().toISOString(), cdpPort: CDP_PORT, port: PORT,
      animals: { a: { id: A.animalId, pos: aPos }, b: { id: B.animalId, pos: bPos },
                 c: { id: C.animalId, pos: cPos }, distance: Math.round(dist), distanceC: Math.round(distC) },
      total: results.length, failed: results.filter((r) => !r.pass).length,
      results, mapping: map, page: pg, snapshots: { a: snapA, b: snapB },
    }, null, 2), 'utf8');
    const failed = results.filter((r) => !r.pass);
    console.log(`${results.length - failed.length}/${results.length} 通过 → evidence/visible.json`);
    if (failed.length) process.exitCode = 1;
  } catch (e) {
    console.error('探针异常：' + (e && e.stack || e));
    if (log.length) console.error(log.join(''));
    process.exitCode = 1;
  } finally {
    try { child.kill(); } catch { /* ignore */ }
    await sleep(150);
    try { bws.close(); } catch { /* ignore */ }
    try { fs.rmSync(DATA_DIR, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main();
