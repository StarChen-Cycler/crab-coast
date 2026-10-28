(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const P = window.__probe;
  const out = {};
  out.touchMounted = !!window.__touch;                       // 桌面应为 false
  out.hudDisplay = getComputedStyle(document.querySelector('.hud')).display;
  out.htmlClass = document.documentElement.className;
  out.sizeBtn = document.getElementById('size-btn').textContent;
  out.coarse = matchMedia('(pointer: coarse)').matches;

  // T 键：中 48 -> 小 24 -> 中 48 -> 大 96 -> 中 48（反弹）
  const seq = [];
  for (let i = 0; i < 4; i++) {
    P.press('KeyT'); await sleep(90); seq.push(P.state().size);
  }
  out.tSeq = seq;

  // 键盘移动仍然正常
  P.releaseAll(); P.setPos(500, 412); await sleep(100);
  const a = P.state();
  P.press('KeyD'); await sleep(420); P.release('KeyD');
  const b = P.state();
  out.kbMoveDx = +(b.x - a.x).toFixed(1);
  out.dbg = document.documentElement.className || '(none)';
  return JSON.stringify(out);
})()