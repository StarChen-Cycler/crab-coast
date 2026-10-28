#!/usr/bin/env node
'use strict';
/* Agent 用的命令行（REQ-000009 / 010 / 014）。
   node cli/animalctl.js <command> [options]

   register      --code <注册口令> [--name 名字]
   upload-card   --token … --dir <含 card.png 与 manifest.json 的目录>
   move          --token … --dir up|down|left|right|stop
   state         --token … [--radius 200] [--json]
   play-url      --token … [--animal A-0001]
   rotate-token  --token …

   通用选项：--server http://127.0.0.1:8090  （或环境变量 CRAB_SERVER）
             --token …                      （或环境变量 CRAB_TOKEN）
             --animal A-0001                （或环境变量 CRAB_ANIMAL；多数命令可用 me 代替）
*/

const fs = require('node:fs');
const path = require('node:path');

const argv = process.argv.slice(2);
const cmd = argv[0];

function opt(name, fallback) {
  const i = argv.indexOf('--' + name);
  if (i === -1) return fallback;
  return argv[i + 1];
}
function flag(name) {
  return argv.includes('--' + name);
}

const SERVER = (opt('server', process.env.CRAB_SERVER) || 'http://127.0.0.1:8090').replace(/\/+$/, '');
const TOKEN = opt('token', process.env.CRAB_TOKEN);
const ANIMAL = opt('animal', process.env.CRAB_ANIMAL) || 'me';

function die(msg) {
  console.error('✗ ' + msg);
  process.exit(1);
}

async function call(method, p, body, token = TOKEN) {
  const headers = {};
  if (body !== undefined) headers['content-type'] = 'application/json';
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(SERVER + p, {
    method, headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json = null;
  try { json = await res.json(); } catch { /* 非 JSON */ }
  return { status: res.status, json };
}

async function needToken() {
  if (!TOKEN) die('缺少 --token（或环境变量 CRAB_TOKEN）');
}

const USAGE = `用法：node cli/animalctl.js <命令> [选项]

命令：
  register      --code <注册口令> [--name 名字]
  upload-card   --dir <含 card.png 与 manifest.json 的目录>
  move          --dir up|down|left|right|stop
  state         [--radius 200] [--json]
  play-url
  rotate-token

通用：--server ${SERVER}  --token <token>  --animal <A-0001|me>`;

async function main() {
  if (!cmd || cmd === '-h' || cmd === '--help') {
    console.log(USAGE);
    return;
  }

  if (cmd === 'register') {
    const code = opt('code', process.env.CRAB_REGISTER_CODE);
    if (!code) die('缺少 --code（注册口令）');
    const res = await fetch(SERVER + '/api/v1/register', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-register-code': code },
      body: JSON.stringify({ name: opt('name', undefined) }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) die(`注册失败 ${res.status}: ${json.message || ''}`);
    console.log(JSON.stringify(json, null, 2));
    console.log('\n提示：把 token 存到环境变量 CRAB_TOKEN，把 animalId 存到 CRAB_ANIMAL');
    return;
  }

  if (cmd === 'upload-card') {
    await needToken();
    const dir = opt('dir', '.');
    const png = path.join(dir, 'card.png');
    const mf = path.join(dir, 'manifest.json');
    if (!fs.existsSync(png)) die(`找不到 ${png}`);
    if (!fs.existsSync(mf)) die(`找不到 ${mf}`);
    const manifest = JSON.parse(fs.readFileSync(mf, 'utf8'));
    const pngBase64 = 'data:image/png;base64,' + fs.readFileSync(png).toString('base64');
    const r = await call('POST', `/api/v1/animals/${ANIMAL}/card`, { pngBase64, manifest });
    if (r.status !== 200) {
      console.error(`✗ 上传被拒绝（${r.status}）`);
      for (const e of (r.json && r.json.errors) || [r.json && r.json.message]) console.error('  - ' + e);
      process.exit(1);
    }
    console.log(JSON.stringify(r.json, null, 2));
    return;
  }

  if (cmd === 'move') {
    await needToken();
    const d = opt('dir');
    if (!d) die('缺少 --dir up|down|left|right|stop');
    const dir = d === 'stop' ? null : d;
    if (dir !== null && !['up', 'down', 'left', 'right'].includes(dir)) die(`非法方向：${d}`);
    const r = await call('POST', `/api/v1/animals/${ANIMAL}/intent`, { dir });
    if (r.status !== 200) die(`设置意图失败 ${r.status}: ${r.json && r.json.message}`);
    const s = r.json.state.self;
    console.log(`${s.id} → ${dir || 'stop'}  位置 (${s.x}, ${s.y}) 朝向 ${s.facing}`);
    return;
  }

  if (cmd === 'state') {
    await needToken();
    const radius = opt('radius');
    const q = radius ? `?radius=${encodeURIComponent(radius)}` : '';
    const r = await call('GET', `/api/v1/animals/${ANIMAL}/state${q}`);
    if (r.status !== 200) die(`读取状态失败 ${r.status}: ${r.json && r.json.message}`);
    if (flag('json')) { console.log(JSON.stringify(r.json, null, 2)); return; }
    const { self, nearby, world } = r.json;
    console.log(`自己   ${self.id} ${self.name} (${self.x}, ${self.y}) 朝向 ${self.facing} moving=${self.moving}`);
    console.log(`卡片   ${self.card ? `${self.card.width}×${self.card.height} ${self.card.digest.slice(0, 12)}…` : '（未上传）'}`);
    console.log(`附近   ${nearby.length} 只（半径 ${world.radius}，在线 ${world.online}）`);
    for (const n of nearby) console.log(`       - ${n.id} ${n.name} (${n.x}, ${n.y}) ${n.facing} ${n.distance}px`);
    return;
  }

  if (cmd === 'play-url') {
    await needToken();
    console.log(`${SERVER}/play?t=${encodeURIComponent(TOKEN)}`);
    return;
  }

  if (cmd === 'rotate-token') {
    await needToken();
    const r = await call('POST', `/api/v1/animals/${ANIMAL}/rotate-token`, {});
    if (r.status !== 200) die(`轮换失败 ${r.status}`);
    console.log(JSON.stringify(r.json, null, 2));
    console.log('\n旧 token 已失效，记得更新 CRAB_TOKEN 与给用户的链接');
    return;
  }

  die(`未知命令：${cmd}\n\n${USAGE}`);
}

main().catch((e) => die(e.message));
