'use strict';
/* AC-000056：换 PORT / DATA_DIR / REGISTER_CODE 后生效，且运行时数据只写 DATA_DIR。 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const PORT = 8123;
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'crab-env-'));
const CODE = 'custom-code-xyz';
const ROOT = path.join(__dirname, '..', '..');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const ROOT2 = path.join(__dirname, '..', '..');
  const defaultDb = path.join(ROOT2, 'cloud', 'data', 'world.db');
  const before = fs.existsSync(defaultDb) ? fs.statSync(defaultDb).mtimeMs : null;

  const child = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR, REGISTER_CODE: CODE },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const log = [];
  child.stdout.on('data', (d) => log.push(d.toString()));
  child.stderr.on('data', (d) => log.push(d.toString()));

  const base = `http://127.0.0.1:${PORT}`;
  let up = false;
  for (let i = 0; i < 60 && !up; i++) {
    await sleep(150);
    try { up = (await fetch(base + '/healthz')).ok; } catch { /* not yet */ }
  }
  const out = { port: PORT, dataDir: DATA_DIR, started: up, checks: {} };

  try {
    if (!up) {
      out.checks.listen = false;
      out.log = log.join('');
      return report(out);
    }
    out.checks.listenOnCustomPort = true;

    // 默认口令必须失效，自定义口令必须生效
    const wrong = await fetch(base + '/api/v1/register', {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-register-code': 'dev-code' },
      body: JSON.stringify({ name: 'X' }),
    });
    const right = await fetch(base + '/api/v1/register', {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-register-code': CODE },
      body: JSON.stringify({ name: 'X' }),
    });
    out.checks.customCodeWorks = wrong.status === 401 && right.status === 200;
    out.checks.statuses = [wrong.status, right.status];

    // 数据落在自定义 DATA_DIR
    await sleep(300);
    const db = path.join(DATA_DIR, 'world.db');
    out.checks.dbInDataDir = fs.existsSync(db);
    const cardsDir = path.join(DATA_DIR, 'cards');
    out.checks.cardDirInDataDir = fs.existsSync(cardsDir);

    // 代码目录（默认 data/）在本次运行期间不应被写入
    const after = fs.existsSync(defaultDb) ? fs.statSync(defaultDb).mtimeMs : null;
    out.checks.defaultDataUntouched = before === after;
    out.checks.defaultData = { before, after };
  } finally {
    child.kill();
    await sleep(300);
    report(out);
  }
}

function report(out) {
  const failed = Object.entries(out.checks).filter(([k, v]) => v === false).map(([k]) => k);
  out.ok = failed.length === 0;
  out.failed = failed;
  const dir = path.join(ROOT, 'evidence');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'e2e_env.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
  if (!out.ok) process.exitCode = 1;
}

main().catch((e) => { console.error(e); process.exit(1); });
