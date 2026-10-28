(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 25 && !(window.__probe && window.__probe.ready); i++) await sleep(150);
  return JSON.stringify({
    mounted: !!window.__touch,
    sizeBtn: (() => { const e = document.getElementById('size-btn'); return e ? { d: getComputedStyle(e).display, text: e.textContent } : null; })(),
    toggleExists: !!document.getElementById('touch-toggle'),
    hud: getComputedStyle(document.querySelector('.hud')).display,
    canvas: window.__probe.canvasRect(),
  });
})()