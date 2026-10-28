(() => {
  const e = document.querySelector('#prompt-textarea, div[contenteditable="true"], textarea');
  if (!e) return JSON.stringify({ found: false });
  const t = (e.value !== undefined && e.value !== null && e.tagName === 'TEXTAREA')
    ? e.value
    : (e.innerText || '');
  return JSON.stringify({ found: true, len: t.length, head: t.slice(0, 40), tail: t.slice(-40) });
})()
