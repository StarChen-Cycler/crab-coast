(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const P = window.__probe;
  const base = document.getElementById('stick-base');
  const r = base.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const ev = (type, x, y) => base.dispatchEvent(new PointerEvent(type, {
    bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 7, pointerType: 'touch', isPrimary: true
  }));

  P.releaseAll(); P.setPos(500, 412); await sleep(150);
  const out = {};

  // 摇杆向右推
  ev('pointerdown', cx, cy);
  ev('pointermove', cx + 40, cy);
  await sleep(80);
  out.dirRight = window.__input.touchDir;
  const a = P.state();
  await sleep(500);
  const b = P.state();
  out.movedRight = +(b.x - a.x).toFixed(1);

  // 向上推
  ev('pointermove', cx, cy - 40);
  await sleep(80);
  out.dirUp = window.__input.touchDir;
  const c = P.state();
  await sleep(400);
  const d = P.state();
  out.movedUp = +(d.y - c.y).toFixed(1);

  // 松手
  ev('pointerup', cx, cy);
  await sleep(150);
  out.dirAfterUp = window.__input.touchDir;
  out.movingAfterUp = P.state().moving;

  // 死区：轻微推动不应生效
  ev('pointerdown', cx, cy);
  ev('pointermove', cx + 4, cy + 3);
  await sleep(80);
  out.deadZone = window.__input.touchDir;
  ev('pointerup', cx, cy);

  // A 键：形状轮询
  const before = P.state().size;
  document.getElementById('btn-a').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 9 }));
  await sleep(200);
  const after = P.state().size;
  out.shape = { before, after };

  return JSON.stringify(out);
})()