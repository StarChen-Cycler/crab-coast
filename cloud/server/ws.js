'use strict';
/* WebSocket 广播（REQ-000011）与多会话控制（REQ-000016）。

每只动物最多同时 2 个活跃会话：第 3 个连接到来时接受新的、关闭最早建立的（FIFO），
被淘汰方收到 1008 + 'replaced by newer session'，前端据此不再自动重连。
*/

const { WebSocketServer } = require('ws');
const C = require('../shared/const');

const REPLACED = 'replaced by newer session';

function createWsHub({ world, cfg, server, log = console }) {
  const wss = new WebSocketServer({ noServer: true });
  const sessions = new Map();     // animalId -> [{ ws, sid, at }]，按建立时间升序
  let seq = 0;

  function listFor(id) {
    if (!sessions.has(id)) sessions.set(id, []);
    return sessions.get(id);
  }

  function detach(id, sess) {
    const list = sessions.get(id);
    if (!list) return;
    const i = list.indexOf(sess);
    if (i >= 0) list.splice(i, 1);
  }

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
    // 浏览器一律拿全世界（REQ-000021）：单世界动物数量有限，按距离裁切只会让「走远的角色凭空消失」。
    // 半径语义只留给 Agent 的 /state（REQ-000014），所以这里不再解析 r= 参数。

    wss.handleUpgrade(req, socket, head, (ws) => {
      const list = listFor(animal.id);
      const sess = { ws, sid: ++seq, at: Date.now() };
      ws.animalId = animal.id;
      ws.sid = sess.sid;
      ws.sourceKey = `ws:${sess.sid}`;          // 每个会话是一个独立来源
      list.push(sess);
      world.markSeen(animal.id);

      // FIFO：超出上限就关掉最早建立的那个
      while (list.length > C.MAX_SESSIONS) {
        const oldest = list.shift();
        try { oldest.ws.close(1008, REPLACED); } catch { /* ignore */ }
        log.info?.(`[ws] evict ${animal.id}#${oldest.sid}（被 #${sess.sid} 取代）`);
      }
      log.info?.(`[ws] +${animal.id}#${sess.sid} (${list.length}/${C.MAX_SESSIONS})`);

      ws.on('message', (raw) => {
        let msg;
        try { msg = JSON.parse(raw.toString('utf8')); } catch { return; }
        if (msg && msg.type === 'intent') {
          try { world.setIntent(ws.animalId, msg.dir === undefined ? null : msg.dir, ws.sourceKey); }
          catch { /* 非法方向忽略 */ }
        }
      });
      ws.on('close', () => {
        detach(animal.id, sess);
        log.info?.(`[ws] -${animal.id}#${sess.sid} (${listFor(animal.id).length}/${C.MAX_SESSIONS})`);
      });
      ws.on('error', () => detach(animal.id, sess));
    });
  });

  // 每 100ms 推一次全量快照；t 是服务端发出时刻，供前端做插值计时（REQ-000020）
  const snapshotTimer = setInterval(() => {
    for (const list of sessions.values()) {
      for (const sess of list) {
        const ws = sess.ws;
        if (ws.readyState !== 1) continue;
        const st = world.buildState(ws.animalId, null, { scope: 'all' });
        if (!st) continue;
        ws.send(JSON.stringify({ type: 'snapshot', t: Date.now(), ...st }));
      }
    }
  }, Math.round(1000 / C.SNAPSHOT_HZ));

  function close() {
    clearInterval(snapshotTimer);
    for (const list of sessions.values()) {
      for (const sess of list) { try { sess.ws.close(); } catch { /* ignore */ } }
    }
    sessions.clear();
    wss.close();
  }

  return {
    close,
    get size() {
      let n = 0;
      for (const list of sessions.values()) n += list.length;
      return n;
    },
  };
}

module.exports = { createWsHub, REPLACED };
