(() => {
  const out = { candidates: [] };
  for (const el of document.querySelectorAll('pre, code, textarea, div, span')) {
    const t = el.textContent || '';
    if (t.length > 1500 && t.includes('midi')) {
      out.candidates.push({ tag: el.tagName, cls: (el.className||'').toString().slice(0,40), len: t.length });
    }
  }
  out.candidates = out.candidates.sort((a,b)=>b.len-a.len).slice(0,6);
  const pre = document.querySelector('pre');
  out.preLen = pre ? (pre.textContent||'').length : 0;
  return JSON.stringify(out);
})()