'use strict';
/* 权威世界（REQ-000008 / REQ-000014）：
   位置只由这里的 tick 推进；客户端与 Agent 只能设置意图。
   buildState 同时给 REST 与 WebSocket 用，保证两条路径字段一致。 */

const crypto = require('node:crypto');
const C = require('../shared/const');

const BASE32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'; // Crockford
const ONLINE_TTL_MS = 30_000;

function newToken(len = 40) {
  const buf = crypto.randomBytes(len);
  let out = '';
  for (let i = 0; i < len; i++) out += BASE32[buf[i] & 31];
  return out;
}

function hashToken(token) {
  return crypto.createHash('sha256').update(token).digest('hex');
}

class World {
  constructor({ store, grid, scene, persistMs = 1000, radiusDefault = 200, radiusMax = 400 }) {
    this.store = store;
    this.grid = grid;
    this.scene = scene;
    this.animals = new Map();
    this.seenAt = new Map();
    this.dirty = new Set();
    this.persistMs = persistMs;
    this.radiusDefault = radiusDefault;   // 附近半径默认值（REQ-000014）
    this.radiusMax = radiusMax;           // 半径上限，超出被钳制
    this.lastPersist = 0;
  }

  /** 从库里恢复（重启后位置不丢）。 */
  load() {
    for (const row of this.store.all()) {
      this.animals.set(row.id, {
        id: row.id,
        name: row.name,
        x: row.x,
        y: row.y,
        facing: row.facing || 'down',
        intentDir: null,          // 意图不跨进程恢复
        intentAt: null,
        moving: false,
        card: row.card_path
          ? { width: row.card_w, height: row.card_h, digest: row.card_digest, path: row.card_path }
          : null,
      });
    }
    return this;
  }

  spawnPoint() {
    const p = this.scene.spawn || { x: 470, y: 424 };
    return this.grid.nearestWalkable(p.x, p.y);
  }

  register({ name }) {
    const id = this.store.nextId();
    const token = newToken();
    const spawn = this.spawnPoint();
    const row = this.store.createAnimal({
      id, name: name || id, tokenHash: hashToken(token),
      x: spawn.x, y: spawn.y, facing: 'down',
    });
    this.animals.set(id, {
      id, name: row.name, x: row.x, y: row.y, facing: 'down',
      intentDir: null, intentAt: null, moving: false, card: null,
    });
    return { id, token, x: spawn.x, y: spawn.y };
  }

  byToken(token) {
    if (!token || typeof token !== 'string') return null;
    const row = this.store.byTokenHash(hashToken(token));
    return row ? this.animals.get(row.id) || null : null;
  }

  rotateToken(id) {
    const token = newToken();
    this.store.saveTokenHash(id, hashToken(token));
    return token;
  }

  attachCard(id, { path, digest, width, height }) {
    const a = this.animals.get(id);
    if (!a) return null;
    a.card = { path, digest, width, height };
    this.store.saveCard(id, { path, digest, w: width, h: height });
    return a.card;
  }

  markSeen(id) {
    if (id) this.seenAt.set(id, Date.now());
  }

  setIntent(id, dir) {
    const a = this.animals.get(id);
    if (!a) return null;
    if (dir === null || dir === undefined) {
      a.intentDir = null;
      a.intentAt = null;
      a.moving = false;
    } else {
      if (!C.DIR_VEC[dir]) throw Object.assign(new Error(`非法方向：${dir}`), { code: 'BAD_DIR' });
      a.intentDir = dir;
      a.intentAt = Date.now();
      a.facing = dir;                 // 四向固定朝向：意图即朝向
    }
    this.markSeen(id);
    this.dirty.add(id);
    return a;
  }

  /** 推进一个 tick；返回发生变化的动物 id 列表。 */
  tick(dtMs) {
    const now = Date.now();
    const changed = [];
    for (const a of this.animals.values()) {
      if (!a.intentDir) continue;
      if (a.intentAt != null && now - a.intentAt > C.INTENT_TTL_MS) {
        a.intentDir = null;
        a.intentAt = null;
        a.moving = false;
        changed.push(a.id);
        this.dirty.add(a.id);
        continue;
      }
      const v = C.DIR_VEC[a.intentDir];
      const step = C.SPEED * (dtMs / 1000);
      let moved = false;
      if (v.x !== 0) {
        const nx = a.x + v.x * step;
        if (this.grid.canStand(nx, a.y)) { a.x = nx; moved = true; }
      }
      if (v.y !== 0) {
        const ny = a.y + v.y * step;
        if (this.grid.canStand(a.x, ny)) { a.y = ny; moved = true; }
      }
      a.facing = a.intentDir;
      a.moving = moved;
      if (moved) {
        changed.push(a.id);
        this.dirty.add(a.id);
      }
    }
    if (now - this.lastPersist >= this.persistMs && this.dirty.size) this.persist();
    return changed;
  }

  persist() {
    for (const id of this.dirty) {
      const a = this.animals.get(id);
      if (!a) continue;
      this.store.savePosition(id, {
        x: a.x, y: a.y, facing: a.facing,
        intentDir: a.intentDir, intentAt: a.intentAt,
      });
    }
    this.dirty.clear();
    this.lastPersist = Date.now();
  }

  onlineCount() {
    const now = Date.now();
    let n = 0;
    for (const [id, t] of this.seenAt) {
      if (now - t <= ONLINE_TTL_MS && this.animals.has(id)) n++;
    }
    return n;
  }

  clampRadius(radius) {
    const r = Number(radius);
    if (!Number.isFinite(r) || r <= 0) return this.radiusDefault;
    return Math.min(r, this.radiusMax);
  }

  /** REST 与 WS 共用的状态构造（REQ-000014）。 */
  buildState(id, radiusInput) {
    const a = this.animals.get(id);
    if (!a) return null;
    const radius = this.clampRadius(radiusInput);
    const nearby = [];
    for (const o of this.animals.values()) {
      if (o.id === id) continue;
      const d = Math.hypot(o.x - a.x, o.y - a.y);
      if (d <= radius) nearby.push({ o, d });
    }
    nearby.sort((p, q) => p.d - q.d);
    return {
      self: {
        id: a.id,
        name: a.name,
        x: Math.round(a.x),
        y: Math.round(a.y),
        facing: a.facing,
        moving: !!a.moving,
        card: a.card
          ? { width: a.card.width, height: a.card.height, digest: a.card.digest }
          : null,
      },
      nearby: nearby.map(({ o, d }) => ({
        id: o.id, name: o.name,
        x: Math.round(o.x), y: Math.round(o.y),
        facing: o.facing, distance: Math.round(d),
      })),
      world: {
        w: C.WORLD.w, h: C.WORLD.h,
        online: this.onlineCount(),
        radius,
      },
    };
  }
}

module.exports = { World, newToken, hashToken, ONLINE_TTL_MS };
