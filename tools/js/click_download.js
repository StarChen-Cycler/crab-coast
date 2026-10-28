(() => {
  const els = [...document.querySelectorAll('span,p,button')];
  const btn = els.find(e => (e.textContent || '').trim().startsWith('下载') && (e.textContent||'').includes('.json'));
  if (!btn) return 'NOT_FOUND';
  btn.click();
  return 'CLICKED';
})()