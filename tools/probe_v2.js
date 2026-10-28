(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { spawn: P.state(), dirs: [] };

  for (const code of ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown']) {
    P.setPos(500, 412);
    P.releaseAll();
    await sleep(80);
    const a = P.state();
    P.press(code);
    await sleep(700);
    const mid = P.state();
    P.release(code);
    await sleep(80);
    const b = P.state();
    out.dirs.push({
      code,
      dx: +(b.x - a.x).toFixed(1),
      dy: +(b.y - a.y).toFixed(1),
      dir: mid.dir,
      frameMid: mid.frame,
      moving: mid.moving,
      stopped: !P.state().moving,
    });
  }

  // 帧序
  P.setPos(500, 412);
  P.releaseAll();
  P.log(true);
  await sleep(60);
  P.press('ArrowRight');
  await sleep(1000);
  P.release('ArrowRight');
  await sleep(100);
  const frames = P.frames();
  P.log(false);
  out.frames = {
    seq: frames.map((f) => f.idx).join(''),
    dirs: [...new Set(frames.map((f) => f.dir))],
  };
  out.fps = P.fps();
  return JSON.stringify(out);
})()
