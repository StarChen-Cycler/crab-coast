'use strict';
/* 可行走格：直接读现有单机版的 assets/scene.json（同一份数据，避免两套真相）。
   walk 是 ROWS 个字符串，每行 COLS 个 '0'/'1'。 */

const fs = require('node:fs');
const path = require('node:path');
const { HITBOX } = require('./const');

function loadScene(scenePath) {
  const raw = fs.readFileSync(scenePath, 'utf8');
  const scene = JSON.parse(raw);
  const g = scene.grid;
  if (!g || !Array.isArray(g.walk) || g.walk.length !== g.rows) {
    throw new Error('scene.json 的 grid 结构不符合预期');
  }
  return {
    w: scene.w,
    h: scene.h,
    spawn: scene.spawn,
    speed: scene.speed,
    cell: g.cell,
    cols: g.cols,
    rows: g.rows,
    walk: g.walk,
  };
}

function createGrid(scene) {
  const { cell, cols, rows, walk } = scene;

  function walkableAt(x, y) {
    const cx = Math.floor(x / cell);
    const cy = Math.floor(y / cell);
    if (cx < 0 || cy < 0 || cx >= cols || cy >= rows) return false;
    return walk[cy][cx] === '1';
  }

  // 与单机版一致：脚底判定框的四个角都要在可行走格上
  function canStand(x, y, half = HITBOX.half, foot = HITBOX.foot) {
    return walkableAt(x - half, y - foot)
      && walkableAt(x + half, y - foot)
      && walkableAt(x - half, y)
      && walkableAt(x + half, y);
  }

  // 出生点如果不是可走的，就近螺旋搜索一个可走点（换素材时不至于把动物卡进墙里）
  function nearestWalkable(x, y) {
    if (canStand(x, y)) return { x, y };
    const step = cell;
    for (let ring = 1; ring <= 40; ring++) {
      for (let dy = -ring; dy <= ring; dy++) {
        for (let dx = -ring; dx <= ring; dx++) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== ring) continue;
          const nx = x + dx * step;
          const ny = y + dy * step;
          if (canStand(nx, ny)) return { x: nx, y: ny };
        }
      }
    }
    return { x, y };
  }

  function walkableRatio() {
    let n = 0;
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) if (walk[row][col] === '1') n++;
    }
    return n / (rows * cols);
  }

  return { walkableAt, canStand, nearestWalkable, walkableRatio, cell, cols, rows };
}

// cloud/shared/ → 上两层是仓库根；单机版的 assets/scene.json 就在那里（同一份数据，不复制）
function loadGrid(scenePath = path.join(__dirname, '..', '..', 'assets', 'scene.json')) {
  const scene = loadScene(scenePath);
  return { scene, grid: createGrid(scene) };
}

module.exports = { loadScene, createGrid, loadGrid };
