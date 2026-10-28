'use strict';
/* /api/v1 路由（REQ-000009 / 010 / 013 / 014 / 015）。 */

const fs = require('node:fs');
const path = require('node:path');
const { validateBundle } = require('../shared/card');
const C = require('../shared/const');

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store',
  });
  res.end(body);
}

function readBody(req, limit = 8 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) { reject(Object.assign(new Error('请求体过大'), { code: 'TOO_LARGE' })); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch (e) { reject(Object.assign(new Error('请求体不是合法 JSON'), { code: 'BAD_JSON' })); }
    });
    req.on('error', reject);
  });
}

function createApi({ world, cfg, store }) {
  const hits = new Map();              // ip -> number[]

  function rateLimited(ip) {
    const now = Date.now();
    const arr = (hits.get(ip) || []).filter((t) => now - t < 60_000);
    arr.push(now);
    hits.set(ip, arr);
    return arr.length > cfg.rateLimitPerMin;
  }

  function bearer(req, u) {
    const h = req.headers.authorization || '';
    const m = /^Bearer\s+(.+)$/.exec(h);
    if (m) return m[1].trim();
    return u.searchParams.get('t');
  }

  function auth(req, u) {
    const token = bearer(req, u);
    const animal = token ? world.byToken(token) : null;
    return animal;
  }

  function baseUrl(req) {
    const proto = req.headers['x-forwarded-proto'] || 'http';
    const host = req.headers.host || `127.0.0.1:${cfg.port}`;
    return `${proto}://${host}`;
  }

  async function handle(req, res, u) {
    const p = u.pathname.replace(/\/+$/, '') || '/api/v1';
    const m = (re) => re.exec(p);

    // ---- POST /api/v1/register ----
    if (p === '/api/v1/register' && req.method === 'POST') {
      const ip = req.socket.remoteAddress || 'unknown';
      if (rateLimited(ip)) return send(res, 429, { error: 'RATE_LIMITED', message: '注册过于频繁，请稍后再试' }), true;
      let body = {};
      try { body = await readBody(req); } catch (e) { return send(res, 400, { error: e.code, message: e.message }), true; }
      const code = req.headers['x-register-code'] || body.registerCode;
      if (code !== cfg.registerCode) {
        return send(res, 401, { error: 'BAD_REGISTER_CODE', message: '注册口令缺失或错误' }), true;
      }
      const { id, token } = world.register({ name: body.name });
      const playUrl = `${baseUrl(req)}/play?t=${encodeURIComponent(token)}`;
      return send(res, 200, { animalId: id, token, playUrl, tokenLength: token.length }), true;
    }

    // ---- GET /api/v1/world ----
    if (p === '/api/v1/world' && req.method === 'GET') {
      return send(res, 200, {
        w: C.WORLD.w, h: C.WORLD.h,
        online: world.onlineCount(),
        radius: cfg.radiusDefault,
        radiusMax: cfg.radiusMax,
        speed: C.SPEED,
        card: C.CARD,
      }), true;
    }

    // ---- GET /healthz ----
    if (p === '/healthz' && req.method === 'GET') {
      return send(res, 200, { ok: true, online: world.onlineCount(), version: cfg.version }), true;
    }

    // ---- /api/v1/animals/:id/... ----
    const am = m(/^\/api\/v1\/animals\/([^/]+)(\/[a-z-]+)?$/);
    if (am) {
      let id = decodeURIComponent(am[1]);
      const sub = am[2] || '';
      const animal = auth(req, u);
      if (!animal) return send(res, 401, { error: 'UNAUTHORIZED', message: 'token 缺失或无效' }), true;
      // 前端只拿得到 token（play?t=…），允许用 me 表示"token 绑定的那只"
      if (id === 'me') id = animal.id;
      if (animal.id !== id) {
        return send(res, 403, { error: 'FORBIDDEN', message: 'token 不属于这只动物' }), true;
      }
      world.markSeen(id);

      if (sub === '/state' && req.method === 'GET') {
        return send(res, 200, world.buildState(id, u.searchParams.get('radius'))), true;
      }

      if (sub === '/card-status' && req.method === 'GET') {
        const a = world.animals.get(id);
        return send(res, 200, {
          animalId: id,
          hasCard: !!a.card,
          card: a.card ? { width: a.card.width, height: a.card.height, digest: a.card.digest, url: `/cards/${id}.png` } : null,
        }), true;
      }

      if (sub === '/intent' && req.method === 'POST') {
        let body = {};
        try { body = await readBody(req, 64 * 1024); } catch (e) { return send(res, 400, { error: e.code, message: e.message }), true; }
        try {
          world.setIntent(id, body.dir === undefined ? null : body.dir);
        } catch (e) {
          return send(res, 400, { error: 'BAD_DIR', message: 'dir 只能是 up/down/left/right 或 null' }), true;
        }
        return send(res, 200, { ok: true, state: world.buildState(id) }), true;
      }

      if (sub === '/rotate-token' && req.method === 'POST') {
        const token = world.rotateToken(id);
        return send(res, 200, { animalId: id, token, tokenLength: token.length }), true;
      }

      if (sub === '/card' && req.method === 'POST') {
        let body;
        try { body = await readBody(req); } catch (e) { return send(res, 400, { error: e.code, message: e.message }), true; }
        if (!body.pngBase64 || !body.manifest) {
          return send(res, 400, { error: 'BAD_UPLOAD', message: '需要 pngBase64 与 manifest 两个字段' }), true;
        }
        const buf = Buffer.from(String(body.pngBase64).replace(/^data:image\/png;base64,/, ''), 'base64');
        const result = validateBundle(buf, body.manifest);
        if (!result.ok) {
          return send(res, 400, { error: 'INVALID_CARD', errors: result.errors }), true;
        }
        const file = path.join(cfg.cardDir, `${id}.png`);
        fs.writeFileSync(file, buf);
        const card = world.attachCard(id, {
          path: file, digest: result.digest,
          width: result.size.width, height: result.size.height,
        });
        return send(res, 200, {
          ok: true, animalId: id,
          card: { width: card.width, height: card.height, digest: card.digest, url: `/cards/${id}.png` },
        }), true;
      }

      return send(res, 404, { error: 'NOT_FOUND', message: `未知子路径 ${sub}` }), true;
    }

    if (p.startsWith('/api/')) {
      return send(res, 404, { error: 'NOT_FOUND', message: `未知接口 ${p}` }), true;
    }
    return false;
  }

  return { handle };
}

module.exports = { createApi, send };
