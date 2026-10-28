(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const a = window.__bgm.audio;
  const t0 = a.currentTime;
  await sleep(1500);
  const t1 = a.currentTime;
  return JSON.stringify({ paused: a.paused, t0: +t0.toFixed(2), t1: +t1.toFixed(2), advanced: +(t1 - t0).toFixed(2), volume: +a.volume.toFixed(2) });
})()