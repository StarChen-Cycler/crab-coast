'use strict';
/* 服务入口（REQ-000015）：单进程同时提供
     - 静态：仓库根的本地单机版（index.html 等）
     - 静态：cloud/play 的多人前端
     - /cards/*：上传的动作卡
     - /api/v1/*：REST
     - /ws：WebSocket
   端口/数据目录/注册口令等全部来自环境变量。 */

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { loadConfig, ensureDataDir } = require('./config');
const { Store } = require('./store');
const { World } = require('./world');
const { createApi, send } = require('./api');
const { createWsHub } = require('./ws');
const { loadGrid } = require('../shared/grid');
const C = require('../shared/const');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
};

function serveFile(res, file) {
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, { error: 'NOT_FOUND', message: '文件不存在' });
    res.writeHead(200, {
      'content-type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'content-length': buf.length,
      'cache-control': 'no-cache',
    });
    res.end(buf);
  });
}

/** 把 URL 路径映射到磁盘文件，并阻止越权穿越。 */
function resolveStatic(cfg, pathname) {
  const rel = decodeURIComponent(pathname);
  if (rel === '/' || rel === '/play' || rel === '/play/') {
    return rel.startsWith('/play')
      ? path.join(cfg.appRoot, 'play', 'index.html')
      : path.join(cfg.repoRoot, 'index.html');
  }
  if (rel.startsWith('/cards/')) {
    const f = path.join(cfg.cardDir, path.basename(rel));
    return f.startsWith(cfg.cardDir) ? f : null;
  }
  if (rel.startsWith('/play/')) {
    const f = path.join(cfg.appRoot, rel);
    return f.startsWith(path.join(cfg.appRoot, 'play')) ? f : null;
  }
  const f = path.join(cfg.repoRoot, rel);
  const allowed = ['/assets/', '/music/', '/docs/', '/evidence/'];
  if (allowed.some((p) => rel.startsWith(p))) {
    return f.startsWith(cfg.repoRoot) ? f : null;
  }
  // 根目录下的单机版散文件（main.js / touch-controls.js / README.md 等）
  if (/^\/[A-Za-z0-9._-]+$/.test(rel)) {
    return f.startsWith(cfg.repoRoot) ? f : null;
  }
  return null;
}

function main() {
  const cfg = loadConfig();
  if (cfg.problems.length) {
    console.error('配置有误：\n  - ' + cfg.problems.join('\n  - '));
    process.exit(2);
  }
  try {
    ensureDataDir(cfg);
  } catch (e) {
    console.error(`启动失败：${e.message}`);
    process.exit(1);
  }

  const store = new Store(cfg.dbPath);
  const { scene, grid } = loadGrid();
  const world = new World({
    store, grid, scene,
    radiusDefault: cfg.radiusDefault, radiusMax: cfg.radiusMax,
  }).load();
  const api = createApi({ world, cfg, store });

  const server = http.createServer(async (req, res) => {
    let u;
    try { u = new URL(req.url, `http://${req.headers.host || 'localhost'}`); }
    catch { return send(res, 400, { error: 'BAD_URL' }); }

    // API 优先（/api/* 与 /healthz）
    if (u.pathname.startsWith('/api/') || u.pathname === '/healthz') {
      try {
        const handled = await api.handle(req, res, u);
        if (handled) return;
      } catch (e) {
        return send(res, 500, { error: 'INTERNAL', message: e.message });
      }
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      return send(res, 405, { error: 'METHOD_NOT_ALLOWED' });
    }

    const file = resolveStatic(cfg, u.pathname);
    if (!file) return send(res, 404, { error: 'NOT_FOUND', message: `没有这个路径：${u.pathname}` });
    return serveFile(res, file);
  });

  const hub = createWsHub({ world, cfg, server });

  // 20Hz 推进世界（REQ-000008）
  const tickMs = Math.round(1000 / C.TICK_HZ);
  let last = Date.now();
  const tickTimer = setInterval(() => {
    const now = Date.now();
    const dt = Math.min(now - last, 200);
    last = now;
    world.tick(dt);
  }, tickMs);

  server.on('error', (e) => {
    if (e.code === 'EADDRINUSE') {
      console.error(`启动失败：端口 ${cfg.port} 已被占用`);
    } else {
      console.error(`启动失败：${e.code || e.message}`);
    }
    process.exit(1);
  });

  server.listen(cfg.port, () => {
    console.log(`crab-coast cloud v${cfg.version}`);
    console.log(`  监听:      http://127.0.0.1:${cfg.port}`);
    console.log(`  单机版:    /            （来自 ${cfg.repoRoot}）`);
    console.log(`  多人前端:  /play?t=…    （来自 ${path.join(cfg.appRoot, 'play')}）`);
    console.log(`  数据目录:  ${cfg.dataDir}`);
    if (cfg.usingDefaultCode) {
      console.warn('  ⚠ 未设置 REGISTER_CODE，正在使用默认口令 dev-code —— 上生产前务必显式设置');
    }
  });

  const shutdown = () => {
    clearInterval(tickTimer);
    hub.close();
    try { world.persist(); } catch { /* ignore */ }
    try { store.close(); } catch { /* ignore */ }
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 800);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

if (require.main === module) main();

module.exports = { main, resolveStatic };
