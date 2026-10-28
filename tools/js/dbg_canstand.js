(() => {
  const P = window.__probe;
  const res = [];
  for (let x = 460; x <= 520; x += 4) {
    res.push({ x, can: P.canStand(x, 412), corners: [
      P.walkableAt(x - 11, 406), P.walkableAt(x + 11, 406),
      P.walkableAt(x - 11, 412), P.walkableAt(x + 11, 412),
    ]});
  }
  return JSON.stringify(res);
})()