(async () => {
  const P = window.__probe;
  window.dispatchEvent(new Event('resize'));
  await new Promise(r => setTimeout(r, 120));
  const band = getComputedStyle(document.documentElement).getPropertyValue('--touch-band').trim();
  return JSON.stringify({
    band: band || '(unset)',
    stageBottom: getComputedStyle(document.getElementById('stage')).bottom,
    canvas: P.canvasRect(), viewport: [innerWidth, innerHeight],
    hud: getComputedStyle(document.querySelector('.hud')).display,
    touchUi: !!window.__touch
  });
})()