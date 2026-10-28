(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const els = [...document.querySelectorAll('span,div,p,button')];
  const target = els
    .filter(e => (e.textContent || '').includes('seaside_bgm') && (e.textContent || '').includes('打开文件'))
    .map(e => ({ e, r: e.getBoundingClientRect() }))
    .filter(x => x.r.width > 40)
    .sort((a, b) => a.r.width * a.r.height - b.r.width * b.r.height)[0];
  if (!target) return 'NOT_FOUND';
  target.e.scrollIntoView({ block: 'center' });
  await sleep(600);
  const r = target.e.getBoundingClientRect();
  return JSON.stringify({ x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width) });
})()