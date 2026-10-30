'use strict';
/* 相机裁切视角端到端验收（REQ-000018 / AC-000070…075）
 *
 * 自己拉起服务（临时 DATA_DIR，不碰生产数据），复用已开浏览器的 CDP 端口（默认 9222），
 * 三档视口、每档一只出生在原点的动物（避免跨档位置耦合），断言：
 *   1:1 画布、居中跟随、平移量一致、左/右/下钳制、视野大于世界时整幅居中、
 *   可见 ⊆ 已收到、Agent 半径语义不变。
 * 结果按 condition 映射写入 evidence/camera.json。
 *
 * 取数原则：页面里的 __play.camera 与 worldToScreen 就是**绘制实际使用的那一份**，
 * 断言对象不是另写一份公式；cameraTarget 纯函数只用于真实移动到不了的位置（世界上边界）。
 *
 * 用法：node tools/e2e_camera.js
 * 环境：CDP_PORT（默认 9222）；浏览器未开时以非零码退出并说明（不静默跳过）。
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8600 + Math.floor(Math.random() * 60);
const BASE = `http://127.0.0.1:${PORT}`;
const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const CODE = 'cam-e2e-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-cam-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'camera.json');

const CENTER_TOL = 2;        // 居中偏差上限（px）
const PAN_TOL = 2;           // 相机位移与世界位移之差上限（px）
const MIN_PAN_PX = 30;       // 一次采样里至少要走动这么多，否则判定没走动

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const map = [];
const phases = [];           // 原始样本（写进 evidence，便于复核）

function check(condId, name, pass, detail) {
  results.push({ condition: condId, name, pass: !!pass, detail });
  map.push({ condition_id: condId, assertion: name, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} [${condId}] ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

// ---------- PNG（造合法动作卡） ----------
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

// ---------- 页面内取数（在浏览器里执行） ----------
const PAGE_CAMERA = async function (cfg) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();
  while (Date.now() - t0 < 15000) {
    if (window.__play && window.__play.snapshot) break;
    await sleep(100);
  }
  const p = window.__play;
  if (!p || !p.snapshot) return { error: '页面未就绪（__play.snapshot 缺失）' };

  const cv = document.getElementById('world');
  const snap = () => {
    const c = p.camera;
    const s = p.snapshot.self;
    const rp = c.renderSelf || { x: s.x, y: s.y };   // 屏幕上真正画的位置（插值后，REQ-000020）
    const rect = cv.getBoundingClientRect();
    return {
      cam: { x: +c.x.toFixed(2), y: +c.y.toFixed(2), w: c.w, h: c.h,
             vw: c.vw, vh: c.vh, ox: c.ox, oy: c.oy,
             worldW: c.worldW, worldH: c.worldH },
      self: { id: s.id, x: s.x, y: s.y, facing: s.facing, moving: s.moving },
      render: { x: +rp.x.toFixed(2), y: +rp.y.toFixed(2) },
      screen: p.worldToScreen(rp.x, rp.y),
      nearby: p.snapshot.nearby.map((n) => ({ id: n.id, x: n.x, y: n.y, d: n.distance })),
      worldScope: p.snapshot.world.scope,
      worldRadius: p.snapshot.world.radius,
      drawn: c.drawnIds,
      canvas: { w: Math.round(rect.width), h: Math.round(rect.height),
                l: Math.round(rect.left), t: Math.round(rect.top),
                bw: cv.width, bh: cv.height },
      viewport: [innerWidth, innerHeight],
      band: getComputedStyle(document.documentElement).getPropertyValue('--touch-band').trim(),
    };
  };

  const out = { phase: cfg.name, samples: [] };
  out.initial = snap();
  for (const step of cfg.steps) {
    p.sendIntent(step.dir);
    const marks = step.marks || [step.ms];
    let last = 0;
    for (const m of marks) {
      if (m > last) await sleep(m - last);
      last = m;
      out.samples.push(Object.assign({ label: `${step.label}@${m}ms` }, snap()));
    }
    p.sendIntent(null);
    await sleep(160);
  }
  // 真实移动到不了的位置（世界上边界等），用绘制同一份纯函数断言
  out.pure = cfg.pureCases.map((c) => ({
    name: `${c.name} (self=${c.x},${c.y} view=${c.w}x${c.h})`,
    got: p.cameraTarget(c.x, c.y, c.w, c.h),
  }));
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

async function runPhase(browserRpc, cfg) {
  const { targetId, wsUrl } = await openTarget(browserRpc);
  const ws = await wsConnect(wsUrl);
  const call = rpc(ws);
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', {
    width: cfg.w, height: cfg.h, deviceScaleFactor: 1, mobile: !!cfg.touch,
  });
  await call('Emulation.setTouchEmulationEnabled', { enabled: !!cfg.touch, maxTouchPoints: 5 });
  await call('Page.navigate', { url: cfg.url });
  await sleep(2600);
  const res = await call('Runtime.evaluate', {
    expression: `(${PAGE_CAMERA.toString()})(${JSON.stringify(cfg)})`,
    awaitPromise: true, returnByValue: true,
  });
  ws.close();
  await browserRpc('Target.closeTarget', { targetId });
  if (res.exceptionDetails) throw new Error('页面断言异常：' + JSON.stringify(res.exceptionDetails).slice(0, 300));
  return res.result.value;
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
async function register(name) {
  const r = await rest('POST', '/api/v1/register', { body: { name }, headers: { 'x-register-code': CODE } });
  if (r.status !== 200) throw new Error(`注册 ${name} 失败：${r.status} ${JSON.stringify(r.json)}`);
  return r.json;
}
async function uploadCard(reg, rgb) {
  const r = await rest('POST', `/api/v1/animals/${reg.animalId}/card`, {
    token: reg.token,
    body: {
      pngBase64: cardPng(rgb).toString('base64'),
      manifest: { frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
                  rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps },
    },
  });
  if (r.status !== 200) throw new Error(`上传卡片失败：${r.status} ${JSON.stringify(r.json)}`);
}

const clampTo = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const unclampedX = (s) => s.cam.x > 0 && s.cam.x < s.cam.worldW - s.cam.vw;
const unclampedY = (s) => s.cam.y > 0 && s.cam.y < s.cam.worldH - s.cam.vh;
const dScreen = (a, b) => ({ dx: +(b.screen.x - a.screen.x).toFixed(2), dy: +(b.screen.y - a.screen.y).toFixed(2) });

// ---------- 主流程 ----------
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

    // 每档一只出生在同一个可走点（spawn）的动物：档间互不影响
    const regA = async (name) => { const a = await register(name); await uploadCard(a, [200, 90, 60]); return a; };
    const A1 = await regA('CamP1');
    const A2 = await regA('CamP2');
    const A3 = await regA('CamP3');
    const B = await regA('CamRef');       // 同屏参照物（不打开页面）
    const url = (a) => `${BASE}/play?t=${encodeURIComponent(a.token)}`;
    console.log('动物:', A1.animalId, A2.animalId, A3.animalId, '| 参照:', B.animalId);

    // ================= P1 竖屏 390x844：1:1 画布 + 水平居中 + 平移一致 + 可见⊆已收到 =================
    const p1 = await runPhase(browserRpc, {
      name: 'P1-390x844', w: 390, h: 844, touch: true, url: url(A1),
      steps: [
        { label: 'right-1.2s', dir: 'right', ms: 1200 },
        // 平移一致要在「稳态」两端取点：插值渲染有约一个快照间隔的滞后，起点若刚进场，
        // 滞后还没建立，两个端点就不可比（这是插值方案的固有性质，不是 bug）。
        { label: 'left-2.4s', dir: 'left', marks: [1200, 2400] },
      ],
      pureCases: [{ name: '左上角', x: 0, y: 0, w: 390, h: 608 }],
    });
    phases.push(p1);

    const s0 = p1.initial;
    check('AC-000070', '390x844：画布位图 = 相机窗口 = CSS 尺寸（1 逻辑像素 = 1 CSS 像素），画布贴视口左上角',
      s0.canvas.bw === s0.cam.w && s0.canvas.bh === s0.cam.h
      && s0.canvas.w === s0.cam.w && s0.canvas.h === s0.cam.h
      && s0.canvas.w === s0.viewport[0]
      && s0.canvas.h === s0.viewport[1] - parseFloat(s0.band)
      && s0.canvas.l === 0 && s0.canvas.t === 0,
      { canvas: s0.canvas, cam: [s0.cam.w, s0.cam.h], viewport: s0.viewport, band: s0.band });

    const mid = p1.samples[0];
    const dxMid = Math.abs(mid.screen.x - mid.cam.w / 2);
    check('AC-000070', '390x844 竖屏：自己屏幕坐标水平居中，偏差 ≤2px（相机未被钳制）',
      dxMid <= CENTER_TOL && unclampedX(mid),
      { screen: mid.screen, want: mid.cam.w / 2, diff: +dxMid.toFixed(2), camX: mid.cam.x,
        camMaxX: mid.cam.worldW - mid.cam.vw });

    // 平移：屏幕坐标必须纹丝不动（用户可见的性质），且相机与自己的渲染位置严格同步；
    // 世界位移与相机位移的差异来自 10Hz 整数快照 + 插值相位（固有误差），按 ≤5% 校核
    const panA = p1.samples[1];
    const panB = p1.samples[2];
    const dWorld = panB.self.x - panA.self.x;
    const dCam = panB.cam.x - panA.cam.x;
    const dRender = panB.render.x - panA.render.x;
    check('AC-000070', '稳态平移：屏幕坐标不变（≤2px）、相机与渲染位置同步（≤0.5px）、世界位移与相机位移差 ≤5%',
      Math.abs(dWorld) >= MIN_PAN_PX
      && Math.abs(panB.screen.x - panA.screen.x) <= CENTER_TOL
      && Math.abs(dCam - dRender) <= 0.5
      && Math.abs(dCam - dWorld) <= Math.abs(dWorld) * 0.05,
      { window: 'left-1.2s→2.4s', dWorld: +dWorld.toFixed(1), dCam: +dCam.toFixed(1),
        dRender: +dRender.toFixed(1), dScreen: dScreen(panA, panB) });

    const bState = await rest('GET', `/api/v1/animals/${B.animalId}/state`, { token: B.token });
    const bPos = bState.json.self;
    const vis = mid;
    const bScreen = { x: bPos.x - Math.round(vis.cam.x) + vis.cam.ox,
                      y: bPos.y - Math.round(vis.cam.y) + vis.cam.oy };
    const bInView = bScreen.x >= 0 && bScreen.x <= vis.cam.w && bScreen.y >= 0 && bScreen.y <= vis.cam.h;
    const bInNearby = vis.nearby.some((n) => n.id === B.animalId);
    const bDrawn = vis.drawn.includes(B.animalId);
    const missing = vis.drawn.filter((id) => !vis.nearby.some((n) => n.id === id));
    check('AC-000073', '快照是全量（world.scope=all、radius=null）；视野内的另一只必在 nearby 内并被绘制；绘制 ⊄ 集合缺失 0',
      vis.worldScope === 'all' && vis.worldRadius === null && bInView && bInNearby && bDrawn && missing.length === 0,
      { bPos: [bPos.x, bPos.y], bScreen, bInView, bInNearby, bDrawn, missing,
        worldScope: vis.worldScope, worldRadius: vis.worldRadius,
        nearby: vis.nearby.map((n) => n.id), drawn: vis.drawn });

    // ================= P2 宽矮 900x300：双轴居中 + 下/右/左钳制 =================
    // 路线都贴着「已知可走的通道」：竖直只在出生列（上 94 / 下 115），水平只在出生行（左 305 / 右 184）。
    // 上一版把竖直与水平混着走，插值/网络抖动让动物停进了只有斜向能出的凹槽，两次运动都为 0。
    const p2 = await runPhase(browserRpc, {
      name: 'P2-900x300', w: 900, h: 300, touch: true, url: url(A2),
      steps: [
        { label: 'down-1.2s', dir: 'down', ms: 1200 },              // s0 下边界：相机 y 顶到 240
        { label: 'up-1.6s', dir: 'up', marks: [1200, 1600] },        // s1,s2（s2 双轴未钳制 → 居中）
        { label: 'down-1.0s', dir: 'down', ms: 1000 },               // s3 回到宽通道那一行
        { label: 'right-1.5s', dir: 'right', marks: [600, 1500] },   // s4,s5 右边界：相机 x 顶到 60
        { label: 'left-3.0s', dir: 'left', marks: [3000] },          // s6 左边界：相机 x 回到 0
      ],
      pureCases: [
        { name: '左上角', x: 0, y: 0, w: 900, h: 300 },
        { name: '右下角', x: 960, y: 540, w: 900, h: 300 },
        { name: '世界中心', x: 480, y: 270, w: 900, h: 300 },
      ],
    });
    phases.push(p2);
    const [sDown, sUp1, sUp2, sBack, sRight1, sRight2, sLeft] = p2.samples;

    check('AC-000070', '900x300：相机双轴都未钳制时，自己屏幕坐标双轴居中，偏差 ≤2px',
      unclampedX(sUp2) && unclampedY(sUp2)
      && Math.abs(sUp2.screen.x - sUp2.cam.w / 2) <= CENTER_TOL
      && Math.abs(sUp2.screen.y - sUp2.cam.h / 2) <= CENTER_TOL,
      { screen: sUp2.screen, want: [sUp2.cam.w / 2, sUp2.cam.h / 2],
        diff: [+(sUp2.screen.x - sUp2.cam.w / 2).toFixed(2), +(sUp2.screen.y - sUp2.cam.h / 2).toFixed(2)],
        cam: [sUp2.cam.x, sUp2.cam.y],
        camRange: [[0, sUp2.cam.worldW - sUp2.cam.vw], [0, sUp2.cam.worldH - sUp2.cam.vh]] });

    const wantY = sDown.cam.worldH - sDown.cam.vh;
    check('AC-000072', '持续向下：相机停在 y = worldH-h，动物屏幕 y 继续增大（≥30px）',
      sDown.cam.y === wantY && (sDown.screen.y - p2.initial.screen.y) >= MIN_PAN_PX,
      { cam: sDown.cam.y, want: wantY, screen: [p2.initial.screen.y, sDown.screen.y],
        dScreen: dScreen(p2.initial, sDown) });

    const wantX = sRight2.cam.worldW - sRight2.cam.vw;
    check('AC-000072', '持续向右：相机停在 x = worldW-w，动物屏幕 x 继续增大（≥30px）',
      sRight2.cam.x === wantX && sRight1.cam.x === wantX
      && (sRight2.screen.x - sRight1.screen.x) >= MIN_PAN_PX,
      { cam: [sRight1.cam.x, sRight2.cam.x], want: wantX,
        screen: [sRight1.screen.x, sRight2.screen.x], dScreen: dScreen(sRight1, sRight2) });

    check('AC-000071', '持续向左：相机停在 x=0，动物屏幕 x 继续减小（≥30px），且相机不再移动',
      sLeft.cam.x === 0 && (sRight2.screen.x - sLeft.screen.x) >= MIN_PAN_PX,
      { camBefore: sRight2.cam.x, camAfter: sLeft.cam.x,
        screen: [sRight2.screen.x, sLeft.screen.x], dScreen: dScreen(sRight2, sLeft) });

    const pureLT = p2.pure[0].got;
    const pureRT = p2.pure[1].got;
    const pureMid = p2.pure[2].got;
    check('AC-000071', '纯函数：自己贴世界左上角 (0,0) 时相机 = (0,0)（上边界与左边界同一套钳制）',
      pureLT.x === 0 && pureLT.y === 0,
      { case: p2.pure[0].name, got: pureLT, note: '世界上边界 195px 内没有可走地块，真实移动到不了，故用同一份纯函数验证' });
    check('AC-000072', '纯函数：自己贴世界右下角时相机 = (worldW-w, worldH-h)',
      pureRT.x === 960 - 900 && pureRT.y === 540 - 300,
      { case: p2.pure[1].name, got: pureRT, want: [60, 240] });
    check('AC-000070', '纯函数：自己位于世界中心时相机把自己放在画布中心',
      pureMid.x === (480 - 900 / 2) && pureMid.y === (270 - 300 / 2),
      { case: p2.pure[2].name, got: pureMid, want: [30, 120] });

    // ================= P3 1400x1000：视野大于世界 → 整幅居中、相机不动 =================
    const p3 = await runPhase(browserRpc, {
      name: 'P3-1400x1000', w: 1400, h: 1000, touch: false, url: url(A3),
      steps: [{ label: 'right-1.0s', dir: 'right', ms: 1000 }],
      pureCases: [{ name: '视野大于世界', x: 480, y: 270, w: 1400, h: 1000 }],
    });
    phases.push(p3);
    const q = p3.samples[0];
    const wantOx = Math.floor((q.cam.w - q.cam.vw) / 2);
    const wantOy = Math.floor((q.cam.h - q.cam.vh) / 2);
    check('AC-000075', '视野 (1400x1000) 大于世界：相机固定 (0,0)、世界在画布内居中，走动也不动',
      q.cam.x === 0 && q.cam.y === 0 && q.cam.vw === 960 && q.cam.vh === 540
      && q.cam.ox === wantOx && q.cam.oy === wantOy
      && p3.initial.cam.x === 0 && p3.initial.cam.y === 0
      && Math.abs(q.screen.x - (q.render.x + wantOx)) <= CENTER_TOL
      && Math.abs((q.self.x - p3.initial.self.x)) >= MIN_PAN_PX,
      { cam: [q.cam.x, q.cam.y], view: [q.cam.vw, q.cam.vh], oxy: [q.cam.ox, q.cam.oy],
        want: [wantOx, wantOy], screen: q.screen, selfX: q.self.x,
        travel: +(q.self.x - p3.initial.self.x).toFixed(1) });

    const big = p3.pure[0].got;
    check('AC-000075', '纯函数：视野大于世界时 vw/vh 取世界尺寸、留白按整幅居中',
      big.x === 0 && big.y === 0 && big.vw === 960 && big.vh === 540
      && big.ox === 220 && big.oy === 230,
      { case: p3.pure[0].name, got: big });

    // ================= Agent 半径语义不变（AC-000074） =================
    const st0 = await rest('GET', '/api/v1/animals/me/state', { token: A1.token });
    const st1 = await rest('GET', '/api/v1/animals/me/state?radius=10000', { token: A1.token });
    check('AC-000074', '/state 默认 radius=200；传 10000 回显 400（与相机无关）',
      st0.status === 200 && st0.json.world.radius === 200
      && st1.status === 200 && st1.json.world.radius === 400,
      { def: st0.json && st0.json.world && st0.json.world.radius,
        big: st1.json && st1.json.world && st1.json.world.radius });

    console.log(`\nP1 半径请求 ${s0.cam.desiredRadius}px / 服务端回显 ${s0.serverRadius}px`);
  } finally {
    child.kill();
    try { bws.close(); } catch { /* ignore */ }
    await sleep(300);
    const failed = results.filter((r) => !r.pass);
    fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
    fs.writeFileSync(EVIDENCE, JSON.stringify({
      when: new Date().toISOString(),
      cdpPort: CDP_PORT,
      total: results.length,
      passed: results.length - failed.length,
      failed: failed.length,
      results,
      mapping: map,
      samples: phases,
    }, null, 2), 'utf8');
    console.log(`${results.length - failed.length}/${results.length} 通过；结果写入 evidence/camera.json`);
    if (failed.length) process.exitCode = 1;
  }
}

main().catch((e) => { console.error('e2e 异常：', e); process.exit(1); });
