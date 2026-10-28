(() => {
  const t = window.__touch;
  const ui = document.getElementById('touch-ui');
  const a = document.getElementById('btn-a');
  const b = document.getElementById('btn-b');
  const stick = document.getElementById('stick-base');
  return JSON.stringify({
    touch: !!t,
    visible: t ? t.visible : null,
    uiExists: !!ui,
    buttons: ['y','x','b','a'].map(k => {
      const el = document.getElementById('btn-' + k);
      return k.toUpperCase() + ':' + (el ? (el.classList.contains('disabled') ? 'disabled' : 'active') : 'missing');
    }),
    stickBox: stick ? (() => { const r = stick.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width)]; })() : null,
    aBox: a ? (() => { const r = a.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)]; })() : null,
  });
})()