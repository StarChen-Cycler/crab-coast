(() => {
  // 导出会话里最后出现的那张图（新生成的），返回 PNG dataURL
  const imgs = [...document.querySelectorAll('img')].filter((i) => i.naturalWidth >= 256);
  if (!imgs.length) return 'NONE';
  const img = imgs[imgs.length - 1];
  const c = document.createElement('canvas');
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  c.getContext('2d').drawImage(img, 0, 0);
  return c.toDataURL('image/png');
})()
