(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};

  // 单次移动测量：返回位移、耗时、归一化速度
  async function move(x, y, code, ms) {
    P.setPos(x, y);
    P.releaseAll();
    await sleep(80);
    const a = P.state();
    const t0 = performance.now();
    P.press(code);
    await sleep(ms);
    const mid = P.state();
    P.release(code);
    const dt = (performance.now() - t0) / 1000;
    await sleep(90);
    const b = P.state();
    return {
      dx: +(b.x - a.x).toFixed(1),
      dy: +(b.y - a.y).toFixed(1),
      dt: +dt.toFixed(2),
      vx: +((b.x - a.x) / dt).toFixed(1),
      vy: +((b.y - a.y) / dt).toFixed(1),
      dirMid: mid.dir,
      frameMid: mid.frame,
      stopped: !b.moving && b.frame === 0,
    };
  }

  // 每个方向最多试 4 次，取位移最大的那次（避开浏览器节流导致的偏小值）
  const best = async (code, ms, tries = 4) => {
    let bestRun = null;
    for (let i = 0; i < tries; i++) {
      const r = await move(500, 412, code, ms);
      if (!bestRun || Math.abs(r.dx) + Math.abs(r.dy) > Math.abs(bestRun.dx) + Math.abs(bestRun.dy)) {
        bestRun = r;
      }
      if (Math.abs(bestRun.vx) + Math.abs(bestRun.vy) > 105) break;
      await sleep(150);
    }
    return bestRun;
  };

  out.dirs = [];
  for (const code of ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown']) {
    const r = await best(code, 700);
    out.dirs.push({ code, ...r });
  }

  // 速度一致性：三次 1 秒向右，取归一化速度
  const speeds = [];
  for (let i = 0; i < 3; i++) {
    let r = null;
    for (let k = 0; k < 3; k++) {
      const c = await move(500, 412, 'ArrowRight', 1000);
      if (!r || Math.abs(c.vx) > Math.abs(r.vx)) r = c;
      if (Math.abs(r.vx) > 105) break;
      await sleep(150);
    }
    speeds.push(r.vx);
  }
  const mn = Math.min(...speeds), mx = Math.max(...speeds);
  out.speeds = speeds;
  out.speedSpreadPct = +(((mx - mn) / ((mx + mn) / 2)) * 100).toFixed(2);

  // 帧序
  P.setPos(500, 412); P.releaseAll(); P.log(true); await sleep(60);
  P.press('ArrowRight'); await sleep(1000); P.release('ArrowRight'); await sleep(150);
  const f1 = P.frames(); P.log(false);
  out.frameSeq = { seq: f1.map((f) => f.idx).join(''), count: f1.length,
                   dirs: [...new Set(f1.map((f) => f.dir))] };

  // 切向换组
  P.setPos(500, 412); P.releaseAll(); P.log(true);
  P.press('ArrowRight'); await sleep(400); P.release('ArrowRight');
  P.press('ArrowUp'); await sleep(400); P.release('ArrowUp'); await sleep(150);
  const f2 = P.frames(); P.log(false);
  out.switchDir = { order: f2.map((f) => f.dir[0]).join(''),
                    dirs: [...new Set(f2.map((f) => f.dir))] };

  // 碰撞：朝海/礁石/树/下边界走，最终必须仍站在可走沙地
  out.collide = [];
  for (const t of [
    { name: 'up-to-sea', code: 'ArrowUp' },
    { name: 'right-to-rock', code: 'ArrowRight' },
    { name: 'left-to-trees', code: 'ArrowLeft' },
    { name: 'down-to-edge', code: 'ArrowDown' },
  ]) {
    const r = await move(500, 412, t.code, 3500);
    out.collide.push({ name: t.name, x: 500 + r.dx, y: 412 + r.dy,
                       stands: P.canStand(500 + r.dx, 412 + r.dy) });
  }

  out.fps = P.fps();
  out.longFrames = P.longFrames();
  out.grid = P.grid;
  return JSON.stringify(out);
})()
