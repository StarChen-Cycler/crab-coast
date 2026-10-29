'use strict';
/* WebSocket 视角半径探针（REQ-000018 / AC-000070）。

验证 ws 握手上的 `&r=` 参数：
  · 不带 r      → 快照 world.radius = 200（默认不变）
  · r=224       → 224（相机视野半对角，按需放大）
  · r=10000     → 400（RADIUS_MAX 钳制）
  · r=abc       → 200（非法值回落默认，不报错、连接照常）
同时回归 Agent 侧语义不受影响：
  · GET /state                    → radius 200
  · GET /state?radius=10000        → radius 400
用法：node tools/probe_ws_radius.js   （在 cloud/ 下；自起临时服务，退出码 0 = 全 PASS）
*/

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const WebSocket = require('ws');

const PORT = 8400 + Math.floor(Math.random() * 300);
const BASE = `http://127.0.0.1:${PORT}`;
const CODE = 'probe-register-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-radius-'));
const EVIDENCE = path.join(__dirname, '..', '..', 'evidence', 'ws_radius.json');

const results = [];
function check(id, name, pass, detail) {
  results.push({ id, name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name}${detail ? ' — ' + detail : ''}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitHealth(timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(BASE + '/healthz');
      if (r.status === 200) return true;
    } catch { /* 还没起来 */ }
    await sleep(150);
  }
  return false;
}

/** 用给定 query 建一条 WS，返回它第一条快照里的 world.radius。 */
function firstSnapshotRadius(query) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws?t=${encodeURIComponent(TOKEN)}${query}`);
    const timer = setTimeout(() => {
      try { ws.close(); } catch { /* ignore */ }
      reject(new Error(`等快照超时（${query || '无参数'}）`));
    }, 6000);
    ws.on('message', (raw) => {
      let msg;
      try { msg = JSON.parse(raw.toString('utf8')); } catch { return; }
      if (msg.type !== 'snapshot') return;
      clearTimeout(timer);
      ws.close();
      resolve(msg.world.radius);
    });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

async function stateRadius(query) {
  const r = await fetch(`${BASE}/api/v1/animals/me/state${query}`, {
    headers: { authorization: `Bearer ${TOKEN}` },
  });
  const j = await r.json();
  return { status: r.status, radius: j && j.world && j.world.radius };
}

let TOKEN = null;

async function main() {
  const log = [];
  const child = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR, REGISTER_CODE: CODE },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', (d) => log.push(d.toString()));
  child.stderr.on('data', (d) => log.push(d.toString()));

  try {
    if (!await waitHealth()) {
      console.error('服务没起来：\n' + log.join(''));
      process.exit(1);
    }

    const reg = await fetch(BASE + '/api/v1/register', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-register-code': CODE },
      body: JSON.stringify({ name: 'R' }),
    });
    const body = await reg.json();
    TOKEN = body.token;
    if (!TOKEN) throw new Error('注册失败：' + JSON.stringify(body));

    const noParam = await firstSnapshotRadius('');
    check('C1-1', 'ws 不带 r → 快照半径 200', noParam === 200, `radius=${noParam}`);

    const camRadius = await firstSnapshotRadius('&r=224');
    check('C1-2', 'ws r=224 → 快照半径 224', camRadius === 224, `radius=${camRadius}`);

    const huge = await firstSnapshotRadius('&r=10000');
    check('C1-3', 'ws r=10000 → 钳制到 400', huge === 400, `radius=${huge}`);

    const bad = await firstSnapshotRadius('&r=abc');
    check('C1-4', 'ws r=abc → 回落 200 且连接正常', bad === 200, `radius=${bad}`);

    const st0 = await stateRadius('');
    check('C1-5', '/state 默认 radius 200', st0.status === 200 && st0.radius === 200,
      `status=${st0.status} radius=${st0.radius}`);

    const st1 = await stateRadius('?radius=10000');
    check('C1-6', '/state?radius=10000 回显 400', st1.status === 200 && st1.radius === 400,
      `status=${st1.status} radius=${st1.radius}`);

    const failed = results.filter((r) => !r.pass);
    const summary = {
      at: new Date().toISOString(),
      port: PORT,
      total: results.length,
      passed: results.length - failed.length,
      failed: failed.length,
      results,
    };
    fs.writeFileSync(EVIDENCE, JSON.stringify(summary, null, 2), 'utf8');
    console.log(`\n${results.length - failed.length}/${results.length} PASS → ${EVIDENCE}`);
    process.exitCode = failed.length ? 1 : 0;
  } catch (e) {
    console.error('探针异常：' + (e && e.stack || e));
    if (log.length) console.error(log.join(''));
    process.exitCode = 1;
  } finally {
    try { child.kill(); } catch { /* ignore */ }
    await sleep(120);
    try { fs.rmSync(DATA_DIR, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main();
