(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  await sleep(400);
  P.releaseAll(); P.setPos(505, 428);
  await sleep(250);
  P.releaseAll();
  const r = P.canvasRect();
  return JSON.stringify({ rect: r, size: P.state().size, dpr: window.devicePixelRatio });
})()