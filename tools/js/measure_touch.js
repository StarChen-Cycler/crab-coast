(() => {
  const b = document.getElementById('stick-base').getBoundingClientRect();
  const k = document.getElementById('stick-knob').getBoundingClientRect();
  const kStyle = getComputedStyle(document.getElementById('stick-knob'));
  const a = document.getElementById('btn-a').getBoundingClientRect();
  const abxy = document.getElementById('abxy').getBoundingClientRect();
  const c = document.querySelector('canvas').getBoundingClientRect();
  return JSON.stringify({
    viewport: [innerWidth, innerHeight], dpr: devicePixelRatio,
    coarse: matchMedia('(pointer: coarse)').matches,
    base: [b.left, b.top, b.width, b.height].map(v => +v.toFixed(1)),
    knob: [k.left, k.top, k.width, k.height].map(v => +v.toFixed(1)),
    knobTransform: kStyle.transform,
    a: [a.left, a.top, a.width, a.height].map(v => +v.toFixed(1)),
    abxy: [abxy.left, abxy.top, abxy.width, abxy.height].map(v => +v.toFixed(1)),
    canvas: [c.left, c.top, c.width, c.height].map(v => +v.toFixed(1)),
    size: window.__probe.state().size
  });
})()