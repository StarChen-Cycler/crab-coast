(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 25 && !(window.__probe && window.__probe.ready); i++) await sleep(150);
  const out = {
    url: location.search || '(none)',
    mounted: !!window.__touch,
    hasTouchStart: 'ontouchstart' in window,
    maxTouchPoints: navigator.maxTouchPoints || 0,
    coarse: matchMedia('(pointer: coarse)').matches,
  };
  if (!window.__touch) return JSON.stringify(out);
  out.path = window.__touch.path;
  out.hudHidden = getComputedStyle(document.querySelector('.hud')).display;

  // 鼠标拖摇杆（pointer 通道，pointerType=mouse）
  const base = document.getElementById('stick-base');
  const r = base.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const ev = (target, type, x, y) => target.dispatchEvent(new PointerEvent(type, {
    bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 2, pointerType: 'mouse', isPrimary: true
  }));
  ev(base, 'pointerdown', cx, cy);
  ev(base, 'pointermove', cx + 40, cy);
  await sleep(60);
  out.dirMouse = window.__input.touchDir;
  ev(base, 'pointerup', cx + 40, cy);
  await sleep(80);
  out.dirAfterUp = window.__input.touchDir;

  // 触摸型 pointer 必须被跳过（模拟有 touch 通道的机型；这里没有 touch 通道所以应正常处理）
  window.__input.setTouchDir(null);
  base.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, cancelable: true, clientX: cx, clientY: cy - 40, pointerId: 5, pointerType: 'touch', isPrimary: true
  }));
  await sleep(60);
  out.dirTouchPointer = window.__input.touchDir;
  base.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, cancelable: true, clientX: cx, clientY: cy - 40, pointerId: 5, pointerType: 'touch', isPrimary: true
  }));
  await sleep(60);
  out.dirAfterTouchPointerUp = window.__input.touchDir;
  out.diag = window.__touch.diag();
  return JSON.stringify(out, null, 1);
})()