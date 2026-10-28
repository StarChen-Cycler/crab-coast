'use strict';
/* 云端版端到端验收（服务端范围）。
   自己起一个临时服务（独立端口 + 临时 DATA_DIR），逐条对应台账条件：
     AC-000032 挡墙、AC-000033 意图 TTL、AC-000034 速度、
     AC-000035 口令门禁、AC-000036 明文不入库、AC-000037 越权 403、
     AC-000038/39/40 卡片校验、AC-000041/42/43 WS 快照、AC-000051/52/53/54 状态接口、
     AC-000055/57 健康检查与在线数。
   用法：node tools/e2e_multiplayer.js   （在 cloud/ 下）
*/

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const { DatabaseSync } = require('node:sqlite');
const WebSocket = require('ws');

const C = require('../shared/const');
const { loadGrid } = require('../shared/grid');

const PORT = 8100 + Math.floor(Math.random() * 300);
const BASE = `http://127.0.0.1:${PORT}`;
const CODE = 'test-register-code';
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-e2e-'));

const results = [];
function check(id, name, pass, detail) {
  results.push({ id, name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${name}${detail ? ' — ' + detail : ''}`);
}

// ---------------- PNG 编码（只用于造测试素材） ----------------
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = -1;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
/** pixel(x,y) → [r,g,b,a] */
function makePng(w, h, pixel) {
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 4 + 1)] = 0; // filter: none
    for (let x = 0; x < w; x++) {
      const [r, g, b, a] = pixel(x, y);
      const o = y * (w * 4 + 1) + 1 + x * 4;
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b; raw[o + 3] = a;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const MANIFEST = {
  frame: C.CARD.frame, cols: C.CARD.cols, rows: C.CARD.rows,
  rowOrder: C.CARD.rowOrder, footLine: C.CARD.footLine, fps: C.CARD.fps,
};

/** 合法卡：每帧中间有不透明像素，四角与每帧左下角透明 */
function validCardPng() {
  const S = C.CARD.frame;
  return makePng(S * C.CARD.cols, S * C.CARD.rows, (x, y) => {
    const lx = x % S;
    const ly = y % S;
    const isCorner = (x === 0 || x === S * C.CARD.cols - 1) && (y === 0 || y === S * C.CARD.rows - 1);
    const frameBottomLeft = lx === 0 && ly === S - 1;
    const body = lx > 10 && lx < S - 10 && ly > 10 && ly < S - 8;
    const a = isCorner || frameBottomLeft ? 0 : body ? 255 : 0;
    return [200, 90, 60, a];
  });
}

// ---------------- HTTP ----------------
async function req(method, p, { token, body, headers } = {}) {
  const h = { ...(headers || {}) };
  if (body !== undefined) h['content-type'] = 'application/json';
  if (token) h.authorization = `Bearer ${token}`;
  const res = await fetch(BASE + p, {
    method, headers: h,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json = null;
  try { json = await res.json(); } catch { /* 非 JSON */ }
  return { status: res.status, json };
}

async function waitHealth(timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(BASE + '/healthz');
      if (r.status === 200) return true;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------- 主流程 ----------------
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

    // AC-000055 一条命令启动后可访问
    const health = await req('GET', '/healthz');
    check('AC-000055', 'healthz 200 且含 online', health.status === 200 && typeof health.json.online === 'number',
      JSON.stringify(health.json));
    const home = await fetch(BASE + '/');
    check('AC-000055', '单机首页 200', home.status === 200, `status=${home.status}`);

    // AC-000035 口令门禁
    const noCode = await req('POST', '/api/v1/register', { body: { name: 'A' } });
    const badCode = await req('POST', '/api/v1/register', { body: { name: 'A', registerCode: 'nope' } });
    const okA = await req('POST', '/api/v1/register', { body: { name: 'A' }, headers: { 'x-register-code': CODE } });
    check('AC-000035', '无口令/错口令 401，正确口令 200',
      noCode.status === 401 && badCode.status === 401 && okA.status === 200,
      `${noCode.status}/${badCode.status}/${okA.status}`);
    const tokenA = okA.json && okA.json.token;
    const idA = okA.json && okA.json.animalId;
    check('AC-000035', 'token 长度 ≥ 40', !!tokenA && tokenA.length >= 40, `len=${tokenA && tokenA.length}`);

    // AC-000036 明文不入库
    const db = new DatabaseSync(path.join(DATA_DIR, 'world.db'));
    const rows = db.prepare('SELECT id, token_hash FROM animals').all();
    const plain = rows.some((r) => r.token_hash === tokenA);
    const hashed = rows.find((r) => r.id === idA);
    check('AC-000036', '库里只有 64 位哈希、无明文',
      !plain && hashed && /^[0-9a-f]{64}$/.test(hashed.token_hash), hashed && hashed.token_hash.slice(0, 12));
    db.close();

    const okB = await req('POST', '/api/v1/register', { body: { name: 'B' }, headers: { 'x-register-code': CODE } });
    const tokenB = okB.json.token;
    const idB = okB.json.animalId;

    // AC-000037 越权
    const cross = await req('POST', `/api/v1/animals/${idB}/intent`, { token: tokenA, body: { dir: 'right' } });
    const bAfter = await req('GET', `/api/v1/animals/${idB}/state`, { token: tokenB });
    check('AC-000037', 'A 的 token 改 B 返回 403 且 B 未变',
      cross.status === 403 && !!bAfter.json, `status=${cross.status}`);

    // AC-000051 状态含卡片信息（先无卡）
    const st0 = await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA });
    check('AC-000051', '无卡时 self.card 为 null',
      st0.status === 200 && st0.json.self.card === null, JSON.stringify(st0.json.self.card));

    // AC-000039 行数不符
    const threeRows = makePng(C.CARD.frame * 4, C.CARD.frame * 3, () => [10, 20, 30, 0]);
    const bad3 = await req('POST', `/api/v1/animals/${idA}/card`, {
      token: tokenA,
      body: { pngBase64: threeRows.toString('base64'), manifest: { ...MANIFEST, rows: 3 } },
    });
    check('AC-000039', '3 行卡片被拒且指出行数',
      bad3.status === 400 && bad3.json.errors.some((e) => e.includes('行数')),
      (bad3.json.errors || []).join(' | '));

    // AC-000040 四角不透明
    const S = C.CARD.frame;
    const opaqueCorner = makePng(S * 4, S * 4, (x, y) => ([0, 0].includes(x) && [0, 0].includes(y) ? [9, 9, 9, 255] : [0, 0, 0, 0]));
    const badCorner = await req('POST', `/api/v1/animals/${idA}/card`, {
      token: tokenA, body: { pngBase64: opaqueCorner.toString('base64'), manifest: MANIFEST },
    });
    check('AC-000040', '四角不透明被拒并给出角坐标',
      badCorner.status === 400 && badCorner.json.errors.some((e) => e.includes('四角')),
      (badCorner.json.errors || []).join(' | '));

    // AC-000038 合法卡片
    const good = await req('POST', `/api/v1/animals/${idA}/card`, {
      token: tokenA, body: { pngBase64: validCardPng().toString('base64'), manifest: MANIFEST },
    });
    const st1 = await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA });
    check('AC-000038', '合法卡片 200，状态含 192×192 与摘要',
      good.status === 200 && st1.json.self.card && st1.json.self.card.width === 192
      && /^[0-9a-f]{64}$/.test(st1.json.self.card.digest),
      JSON.stringify(st1.json.self.card));

    // AC-000051 有卡后
    check('AC-000051', '有卡后 self.card 含尺寸与摘要', !!st1.json.self.card, JSON.stringify(st1.json.self.card && st1.json.self.card.width));

    // AC-000034 速度：1 秒位移
    const p0 = (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self;
    await req('POST', `/api/v1/animals/${idA}/intent`, { token: tokenA, body: { dir: 'right' } });
    await sleep(1000);
    const p1 = (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self;
    const dist = Math.hypot(p1.x - p0.x, p1.y - p0.y);
    check('AC-000034', '1 秒位移 99–121 px', dist >= 99 && dist <= 121, `dist=${dist.toFixed(1)}`);

    // AC-000033 意图 TTL
    await req('POST', `/api/v1/animals/${idA}/intent`, { token: tokenA, body: { dir: 'right' } });
    await sleep(3500);
    const q0 = (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self;
    await sleep(600);
    const q1 = (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self;
    check('AC-000033', '意图 3 秒后自动停车',
      q0.x === q1.x && q0.y === q1.y && q0.moving === false,
      `x ${q0.x}→${q1.x} moving=${q0.moving}`);

    // AC-000032 挡墙：朝一个方向走 3 秒，采样点必须都在可行走格内
    const { grid } = loadGrid();
    await req('POST', `/api/v1/animals/${idB}/intent`, { token: tokenB, body: { dir: 'up' } });
    let allWalkable = true;
    const samples = [];
    for (let i = 0; i < 15; i++) {
      await sleep(200);
      const s = (await req('GET', `/api/v1/animals/${idB}/state`, { token: tokenB })).json.self;
      samples.push([s.x, s.y]);
      if (!grid.canStand(s.x, s.y)) allWalkable = false;
    }
    await req('POST', `/api/v1/animals/${idB}/intent`, { token: tokenB, body: { dir: null } });
    check('AC-000032', '朝墙走 3 秒，全部采样都在可行走格内', allWalkable,
      `末点 ${samples[samples.length - 1].join(',')}；采样 ${samples.length} 次`);

    // AC-000052 nearby 半径过滤：同一对动物，小半径看不到、大半径看得到
    const dReal = Math.hypot(
      (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self.x
        - (await req('GET', `/api/v1/animals/${idB}/state`, { token: tokenB })).json.self.x,
      (await req('GET', `/api/v1/animals/${idA}/state`, { token: tokenA })).json.self.y
        - (await req('GET', `/api/v1/animals/${idB}/state`, { token: tokenB })).json.self.y,
    );
    const nearSmall = (await req('GET', `/api/v1/animals/${idA}/state?radius=50`, { token: tokenA })).json;
    const nearBig = (await req('GET', `/api/v1/animals/${idA}/state?radius=400`, { token: tokenA })).json;
    const bigHasB = nearBig.nearby.find((n) => n.id === idB);
    check('AC-000052', '半径 50 不含对方、半径 400 含对方且距离正确',
      !nearSmall.nearby.some((n) => n.id === idB)
      && !!bigHasB && Math.abs(bigHasB.distance - dReal) <= 2,
      `实际距离=${dReal.toFixed(1)} nearby(400)=${JSON.stringify(bigHasB || null)}`);

    // AC-000054 半径上限
    const big = (await req('GET', `/api/v1/animals/${idA}/state?radius=10000`, { token: tokenA })).json;
    check('AC-000054', 'radius=10000 被钳制并回显', big.world.radius <= 400, `radius=${big.world.radius}`);

    // AC-000053 不泄露凭据
    const raw = JSON.stringify(big);
    check('AC-000053', '响应里搜不到任何 token', !raw.includes(tokenA) && !raw.includes(tokenB));

    // AC-000041/042/043 WS
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws?t=${encodeURIComponent(tokenA)}`);
    const snaps = [];
    await new Promise((resolve, reject) => {
      ws.on('open', resolve);
      ws.on('error', reject);
      setTimeout(() => reject(new Error('ws open timeout')), 5000);
    });
    ws.on('message', (m) => { try { snaps.push(JSON.parse(m.toString())); } catch { /* ignore */ } });
    await sleep(3000);
    check('AC-000041', '3 秒内收到 ≥20 条快照且 self.id 正确',
      snaps.length >= 20 && snaps[0].self.id === idA, `snaps=${snaps.length} id=${snaps[0] && snaps[0].self.id}`);

    const beforeX = snaps[snaps.length - 1].self.x;
    ws.send(JSON.stringify({ type: 'intent', dir: 'left' }));   // 上面已走到右边界，往回走才有位移
    await sleep(700);
    const afterX = snaps[snaps.length - 1].self.x;
    check('AC-000042', 'WS 下发意图后 x 减少（四向固定朝向生效）',
      afterX < beforeX && snaps[snaps.length - 1].self.facing === 'left',
      `x ${beforeX}→${afterX} facing=${snaps[snaps.length - 1].self.facing}`);
    ws.send(JSON.stringify({ type: 'intent', dir: null }));

    // AC-000057 在线数
    const h2 = await req('GET', '/healthz');
    check('AC-000057', 'WS 连上后 online ≥1', h2.json.online >= 1, `online=${h2.json.online}`);

    // AC-000043 nearby 含对方且不含凭据（用能覆盖实际距离的半径查）
    const stA2 = (await req('GET', `/api/v1/animals/${idA}/state?radius=400`, { token: tokenA })).json;
    const inRange = stA2.nearby.some((n) => n.id === idB);
    check('AC-000043', 'nearby 含对方 id 且不含任何凭据',
      inRange
      && stA2.nearby.every((n) => n.id && !('token' in n) && !('token_hash' in n))
      && !JSON.stringify(stA2).includes(tokenB),
      `含对方=${inRange} nearby=${stA2.nearby.length}`);

    ws.close();
  } finally {
    child.kill();
    await sleep(300);
    const failed = results.filter((r) => !r.pass);
    const out = path.join(__dirname, '..', '..', 'evidence');
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, 'e2e_multiplayer.json'), JSON.stringify({
      when: new Date().toISOString(), port: PORT, dataDir: DATA_DIR,
      total: results.length, failed: failed.length, results,
    }, null, 2));
    console.log(`\n${results.length - failed.length}/${results.length} 通过；结果写入 evidence/e2e_multiplayer.json`);
    if (failed.length) {
      console.log('失败项：');
      for (const f of failed) console.log(`  - ${f.id} ${f.name} (${f.detail})`);
      process.exitCode = 1;
    }
  }
}

main().catch((e) => {
  console.error('e2e 异常：', e);
  process.exit(1);
});
