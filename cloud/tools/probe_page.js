'use strict';
/* 浏览器进场页实测（REQ-000011 r3 / AC-000041…044）
 *
 * r3 把「半径 200 内的其他动物」改为「相机视野内的其他动物」（相机语义见 REQ-000018）。
 * 这条需求是**页面**需求，所以这里用 CDP 打开真实页面取数，而不是只看服务端广播：
 *   AC-000041 进场 3 秒内收到 ≥20 条快照，且 self.id = 注册返回的 animalId
 *   AC-000042 按住「右」0.5 秒 x 增大、y 基本不变；松手 300ms 内 moving=false
 *   AC-000043 页面 nearby 含参照动物的 id 与坐标，且响应里搜不到任何 token / 哈希
 *   AC-000044 主动断开 WebSocket 后 5 秒内自动重连并继续收到快照
 *
 * 用法：node tools/probe_page.js          （在 cloud/ 下）
 * 环境：CDP_PORT（默认 9222）；浏览器未开时以非零码退出并说明（不静默跳过）。
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8700 + Math.floor(Math.random() * 60);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'page-probe-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-page-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'page_live.json');

const MIN_SNAPSHOTS = 20;      // AC-000041：3 秒内至少 20 条（10Hz 服务端广播）
const MIN_STEP_PX = 30;        // AC-000042：0.5 秒至少走 30px（速度 110px/s）
const RECONNECT_MAX_MS = 5000; // AC-000044：5 秒内恢复
const NEAR_TOL_PX = 2;         // y 基本不变

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
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

// ---------- 页面内取数 ----------
const PAGE_PROBE = async function (cfg) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();
  while (Date.now() - t0 < 15000) {
    if (window.__play && window.__play.snapshot) break;
    await sleep(100);
  }
  const p = window.__play;
  if (!p || !p.snapshot) return { error: '页面未就绪（__play.snapshot 缺失）' };
  const out = {};

  // AC-000041 3 秒内快照条数（每次消息都会换新的对象引用）
  let count = 0;
  let last = p.snapshot;
  const t = performance.now();
  while (performance.now() - t < 3000) {
    await sleep(60);
    if (p.snapshot !== last) { count++; last = p.snapshot; }
  }
  out.snapshots = { count, ms: Math.round(performance.now() - t), selfId: p.snapshot.self.id, connected: p.connected };

  // AC-000042 按住右 0.5 秒
  const s0 = p.snapshot.self;
  p.sendIntent('right');
  await sleep(500);
  const s1 = p.snapshot.self;
  p.sendIntent(null);
  await sleep(300);
  const s2 = p.snapshot.self;
  out.moveRight = { from: [s0.x, s0.y], to: [s1.x, s1.y], dx: +(s1.x - s0.x).toFixed(1),
                    dy: +(s1.y - s0.y).toFixed(1), facing: s1.facing,
                    stopped: s2.moving === false, movingAfterRelease: s2.moving };

  // AC-000043 nearby 内容（含参照动物；不含凭据）
  const raw = JSON.stringify(p.snapshot);
  out.nearby = {
    ids: p.snapshot.nearby.map((n) => n.id),
    sample: p.snapshot.nearby.slice(0, 2),
    radius: p.snapshot.world.radius,
    jsonBytes: raw.length,
  };

  // AC-000044 主动断开 → 自动重连
  const beforeDrop = p.snapshot;
  p._drop();
  await sleep(150);
  out.reconnect = { droppedConnected: p.connected, recoveredMs: null, snapshotsResumed: false };
  const t1 = performance.now();
  while (performance.now() - t1 < 8000) {
    await sleep(80);
    if (p.connected && p.snapshot !== beforeDrop) {
      out.reconnect.recoveredMs = Math.round(performance.now() - t1);
      out.reconnect.snapshotsResumed = true;
      break;
    }
    if (p.connected) out.reconnect.connectedAt = Math.round(performance.now() - t1);
  }
  out.reconnect.finalConnected = p.connected;
  return out;
};

async function rest(method, p, { token, body, headers } = {}) {
  const h = Object.assign({}, headers);
  if (body !== undefined) h['content-type'] = 'application/json';
  if (token) h.authorization = `Bearer ${token}`;
  const r = await fetch(BASE + p, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
  let json = null;
  try { json = await r.json(); } catch { /* 非 JSON */ }
  return { status: r.status, json };
}

async function main() {
  let version;
  try { version = await cdpVersion(); } catch {
    console.error(`无法连接 CDP ${CDP_PORT}：请先启动一次带 --remote-debugging-port=${CDP_PORT} 的 Edge/Chrome 再重跑。`);
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
    let serverUp = false;
    for (let i = 0; i < 80 && !serverUp; i++) { await sleep(150); try { serverUp = (await fetch(BASE + '/healthz')).ok; } catch { /* wait */ } }
    if (!serverUp) { console.error('服务没起来\n' + log.join('')); process.exit(1); }

    const reg = async (name) => {
      const r = await rest('POST', '/api/v1/register', { body: { name }, headers: { 'x-register-code': CODE } });
      if (r.status !== 200) throw new Error(`注册 ${name} 失败：${r.status}`);
      const a = r.json;
      const up = await rest('POST', `/api/v1/animals/${a.animalId}/card`, {
        token: a.token,
        body: { pngBase64: cardPng().toString('base64'),
                manifest: { frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
                            rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps } },
      });
      if (up.status !== 200) throw new Error(`上传卡片失败：${up.status}`);
      return a;
    };
    const A = await reg('PageA');
    const B = await reg('PageB');
    console.log('页面动物:', A.animalId, '| 参照:', B.animalId);

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
    await sleep(2600);
    const res = await call('Runtime.evaluate', {
      expression: `(${PAGE_PROBE.toString()})(${JSON.stringify({})})`,
      awaitPromise: true, returnByValue: true,
    });
    ws.close();
    await browserRpc('Target.closeTarget', { targetId });
    if (res.exceptionDetails) throw new Error('页面探针异常：' + JSON.stringify(res.exceptionDetails).slice(0, 300));
    const out = res.result.value;
    if (out.error) throw new Error(out.error);

    check('AC-000041', '进场 3 秒内收到 ≥20 条快照，self.id 与注册返回一致',
      out.snapshots.count >= MIN_SNAPSHOTS && out.snapshots.selfId === A.animalId && out.snapshots.connected,
      out.snapshots);

    check('AC-000042', '按住「右」0.5 秒 x 增大 ≥30px、y 基本不变；松手 300ms 内 moving=false',
      out.moveRight.dx >= MIN_STEP_PX && Math.abs(out.moveRight.dy) <= NEAR_TOL_PX
      && out.moveRight.facing === 'right' && out.moveRight.stopped === true,
      out.moveRight);

    const nearbyHasB = out.nearby.ids.includes(B.animalId);
    const rawText = JSON.stringify(out);
    const leak = [A.token, B.token].some((tk) => tk && rawText.includes(tk));
    check('AC-000043', '页面 nearby 含参照动物 id 与坐标，且整份快照里搜不到任何 token',
      nearbyHasB && !leak && !!out.nearby.sample.length,
      { ids: out.nearby.ids, sample: out.nearby.sample, leak, radius: out.nearby.radius });

    check('AC-000044', '主动断开 WebSocket 后 5 秒内自动重连并继续收到快照',
      out.reconnect.snapshotsResumed && out.reconnect.recoveredMs !== null
      && out.reconnect.recoveredMs <= RECONNECT_MAX_MS && out.reconnect.finalConnected,
      out.reconnect);

    fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
    fs.writeFileSync(EVIDENCE, JSON.stringify({
      when: new Date().toISOString(), cdpPort: CDP_PORT, port: PORT,
      animals: { page: A.animalId, ref: B.animalId },
      total: results.length, failed: results.filter((r) => !r.pass).length,
      results, raw: out,
    }, null, 2), 'utf8');
    const failed = results.filter((r) => !r.pass);
    console.log(`${results.length - failed.length}/${results.length} 通过 → evidence/page_live.json`);
    if (failed.length) process.exitCode = 1;
  } catch (e) {
    console.error('探针异常：' + (e && e.stack || e));
    if (log.length) console.error(log.join(''));
    process.exitCode = 1;
  } finally {
    try { child.kill(); } catch { /* ignore */ }
    await sleep(150);
    try { await bws.close(); } catch { /* ignore */ }
    try { fs.rmSync(DATA_DIR, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main();
