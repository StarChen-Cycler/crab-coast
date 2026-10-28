'use strict';
/* 落盘层：node:sqlite（Node 22 内置）。换 Postgres 时只改这个文件。 */

const { DatabaseSync } = require('node:sqlite');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS animals (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,
  card_path     TEXT,
  card_digest   TEXT,
  card_w        INTEGER,
  card_h        INTEGER,
  x             REAL NOT NULL,
  y             REAL NOT NULL,
  facing        TEXT NOT NULL DEFAULT 'down',
  intent_dir    TEXT,
  intent_at     INTEGER,
  world_id      TEXT NOT NULL DEFAULT 'w1',
  created_at    INTEGER NOT NULL,
  token_rotated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_animals_world ON animals(world_id);
`;

class Store {
  constructor(dbPath) {
    this.db = new DatabaseSync(dbPath);
    this.db.exec(SCHEMA);
    this.q = {
      insert: this.db.prepare(`INSERT INTO animals
        (id,name,token_hash,x,y,facing,intent_dir,intent_at,world_id,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)`),
      byId: this.db.prepare('SELECT * FROM animals WHERE id = ?'),
      byToken: this.db.prepare('SELECT * FROM animals WHERE token_hash = ?'),
      all: this.db.prepare('SELECT * FROM animals WHERE world_id = ?'),
      count: this.db.prepare('SELECT COUNT(*) AS n FROM animals'),
      setPos: this.db.prepare('UPDATE animals SET x=?, y=?, facing=?, intent_dir=?, intent_at=? WHERE id=?'),
      setCard: this.db.prepare('UPDATE animals SET card_path=?, card_digest=?, card_w=?, card_h=? WHERE id=?'),
      setToken: this.db.prepare('UPDATE animals SET token_hash=?, token_rotated_at=? WHERE id=?'),
    };
  }

  nextId() {
    const n = this.q.count.get().n + 1;
    return `A-${String(n).padStart(4, '0')}`;
  }

  createAnimal({ id, name, tokenHash, x, y, facing = 'down' }) {
    const now = Date.now();
    this.q.insert.run(id, name, tokenHash, x, y, facing, null, null, 'w1', now);
    return this.byId(id);
  }

  byId(id) { return this.q.byId.get(id) || null; }
  byTokenHash(h) { return this.q.byToken.get(h) || null; }
  all() { return this.q.all.all('w1'); }

  savePosition(id, { x, y, facing, intentDir, intentAt }) {
    this.q.setPos.run(x, y, facing, intentDir ?? null, intentAt ?? null, id);
  }

  saveCard(id, { path, digest, w, h }) {
    this.q.setCard.run(path, digest, w, h, id);
  }

  saveTokenHash(id, hash) {
    this.q.setToken.run(hash, Date.now(), id);
  }

  close() { this.db.close(); }
}

module.exports = { Store };
