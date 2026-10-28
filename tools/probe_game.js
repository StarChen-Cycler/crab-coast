(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { checks: {} };
  const round = (v) => Math.round(v * 10) / 10;

  // 0. ready
  out.checks.ready = { assets: P.assetsLoaded(), canvas: P.canvasRect() };

  // 1. 四向位移方向
  out.checks.dirs = [];
  for (const code of ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown']) {
    P.setPos(480, 430);
    P.releaseAll();
    await sleep(80);
    const a = P.state();
    P.press(code);
    await sleep(1000);
    P.release(code);
    await sleep(80);
    const b = P.state();
    out.checks.dirs.push({
      code,
      dx: round(b.x - a.x),
      dy: round(b.y - a.y),
      dir: b.dir,
      frameAfterRelease: b.frame,
    });
  }

  // 2. 速度一致性：三次 1 秒向右
  out.checks.speed = [];
  for (let i = 0; i < 3; i++) {
    P.setPos(200, 430);
    P.releaseAll();
    await sleep(80);
    const a = P.state();
    P.press('ArrowRight');
    await sleep(1000);
    P.release('ArrowRight');
    const b = P.state();
    out.checks.speed.push(round(b.x - a.x));
    await sleep(120);
  }
  const mn = Math.min(...out.checks.speed);
  const mx = Math.max(...out.checks.speed);
  out.checks.speedSpreadPct = round(((mx - mn) / ((mx + mn) / 2)) * 100);

  // 3. 边界钳制：持续 5 秒向右
  P.setPos(700, 430);
  P.releaseAll();
  P.press('ArrowRight');
  await sleep(5000);
  P.release('ArrowRight');
  const edge = P.state();
  out.checks.boundary = { x: edge.x, limit: P.bounds.x1, within: edge.x <= P.bounds.x1 };

  // 4. 松键立即停止
  P.setPos(400, 430);
  P.releaseAll();
  await sleep(60);
  P.press('ArrowRight');
  await sleep(300);
  P.release('ArrowRight');
  const atRelease = P.state();
  await sleep(400);
  const afterStop = P.state();
  out.checks.releaseStop = {
    dxAfterRelease: round(afterStop.x - atRelease.x),
    frameFrozen: afterStop.frame === 0,
  };

  // 5. 帧序（向右 1 秒）
  P.setPos(300, 430);
  P.releaseAll();
  P.log(true);
  await sleep(60);
  P.press('ArrowRight');
  await sleep(1000);
  P.release('ArrowRight');
  await sleep(200);
  const frames = P.frames();
  P.log(false);
  out.checks.frameSeq = {
    count: frames.length,
    seq: frames.map((f) => f.idx).join(''),
    dirs: [...new Set(frames.map((f) => f.dir))],
    distinctIdx: [...new Set(frames.map((f) => f.idx))].sort(),
  };

  // 6. 切向换动作组
  P.setPos(400, 430);
  P.releaseAll();
  P.log(true);
  P.press('ArrowRight');
  await sleep(400);
  P.release('ArrowRight');
  P.press('ArrowUp');
  await sleep(400);
  P.release('ArrowUp');
  const f2 = P.frames();
  P.log(false);
  out.checks.switchDir = {
    dirsInOrder: f2.map((f) => f.dir[0]).join(''),
    dirs: [...new Set(f2.map((f) => f.dir))],
  };

  // 7. 帧率
  out.checks.fps = P.fps();
  out.checks.longFrames = P.longFrames();

  return JSON.stringify(out);
})()
