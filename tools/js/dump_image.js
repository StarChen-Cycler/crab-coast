(() => {
  // 导出页面上最大的那张图（通常是刚生成的图），返回 PNG dataURL
  const imgs = [...document.querySelectorAll('img')]
    .filter((i) => i.naturalWidth >= 256)
    .sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight);
  if (!imgs.length) return 'NONE';
  const img = imgs[0];
  const c = document.createElement('canvas');
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  c.getContext('2d').drawImage(img, 0, 0);
  return c.toDataURL('image/png');
})()
