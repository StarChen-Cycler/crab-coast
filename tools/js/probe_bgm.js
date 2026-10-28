(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  await sleep(1500);
  const b = window.__bgm;
  if (!b) return JSON.stringify({ error: 'no __bgm' });
  const a = b.audio;
  if (a.readyState < 1) await new Promise(res => { a.addEventListener('loadedmetadata', res, { once: true }); setTimeout(res, 3000); });
  return JSON.stringify({
    src: a.src.split('/').pop(),
    duration: +a.duration.toFixed(2),
    loop: a.loop,
    readyState: a.readyState,
    muted: b.muted,
    started: b.started,
    button: !!document.getElementById('bgm-btn'),
  });
})()