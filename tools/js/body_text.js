(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({ chars: t.length, text: t });
})()
