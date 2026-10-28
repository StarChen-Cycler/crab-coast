(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  await sleep(1200);
  const P = window.__probe;
  const s = P ? P.state() : null;
  return JSON.stringify({
    title: document.title,
    ready: P ? P.ready : null,
    assets: P ? P.assetsLoaded() : null,
    frame: window.SCENE ? window.SCENE.frame.w : null,
    size: s ? s.size : null,
    bgm: window.__bgm ? { duration: Math.round(window.__bgm.audio.duration), loop: window.__bgm.audio.loop } : null,
    canvas: P ? P.canvasRect() : null
  });
})()