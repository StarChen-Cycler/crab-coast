'use strict';
/* WebSocket 广播（REQ-000011）：/ws?t=<token>，10Hz 推送各自的快照。 */

const { WebSocketServer } = require('ws');
const C = require('../shared/const');

function createWsHub({ world, cfg, server, log = console }) {
  const wss = new WebSocketServer({ noServer: true });
  const clients = new Set();

  server.on('upgrade', (req, socket, head) => {
    let u;
    try { u = new URL(req.url, 'http://localhost'); } catch { socket.destroy(); return; }
    if (u.pathname !== '/ws') { socket.destroy(); return; }
    const token = u.searchParams.get('t');
    const animal = token ? world.byToken(token) : null;
    if (!animal) {
      socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      ws.animalId = animal.id;
      clients.add(ws);
      world.markSeen(animal.id);
      log.info?.(`[ws] +${animal.id} (${clients.size})`);
      ws.on('message', (raw) => {
        let msg;
        try { msg = JSON.parse(raw.toString('utf8')); } catch { return; }
        if (msg && msg.type === 'intent') {
          try { world.setIntent(ws.animalId, msg.dir === undefined ? null : msg.dir); }
          catch { /* 非法方向忽略 */ }
        }
      });
      ws.on('close', () => {
        clients.delete(ws);
        log.info?.(`[ws] -${animal.id} (${clients.size})`);
      });
      ws.on('error', () => clients.delete(ws));
    });
  });

  // 每个连接推它自己的视角（自己 + 附近）
  const snapshotTimer = setInterval(() => {
    if (!clients.size) return;
    for (const ws of clients) {
      if (ws.readyState !== 1) continue;
      const st = world.buildState(ws.animalId, cfg.radiusDefault);
      if (!st) continue;
      ws.send(JSON.stringify({ type: 'snapshot', ...st }));
    }
  }, Math.round(1000 / C.SNAPSHOT_HZ));

  function close() {
    clearInterval(snapshotTimer);
    for (const ws of clients) { try { ws.close(); } catch { /* ignore */ } }
    clients.clear();
    wss.close();
  }

  return { close, get size() { return clients.size; } };
}

module.exports = { createWsHub };
