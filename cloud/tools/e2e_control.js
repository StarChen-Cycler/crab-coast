'use strict';
/* 控制语义端到端验收（REQ-000016 + AC-000063）。
   AC-000058 两路后按优先 / AC-000059 松开回落 / AC-000060 续期生效（含对照组）
   AC-000061 第三个连接淘汰最早 / AC-000062 不区分来源身份 / AC-000063 manifest 取值错误被拒
   用法：node tools/e2e_control.js
*/

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const WebSocket = require('ws');

const C = require('../shared/const');

const PORT = 8450 + Math.floor(Math.random() * 100);
const BASE = `http://127.0.0.1:${PORT}`;
const CODE = 'ctl-test-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-ctl-'));

const results = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function check(id, name, pass, detail) {
  results.push({ id, name, pass: !!pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name}${detail ? ' — ' + detail : ''}`);
}

async function api(method, p, { token, body } = {}) {
  const h = {};
  if (body !== undefined) h['content-type'] = 'application/json';
  if (token) h.authorization = `Bearer ${token}`;
  const res = await fetch(BASE + p, {
    method, headers: h, body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json = null;
  try { json = await res.json(); } catch { /* ignore */ }
  return { status: res.status, json };
}

async function register(name) {
  const res = await fetch(BASE + '/api/v1/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-register-code': CODE },
    body: JSON.stringify({ name }),
  });
  const j = await res.json();
  return { id: j.animalId, token: j.token };
}

async function state(a, radius) {
  const q = radius ? `?radius=${radius}` : '';
  const r = await api('GET', `/api/v1/animals/${a.id}/state${q}`, { token: a.token });
  return r.json;
}

// 以 100ms 步长持续发送方向（模拟"按住"）：先发一次，keepalive 时再周期性续期
async function hold(a, dir, ms, { keepalive = true, onSample } = {}) {
  const t0 = Date.now();
  await api('POST', `/api/v1/animals/${a.id}/intent`, { token: a.token, body: { dir } });
  while (Date.now() - t0 < ms) {
    if (keepalive) await api('POST', `/api/v1/animals/${a.id}/intent`, { token: a.token, body: { dir } });
    if (onSample) await onSample(Date.now() - t0);
    await sleep(100);
  }
}

function wsOpen(token) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws?t=${encodeURIComponent(token)}`);
    ws.on('open', () => resolve(ws));
    ws.on('error', reject);
    setTimeout(() => reject(new Error('ws open timeout')), 5000);
  });
}

// --- 造卡片 ---
const CRC = (() => { const t = new Int32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c; } return t; })();
const crc32 = (b) => { let c = -1; for (const x of b) c = CRC[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ -1) >>> 0; };
const chunk = (type, data) => {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
};
function png(w, h) {
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
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const MANIFEST = () => ({
  frame: 48, cols: 4, rows: 4, rowOrder: C.CARD.rowOrder, footLine: 43, fps: 8,
});

async function main() {
  const child = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR, REGISTER_CODE: CODE },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const log = [];
  child.stdout.on('data', (d) => log.push(d.toString()));
  child.stderr.on('data', (d) => log.push(d.toString()));

  try {
    let up = false;
    for (let i = 0; i < 80 && !up; i++) {
      await sleep(150);
      try { up = (await fetch(BASE + '/healthz')).ok; } catch { /* wait */ }
    }
    if (!up) { console.error('服务没起来\n' + log.join('')); process.exit(1); }

    const A = await register('HoldA');
    const B = await register('HoldB');
    const Cc = await register('TwoSrc');

    // ---------- AC-000063 manifest 取值错误 ----------
    const bad = await api('POST', `/api/v1/animals/${A.id}/card`, {
      token: A.token,
      body: {
        pngBase64: png(192, 192).toString('base64'),
        manifest: { ...MANIFEST(), fps: 7, footLine: 40 },
      },
    });
    const errs = (bad.json && bad.json.errors) || [];
    const st0 = await state(A);
    check('AC-000063', 'manifest 取值错误被拒且不落库',
      bad.status === 400
      && errs.some((e) => e.includes('帧率'))
      && errs.some((e) => e.includes('脚底线'))
      && st0.self.card === null,
      `status=${bad.status} errors=${errs.length} card=${st0.self.card}`);

    // ---------- AC-000060 续期生效（A）+ 对照组（B） ----------
    async function prep(a) {
      await hold(a, 'up', 300);                 // 走到 y≈380
      await api('POST', `/api/v1/animals/${a.id}/intent`, { token: a.token, body: { dir: null } });
      await sleep(150);
      return (await state(a)).self;
    }

    const a0 = await prep(A);
    let a32 = null;
    await hold(A, 'left', 3400, {
      keepalive: true,
      onSample: async (t) => { if (t >= 3150 && !a32) a32 = (await state(A)).self; },
    });
    const a34 = (await state(A)).self;
    await api('POST', `/api/v1/animals/${A.id}/intent`, { token: A.token, body: { dir: null } });

    const b0 = await prep(B);
    let b32 = null;
    await hold(B, 'left', 3400, {
      keepalive: false,                          // 只在开始时发一次
      onSample: async (t) => { if (t >= 3150 && !b32) b32 = (await state(B)).self; },
    });
    const b34 = (await state(B)).self;

    const aMoved = a0.x - a34.x;
    const bMoved = b0.x - b34.x;
    // 判别信号：续期组在 t=3.2s（距墙壁还有约 30px）仍 moving；对照组已在 t≈3.0s 被 TTL 停下
    const bInTtlRange = bMoved >= 297 && bMoved <= 363;   // ≈ 3 秒 × 110px/s ±10%
    check('AC-000060', '续期组 t=3.2s 仍在移动且位移 ≥330px；对照组按 TTL 在 t≈3s 停下',
      a32 && a32.moving === true && aMoved >= 330
      && b32 && b32.moving === false && bInTtlRange,
      `续期 dx=${aMoved.toFixed(1)} moving@3.2=${a32 && a32.moving}；对照 dx=${bMoved.toFixed(1)} moving@3.2=${b32 && b32.moving}`);

    // ---------- AC-000058 / AC-000059 两来源 ----------
    const c0 = (await state(Cc)).self;
    // 来源甲：REST 按住「上」（持续续期）
    let restTimer = setInterval(() => {
      api('POST', `/api/v1/animals/${Cc.id}/intent`, { token: Cc.token, body: { dir: 'up' } });
    }, 500);
    await api('POST', `/api/v1/animals/${Cc.id}/intent`, { token: Cc.token, body: { dir: 'up' } });
    await sleep(200);

    const ws = await wsOpen(Cc.token);
    ws.send(JSON.stringify({ type: 'intent', dir: 'right' }));   // 来源乙：后按者
    await sleep(600);
    const s1 = (await state(Cc)).self;            // 期望向右
    ws.send(JSON.stringify({ type: 'intent', dir: null }));      // 松开「右」→ 应回落到「上」
    await sleep(600);
    const s2 = (await state(Cc)).self;            // 期望向上
    clearInterval(restTimer);
    await api('POST', `/api/v1/animals/${Cc.id}/intent`, { token: Cc.token, body: { dir: null } });

    check('AC-000058', '后按的「右」优先（facing=right 且 x 增大）',
      s1.facing === 'right' && s1.x > c0.x,
      `facing=${s1.facing} x ${c0.x}→${s1.x}`);
    check('AC-000059', '松开「右」后回落到仍按住的「上」（不停车）',
      s2.facing === 'up' && s2.y < s1.y,
      `facing=${s2.facing} y ${s1.y}→${s2.y}`);

    // ---------- AC-000062 不区分来源身份 ----------
    const raw = JSON.stringify(s2);
    check('AC-000062', '状态里没有任何来源身份字段',
      !/"(agent|human|source|sourceKey|role)"/.test(raw),
      `keys=${Object.keys(s2).join(',')}`);

    // ---------- AC-000061 三会话 FIFO ----------
    const w1 = await wsOpen(Cc.token);
    const w2 = await wsOpen(Cc.token);
    const closed = [];
    w1.on('close', (code, reason) => closed.push({ code, reason: reason.toString() }));
    const w3 = await wsOpen(Cc.token);
    await sleep(800);
    const stillOpen = [w1.readyState, w2.readyState, w3.readyState].map((r) => r === 1);
    check('AC-000061', '第 3 个连接淘汰最早的那个，最终恰好 2 个在线',
      closed.length === 1 && closed[0].code === 1008 && /replace/i.test(closed[0].reason)
      && stillOpen[0] === false && stillOpen[1] === true && stillOpen[2] === true,
      `closed=${JSON.stringify(closed)} open=${stillOpen}`);
    for (const w of [w1, w2, w3, ws]) { try { w.close(); } catch { /* ignore */ } }
  } finally {
    child.kill();
    await sleep(300);
    const failed = results.filter((r) => !r.pass);
    const out = path.join(__dirname, '..', '..', 'evidence');
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, 'e2e_control.json'), JSON.stringify({
      when: new Date().toISOString(), port: PORT, total: results.length,
      failed: failed.length, results,
    }, null, 2));
    console.log(`\n${results.length - failed.length}/${results.length} 通过；结果写入 evidence/e2e_control.json`);
    if (failed.length) process.exitCode = 1;
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
