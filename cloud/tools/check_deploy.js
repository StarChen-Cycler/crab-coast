'use strict';
/* 部署后断言：健康检查 + 静态资源指纹 + 音频 Range（REQ-000022 上线验证）。
 *
 * 用法：node tools/check_deploy.js [baseUrl]     默认 http://127.0.0.1:8090
 * 退出码 0 = 全部通过。只读，不写任何东西。
 */

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const BASE = (process.argv[2] || 'http://127.0.0.1:8090').replace(/\/+$/, '');
const REPO = path.join(__dirname, '..', '..');
// 需要指纹核对的资源：URL → 本地文件
const FILES = [
  ['/play/bgm.js', path.join(__dirname, '..', 'play', 'bgm.js')],
  ['/play/play.js', path.join(__dirname, '..', 'play', 'play.js')],
  ['/play/touch.js', path.join(__dirname, '..', 'play', 'touch.js')],
  ['/play/index.html', path.join(__dirname, '..', 'play', 'index.html')],
  ['/music/seaside_lazy_loop_40s.wav', path.join(REPO, 'music', 'seaside_lazy_loop_40s.wav')],
];

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const results = [];
function check(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

async function main() {
  // 1) 健康检查
  const hz = await fetch(BASE + '/healthz');
  const hzBody = await hz.json().catch(() => null);
  check('/healthz 200 且 ok', hz.status === 200 && hzBody && hzBody.ok === true, { status: hz.status, body: hzBody });

  // 2) 静态资源指纹（served bytes === 本地 bytes）
  for (const [url, local] of FILES) {
    const disk = fs.readFileSync(local);
    const res = await fetch(BASE + url);
    const buf = Buffer.from(await res.arrayBuffer());
    check(`${url} 指纹一致`, res.status === 200 && sha(buf) === sha(disk),
      { status: res.status, bytes: buf.length, diskBytes: disk.length, sha: sha(disk).slice(0, 12) });
  }

  // 3) 音频 Range：200 / 206 / 416
  const wav = path.join(REPO, 'music', 'seaside_lazy_loop_40s.wav');
  const size = fs.statSync(wav).size;
  const full = await fetch(BASE + '/music/seaside_lazy_loop_40s.wav');
  const fullBuf = Buffer.from(await full.arrayBuffer());
  check('音频整文件 200 + accept-ranges + content-length',
    full.status === 200 && full.headers.get('accept-ranges') === 'bytes'
    && Number(full.headers.get('content-length')) === size && fullBuf.length === size
    && sha(fullBuf) === sha(fs.readFileSync(wav)),
    { status: full.status, contentLength: Number(full.headers.get('content-length')), size });

  const part = await fetch(BASE + '/music/seaside_lazy_loop_40s.wav', { headers: { Range: 'bytes=0-1023' } });
  const partBuf = Buffer.from(await part.arrayBuffer());
  check('音频 Range 206 + content-range + 1024 字节',
    part.status === 206 && part.headers.get('content-range') === `bytes 0-1023/${size}` && partBuf.length === 1024,
    { status: part.status, contentRange: part.headers.get('content-range'), bytes: partBuf.length });

  const bad = await fetch(BASE + '/music/seaside_lazy_loop_40s.wav', { headers: { Range: 'bytes=99999999-' } });
  check('音频 Range 越界 416 + content-range',
    bad.status === 416 && bad.headers.get('content-range') === `bytes */${size}`,
    { status: bad.status, contentRange: bad.headers.get('content-range') });

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} 通过（${BASE}）`);
  if (failed.length) process.exitCode = 1;
}

main().catch((e) => { console.error('断言异常：', e); process.exit(1); });
