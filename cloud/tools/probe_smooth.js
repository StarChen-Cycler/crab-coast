'use strict';
/* 平滑与连接自愈实测（REQ-000019 / 000020）
 *
 * REQ-000019（连接）：
 *   AC-000076 隐藏 5 秒再恢复：2 秒内连续收到 ≥3 条快照，HUD 回到「已连接」
 *   AC-000077 旋屏（390x844 → 844x390）：2 秒内快照继续到达，不出现常驻「快照中断」
 *   AC-000078 半开连接（不派发 close、数据停止）：看门狗 4 秒内重连成功，且只重建 1 次
 *   AC-000079 被第三个会话顶掉：10 秒内不重连，HUD 保持「已在别处被接管」
 * REQ-000020（插值渲染）：
 *   AC-000080 逐帧采样：相邻帧渲染位移最大值 ≤3px（修复前 11px），累计位移与 110px/s 误差 ≤5%
 *   AC-000081 相机相邻帧位移 ≤3px，非零位移帧占比 ≥90%
 *   AC-000082 松手 300ms 后渲染位置与快照真值 ≤1px，且此后 5 帧不再变化
 *   AC-000083 静止时连续 5 帧画布像素完全一致（像素对齐、不闪烁）
 *
 * 用法：node tools/probe_smooth.js        （在 cloud/ 下；CDP_PORT 默认 9222）
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8900 + Math.floor(Math.random() * 60);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'smooth-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-smooth-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'smooth.json');

const MAX_FRAME_STEP = 3;        // AC-000080/081：每帧位移上限（修复前 11px）
const CAM_ZERO_MAX_RATIO = 0.1;  // AC-000081：相机零位移帧占比上限
const SPEED = 110;               // 与 shared/const.js 一致
const SPEED_TOL = 0.05;
const CONVERGE_PX = 1;           // AC-000082
const RECOVER_MS = 2000;         // AC-000076/077
const HALF_OPEN_MS = 4000;       // AC-000078

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// 逐步日志：同步写文件，进程被中途杀掉也能看到走到哪一步（CDP 冻结过页面导致过一次挂死）
const LOG = path.join(__dirname, '..', 'build', 'probe_smooth.log');
try { fs.mkdirSync(path.dirname(LOG), { recursive: true }); fs.writeFileSync(LOG, ''); } catch { /* ignore */ }
function log(line) {
  try { fs.appendFileSync(LOG, line + '\n'); } catch { /* ignore */ }
  console.log(line);
}

const results = [];
const map = [];
function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
  map.push({ condition_id: condId, assertion: name, detail });
  log(`${pass ? 'PASS' : 'FAIL'} [${condId}] ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
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

async function evaluate(call, fn, arg) {
  const res = await call('Runtime.evaluate', {
    expression: `(${fn.toString()})(${JSON.stringify(arg === undefined ? null : arg)})`,
    awaitPromise: true, returnByValue: true,
  });
  if (res.exceptionDetails) throw new Error('页面求值异常：' + JSON.stringify(res.exceptionDetails).slice(0, 300));
  return res.result.value;
}

// ---------- 页面内动作 ----------
// ① 逐帧采样：按住左 2.5 秒，记录每帧渲染位置与相机位置
const PAGE_SAMPLE = async function (cfg) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const p = window.__play;
  while (!(p && p.snapshot)) await sleep(100);
  await sleep(600);
  const samples = [];
  let stop = false;
  const tick = () => {
    const c = p.camera;
    const s = p.snapshot.self;
    samples.push({ t: performance.now(), rx: c.renderSelf.x, ry: c.renderSelf.y,
                   cx: c.x, cy: c.y, sx: s.x, sy: s.y, moving: s.moving });
    if (!stop) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  await sleep(120);
  p.sendIntent(cfg.dir);
  await sleep(cfg.holdMs);
  p.sendIntent(null);
  await sleep(60);
  stop = true;
  await sleep(80);
  return samples;
};

// ② 收敛 + 像素稳定：松手后 300ms 比较渲染位置与快照真值，并抓 5 帧画布
const PAGE_SETTLE = async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const p = window.__play;
  const cv = document.getElementById('world');
  await sleep(300);
  const a = p.camera;
  const truth = p.snapshot.self;
  const renders = [];
  const frames = [];
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => requestAnimationFrame(r));
    const c = p.camera;
    renders.push({ x: c.renderSelf.x, y: c.renderSelf.y });
    frames.push(cv.toDataURL());
  }
  await sleep(200);
  const b = p.camera;
  return {
    renderAfter300: renders[0],
    truth: { x: truth.x, y: truth.y },
    later: { x: b.renderSelf.x, y: b.renderSelf.y },
    framesIdentical: frames.every((f) => f === frames[0]),
    frameBytes: frames[0].length,
  };
};

// ③ 半开连接：摘掉所有回调并让"最后一条快照"变旧，看门狗只能靠超时发现
const PAGE_HALF_OPEN = function () {
  const p = window.__play;
  if (!p) return { ok: false };
  const before = p.camera.reconnectCount;
  const ok = p._killSilently();
  return { ok, reconnectBefore: before };
};

// ⑤ 模拟「切后台挂起」：摘掉所有回调和数据（真实后台就是既不派发 close 也不再收快照），
//    让「最后一条快照」变旧，然后等 5 秒——期间看门狗本来就该把它救回来。
const PAGE_SUSPEND = function () {
  const p = window.__play;
  if (!p) return { ok: false };
  const before = p.camera.reconnectCount;
  const ok = p._killSilently();
  return { ok, reconnectBefore: before, lastAge: p.camera.lastSnapAgeMs };
};

// ⑥ 等待健康：轮询 connected + 快照新鲜度（页面内定时器，页面没被冻结所以一定推进）
const PAGE_WAIT_HEALTHY = async function (cfg) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const p = window.__play;
  const t0 = performance.now();
  let healthyAt = null;
  while (performance.now() - t0 < cfg.timeoutMs) {
    if (p.connected && p.camera.lastSnapAgeMs < 300) { healthyAt = Math.round(performance.now() - t0); break; }
    await sleep(50);
  }
  const c = p.camera;
  const hud = document.getElementById('link-hud');
  return { healthyAt, connected: p.connected, lastAge: c.lastSnapAgeMs,
           hud: hud.textContent, hudBad: hud.classList.contains('bad'),
           reconnectDelta: c.reconnectCount - cfg.baselineReconnects, stopped: c.stopped };
};

// ⑤ 旋转/可见性事件后的状态快照
const PAGE_STATE = function () {
  const p = window.__play;
  const hud = document.getElementById('link-hud');
  return { connected: p.connected, lastSnapAgeMs: p.camera.lastSnapAgeMs,
           hud: hud.textContent, hudBad: hud.classList.contains('bad'),
           reconnectCount: p.camera.reconnectCount, stopped: p.camera.stopped,
           viewport: [innerWidth, innerHeight], snapInterval: p.camera.snapInterval };
};

const PAGE_DISPATCH_VISIBLE = function () {
  document.dispatchEvent(new Event('visibilitychange'));
  return document.visibilityState;
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
  const childOut = [];
  child.stdout.on('data', (d) => childOut.push(d.toString()));
  child.stderr.on('data', (d) => childOut.push(d.toString()));

  try {
    let up = false;
    for (let i = 0; i < 80 && !up; i++) { await sleep(150); try { up = (await fetch(BASE + '/healthz')).ok; } catch { /* wait */ } }
    if (!up) { console.error('服务没起来\n' + childOut.join('')); process.exit(1); }

    const reg = await rest('POST', '/api/v1/register', { body: { name: 'SmoothA' }, headers: { 'x-register-code': CODE } });
    const A = reg.json;
    const up2 = await rest('POST', `/api/v1/animals/${A.animalId}/card`, {
      token: A.token,
      body: { pngBase64: cardPng().toString('base64'),
              manifest: { frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
                          rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps } },
    });
    if (up2.status !== 200) throw new Error('上传卡片失败：' + up2.status);

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
    try { await call('Page.bringToFront'); } catch { /* 可选 */ }   // 后台标签页 rAF 会被节流，逐帧采样需要前台
    await sleep(2600);
    log('页面动物: ' + A.animalId);

    // ============ AC-000076 挂起 5 秒再恢复 ============
    // 不能真把渲染进程冻结（Page.setWebLifecycleState('frozen') 在本机 Edge 上 resume 不回来，
    // 会把整个探针挂死），所以用同样的可观测状态来模拟：回调全摘、最后一条快照变旧 = 切后台后的样子。
    const suspend = await evaluate(call, PAGE_SUSPEND);
    log('suspend: ' + JSON.stringify(suspend));
    await sleep(5000);
    const visibleState = await evaluate(call, PAGE_DISPATCH_VISIBLE);   // 恢复可见时浏览器派发的就是它
    const health76 = await evaluate(call, PAGE_WAIT_HEALTHY, { timeoutMs: RECOVER_MS, baselineReconnects: 0 });
    check('AC-000076', '挂起 5 秒后恢复可见：2 秒内快照恢复、HUD 回到「已连接」',
      suspend.ok === true && health76.healthyAt !== null && health76.healthyAt <= RECOVER_MS
      && health76.hud === '已连接' && !health76.hudBad,
      { suspend, visibleState, healthyAfterResumeMs: health76.healthyAt,
        reconnectDelta: health76.reconnectDelta, hud: health76.hud, lastAge: health76.lastAge });

    // ============ AC-000080/081 逐帧采样（竖屏，相机不会顶到边界） ============
    const baseline077 = (await evaluate(call, PAGE_STATE)).reconnectCount;
    const frames = await evaluate(call, PAGE_SAMPLE, { dir: 'left', holdMs: 2500 });
    const d = [];
    for (let i = 1; i < frames.length; i++) {
      d.push({ dt: frames[i].t - frames[i - 1].t,
               drx: frames[i].rx - frames[i - 1].rx,
               ddx: frames[i].cx - frames[i - 1].cx });
    }
    const maxStep = d.reduce((m, x) => Math.max(m, Math.abs(x.drx)), 0);
    const maxCamStep = d.reduce((m, x) => Math.max(m, Math.abs(x.ddx)), 0);
    const movingFrames = d.filter((x) => Math.abs(x.ddx) > 0.01);
    const camZeroRatio = 1 - movingFrames.length / d.length;
    // 稳态窗口：从第一次位移到最后一帧，避免起步/收尾的加速段
    const firstMove = frames.findIndex((f, i) => i > 0 && Math.abs(f.rx - frames[i - 1].rx) > 0.01);
    const winStart = frames[firstMove];
    const winEnd = frames[frames.length - 1];
    const winSec = (winEnd.t - winStart.t) / 1000;
    const travelled = Math.abs(winEnd.rx - winStart.rx);
    const expected = SPEED * winSec;
    const speedErr = Math.abs(travelled - expected) / expected;

    check('AC-000080', '逐帧采样：相邻帧渲染位移最大值 ≤3px；稳态累计位移与 110px/s 误差 ≤5%',
      maxStep <= MAX_FRAME_STEP && speedErr <= SPEED_TOL && d.length > 60,
      { frames: frames.length, maxStep: +maxStep.toFixed(2), speedErr: +(speedErr * 100).toFixed(1) + '%',
        travelled: +travelled.toFixed(1), expected: +expected.toFixed(1), winSec: +winSec.toFixed(2) });

    check('AC-000081', '相机相邻帧位移最大值 ≤3px，非零位移帧占比 ≥90%',
      maxCamStep <= MAX_FRAME_STEP && camZeroRatio <= CAM_ZERO_MAX_RATIO,
      { maxCamStep: +maxCamStep.toFixed(2), camZeroRatio: +(camZeroRatio * 100).toFixed(1) + '%',
        movingFrames: movingFrames.length, totalFrames: d.length });

    // ============ AC-000082/083 收敛与像素稳定 ============
    const settle = await evaluate(call, PAGE_SETTLE);
    const dx = Math.abs(settle.renderAfter300.x - settle.truth.x);
    const dy = Math.abs(settle.renderAfter300.y - settle.truth.y);
    const laterDrift = Math.max(Math.abs(settle.later.x - settle.renderAfter300.x),
                                Math.abs(settle.later.y - settle.renderAfter300.y));
    check('AC-000082', '松手 300ms 后渲染位置与快照真值差 ≤1px，且此后不再变化',
      dx <= CONVERGE_PX && dy <= CONVERGE_PX && laterDrift <= CONVERGE_PX,
      { render: settle.renderAfter300, truth: settle.truth, dx: +dx.toFixed(2), dy: +dy.toFixed(2),
        laterDrift: +laterDrift.toFixed(2) });
    check('AC-000083', '静止时连续 5 帧画布像素完全一致（像素对齐、不闪烁）',
      settle.framesIdentical === true,
      { framesIdentical: settle.framesIdentical, frameBytes: settle.frameBytes });

    // ============ AC-000077 旋屏 ============
    await call('Emulation.setDeviceMetricsOverride', { width: 844, height: 390, deviceScaleFactor: 1, mobile: true });
    const rotState0 = await evaluate(call, PAGE_STATE);
    const health77 = await evaluate(call, PAGE_WAIT_HEALTHY, { timeoutMs: RECOVER_MS, baselineReconnects: baseline077 });
    await sleep(800);
    const rotState1 = await evaluate(call, PAGE_STATE);
    check('AC-000077', '旋屏（390x844 → 844x390）后 2 秒内快照继续到达，不出现「快照中断」',
      health77.healthyAt !== null && health77.healthyAt <= RECOVER_MS
      && rotState1.lastSnapAgeMs < 600 && rotState1.hud !== '快照中断' && rotState1.connected,
      { viewportBefore: rotState0.viewport, viewportAfter: rotState1.viewport,
        healthyAfterRotateMs: health77.healthyAt, reconnectDelta: health77.reconnectDelta,
        hud: rotState1.hud, lastAge: rotState1.lastSnapAgeMs });

    // ============ AC-000078 半开连接（看门狗） ============
    const base078 = (await evaluate(call, PAGE_STATE)).reconnectCount;
    const half = await evaluate(call, PAGE_HALF_OPEN);
    const health78 = await evaluate(call, PAGE_WAIT_HEALTHY, { timeoutMs: HALF_OPEN_MS + 2000, baselineReconnects: base078 });
    check('AC-000078', '半开连接（不派发 close、数据停止）：4 秒内重连成功，且只重建 1 次',
      half.ok === true && health78.healthyAt !== null && health78.healthyAt <= HALF_OPEN_MS
      && health78.reconnectDelta === 1,
      { halfOpen: half, healthyAfterHalfOpenMs: health78.healthyAt, reconnectDelta: health78.reconnectDelta });

    // ============ AC-000079 被接管后不重连（最后跑：跑完页面就废了） ============
    const base079 = (await evaluate(call, PAGE_STATE)).reconnectCount;
    const keep = [];
    for (let i = 0; i < 2; i++) {
      const sock = new WebSocket(`ws://127.0.0.1:${PORT}/ws?t=${encodeURIComponent(A.token)}`);
      await new Promise((res, rej) => { sock.on('open', res); sock.on('error', rej); });
      keep.push(sock);
      await sleep(200);
    }
    await sleep(1000);
    const st079a = await evaluate(call, PAGE_STATE);
    await sleep(9000);
    const st079b = await evaluate(call, PAGE_STATE);
    for (const s of keep) { try { s.close(); } catch { /* ignore */ } }
    check('AC-000079', '被第三个会话顶掉后 10 秒内不重连，HUD 保持「已在别处被接管」',
      st079a.stopped === true && st079b.connected === false
      && st079b.reconnectCount === base079 && /接管/.test(st079b.hud),
      { afterEvict: { stopped: st079a.stopped, hud: st079a.hud },
        after10s: { connected: st079b.connected, reconnectCount: st079b.reconnectCount,
                    reconnectDelta: st079b.reconnectCount - base079, hud: st079b.hud, stopped: st079b.stopped } });

    ws.close();
    await browserRpc('Target.closeTarget', { targetId });

    fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
    fs.writeFileSync(EVIDENCE, JSON.stringify({
      when: new Date().toISOString(), cdpPort: CDP_PORT, port: PORT, animal: A.animalId,
      total: results.length, failed: results.filter((r) => !r.pass).length,
      results, mapping: map,
      raw: { suspend, health76, health77, health78, settle, frames: frames.slice(0, 8), frameCount: frames.length,
             rotState0, rotState1, st079a, st079b },
    }, null, 2), 'utf8');
    const failed = results.filter((r) => !r.pass);
    console.log(`${results.length - failed.length}/${results.length} 通过 → evidence/smooth.json`);
    if (failed.length) process.exitCode = 1;
  } catch (e) {
    console.error('探针异常：' + (e && e.stack || e));
    if (childOut.length) console.error(childOut.join(''));
    process.exitCode = 1;
  } finally {
    try { child.kill(); } catch { /* ignore */ }
    await sleep(150);
    try { bws.close(); } catch { /* ignore */ }
    try { fs.rmSync(DATA_DIR, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main();
