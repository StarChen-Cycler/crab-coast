(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = [];
  const tests = [
    { name: 'up-to-sea', x: 500, y: 412, code: 'ArrowUp', ms: 4000 },
    { name: 'right-to-house', x: 500, y: 412, code: 'ArrowRight', ms: 4000 },
    { name: 'left-to-trees', x: 400, y: 412, code: 'ArrowLeft', ms: 4000 },
    { name: 'down-to-edge', x: 500, y: 412, code: 'ArrowDown', ms: 4000 },
  ];
  for (const t of tests) {
    P.setPos(t.x, t.y); P.releaseAll(); await sleep(80);
    P.press(t.code); await sleep(t.ms); P.release(t.code); await sleep(80);
    const s = P.state();
    out.push({ name: t.name, x: s.x, y: s.y, stands: P.canStand(s.x, s.y) });
  }
  return JSON.stringify(out);
})()