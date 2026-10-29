'use strict';
/* 服务端与 CLI 共用的常量。浏览器端不 require 这个文件，
   而是启动时 GET /api/v1/world 拿运行时配置（见 play/play.js）。 */

const WORLD = { w: 960, h: 540 };

module.exports = {
  WORLD,

  // 与单机版保持一致
  SPEED: 110,               // px/s
  ANIM_FPS: 8,
  TICK_HZ: 20,              // 服务端推进频率
  SNAPSHOT_HZ: 10,          // 浏览器广播频率
  NEARBY_RADIUS: 200,       // 「附近」半径（逻辑像素）
  INTENT_TTL_MS: 3000,      // 超过这么久没新意图就停车（防止一直飘）
  MAX_SESSIONS: 2,          // 每只动物最多同时两个活跃 WebSocket 会话（FIFO 淘汰最早）
  KEEPALIVE_MS: 1000,       // 客户端按住期间每 1 秒续期一次

  // 角色脚底判定框（与单机版一致）
  HITBOX: { half: 11, foot: 6 },

  DIRECTIONS: ['down', 'left', 'right', 'up'],
  DIR_VEC: {
    up: { x: 0, y: -1 },
    down: { x: 0, y: 1 },
    left: { x: -1, y: 0 },
    right: { x: 1, y: 0 },
  },

  // 动作卡规格（沿用现有素材）
  CARD: {
    frame: 48,
    cols: 4,
    rows: 4,
    rowOrder: ['down', 'left', 'right', 'up'],
    footLine: 43,
    fps: 8,
  },
};
