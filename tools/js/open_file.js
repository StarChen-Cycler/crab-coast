(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const els = [...document.querySelectorAll('span,p,button,div')];
  const btn = els.find(e => (e.textContent || '').trim() === '打开文件');
  if (!btn) return JSON.stringify({ ok: false, why: 'no button' });
  btn.click();
  await sleep(2500);
  const t = document.body.innerText || '';
  const hasJson = t.includes('"midi"') || t.includes('midi":');
  const idx = t.indexOf('"bpm"');
  return JSON.stringify({ ok: true, len: t.length, hasJson, idx, sample: idx > 0 ? t.slice(idx, idx + 200) : '' });
})()