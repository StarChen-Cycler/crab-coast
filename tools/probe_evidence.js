(async () => {
  const P = window.__probe;
  const cv = document.getElementById('scene');
  const g = cv.getContext('2d');
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const W = cv.width, H = cv.height;
  const grab = () => g.getImageData(0, 0, W, H).data;
  const out = {};

  const inBox = (x, y, boxes) => boxes.some((b) => x >= b.x0 && x <= b.x1 && y >= b.y0 && y <= b.y1);
  const crabBoxes = (positions) => positions.map((p) => ({
    x0: p.x - 40, x1: p.x + 40, y0: p.y - 62, y1: p.y + 12,
  }));

  // ---------- 1. 背景不随角色移动（冻结环境动画后逐像素比对） ----------
  P.freeze(true);
  P.releaseAll();
  P.setPos(200, 430);
  await sleep(120);
  const posA = P.state();
  const a = grab();
  P.setPos(800, 430);
  await sleep(120);
  const posB = P.state();
  const b = grab();
  const boxes = crabBoxes([posA, posB]);
  let diffOutside = 0, diffInside = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) {
        if (inBox(x, y, boxes)) diffInside++; else diffOutside++;
      }
    }
  }
  out.backgroundFixed = {
    crabA: posA, crabB: posB,
    diffOutsideCrab: diffOutside,
    diffInsideCrab: diffInside,
    totalPixels: W * H,
  };

  // ---------- 2. 海浪动画确实在动（解冻后连续 3 帧比对） ----------
  P.freeze(false);
  const band = { y0: 150, y1: 300 };
  const frames = [];
  for (let i = 0; i < 3; i++) {
    frames.push(grab());
    await sleep(700);
  }
  const bandDiff = (f1, f2) => {
    let n = 0;
    for (let y = band.y0; y < band.y1; y++) {
      for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        if (f1[i] !== f2[i] || f1[i + 1] !== f2[i + 1] || f1[i + 2] !== f2[i + 2]) n++;
      }
    }
    return n;
  };
  const bandPixels = W * (band.y1 - band.y0);
  out.waveAnim = {
    bandPixels,
    diff12: bandDiff(frames[0], frames[1]),
    diff23: bandDiff(frames[1], frames[2]),
    ratio12: +(bandDiff(frames[0], frames[1]) / bandPixels * 100).toFixed(3),
    ratio23: +(bandDiff(frames[1], frames[2]) / bandPixels * 100).toFixed(3),
  };

  // ---------- 3. 网络请求（应全部是本地） ----------
  const res = performance.getEntriesByType('resource').map((r) => r.name);
  out.resources = res;
  out.externalResources = res.filter((u) => !/^(http:\/\/127\.0\.0\.1|http:\/\/localhost|file:\/\/)/.test(u));

  // ---------- 4. 像素渲染是否关闭平滑 ----------
  out.pixelated = {
    imageSmoothing: g.imageSmoothingEnabled,
    cssImageRendering: getComputedStyle(cv).imageRendering,
    cssSize: P.canvasRect(),
    buffer: { w: W, h: H },
  };

  // ---------- 5. 帧率（移动中 3 秒） ----------
  P.setPos(300, 470);
  P.releaseAll();
  P.press('ArrowRight');
  await sleep(3000);
  P.release('ArrowRight');
  out.fps = P.fps();
  out.longFrames = P.longFrames();

  // ---------- 6. 动作卡资产自检（尺寸/透明角/居中） ----------
  const sheet = new Image();
  sheet.src = 'assets/crab_sheet.png';
  await new Promise((r) => { sheet.onload = r; });
  const sc = document.createElement('canvas');
  sc.width = sheet.width; sc.height = sheet.height;
  const sg = sc.getContext('2d');
  sg.drawImage(sheet, 0, 0);
  const sd = sg.getImageData(0, 0, sc.width, sc.height).data;
  const cells = [];
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      const ox = c * 64, oy = r * 64;
      const cornerA = [sd[((oy) * sc.width + ox) * 4 + 3],
                       sd[((oy) * sc.width + ox + 63) * 4 + 3],
                       sd[((oy + 63) * sc.width + ox) * 4 + 3],
                       sd[((oy + 63) * sc.width + ox + 63) * 4 + 3]];
      let minX = 64, maxX = -1;
      for (let y = 0; y < 64; y++) {
        for (let x = 0; x < 64; x++) {
          if (sd[((oy + y) * sc.width + ox + x) * 4 + 3] > 8) {
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
          }
        }
      }
      cells.push({ r, c, size: '64x64', cornerAlpha: cornerA, centerOff: +((minX + maxX) / 2 - 31.5).toFixed(1) });
    }
  }
  out.sheet = {
    size: sheet.width + 'x' + sheet.height,
    frames: cells.length,
    maxCenterOff: Math.max(...cells.map((c) => Math.abs(c.centerOff))),
    maxCornerAlpha: Math.max(...cells.flatMap((c) => c.cornerAlpha)),
  };

  return JSON.stringify(out);
})()
