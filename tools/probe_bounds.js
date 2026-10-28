(async () => {
  const P = window.__probe;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};

  // 预热：确认 rAF 与输入确实在工作（标签页被切到后台时会被节流，重试等待）
  const warm = { tries: 0, ok: false };
  for (let i = 0; i < 20; i++) {
    warm.tries = i + 1;
    P.setPos(480, 430);
    P.releaseAll();
    await sleep(60);
    const a = P.state();
    P.press('ArrowRight');
    await sleep(200);
    P.release('ArrowRight');
    const b = P.state();
    if (b.x - a.x > 5) { warm.ok = true; break; }
    await sleep(400);
  }
  out.warmup = warm;
  if (!warm.ok) return JSON.stringify(out);

  const runTo = async (x, y, code, ms) => {
    P.setPos(x, y);
    P.releaseAll();
    await sleep(80);
    P.press(code);
    await sleep(ms);
    P.release(code);
    await sleep(80);
    return P.state();
  };

  let s = await runTo(300, 500, 'ArrowRight', 7000);
  out.right = { x: s.x, limit: P.bounds.x1, within: s.x <= P.bounds.x1 };
  s = await runTo(300, 500, 'ArrowLeft', 4000);
  out.left = { x: s.x, limit: P.bounds.x0, within: s.x >= P.bounds.x0 };
  s = await runTo(160, 470, 'ArrowUp', 4000);
  out.up = { y: s.y, limit: P.bounds.y0, within: s.y >= P.bounds.y0 };
  s = await runTo(160, 400, 'ArrowDown', 4000);
  out.down = { y: s.y, limit: P.bounds.y1, within: s.y <= P.bounds.y1 };

  // 房屋遮挡：从房屋上方往下走，应停在房屋上沿（392）之前
  s = await runTo(730, 340, 'ArrowDown', 1500);
  out.houseBlock = { y: s.y, houseTop: 392, blocked: s.y < 392 };

  return JSON.stringify(out);
})()
