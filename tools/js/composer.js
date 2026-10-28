(() => {
  const e = document.querySelector('#prompt-textarea, div[contenteditable="true"], textarea');
  if (!e) return JSON.stringify({ found: false });
  const r = e.getBoundingClientRect();
  return JSON.stringify({
    found: true,
    x: Math.round(r.x + r.width / 2),
    y: Math.round(r.y + r.height / 2),
  });
})()
