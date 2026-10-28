(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // 预热：确保 rAF 未被后台节流
  let ok = false;
  for (let i = 0; i < 20 && !ok; i++) {
    P.setPos(480, 430);
    P.releaseAll();
    await sleep(60);
    const a = P.state();
    P.press('ArrowRight');
    await sleep(200);
    P.release('ArrowRight');
    ok = P.state().x - a.x > 5;
    if (!ok) await sleep(400);
  }
  if (!ok) return JSON.stringify({ warmup: false });

  await sleep(500);
  P.resetStats();
  P.setPos(200, 500);
  P.releaseAll();
  P.press('ArrowRight');
  await sleep(4000);
  P.release('ArrowRight');

  return JSON.stringify({
    warmup: true,
    seconds: 4,
    fpsAvg: P.fps(),
    longFrames: P.longFrames(),
    longFrameDefinition: '单帧间隔 > 50ms',
    state: P.state(),
  });
})()
