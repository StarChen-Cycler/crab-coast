(() => {
  const hits = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      const txt = (el.textContent || '').trim();
      if (txt && txt.length < 200 && /seaside_bgm|\.json/i.test(txt)) {
        hits.push({
          tag: el.tagName,
          cls: (el.className || '').toString().slice(0, 60),
          href: el.getAttribute && el.getAttribute('href') || null,
          download: el.getAttribute && el.getAttribute('download') || null,
          text: txt.slice(0, 80),
        });
      }
    }
  };
  walk(document);
  // 再找所有 a[href] 里像文件的
  const links = [...document.querySelectorAll('a[href]')]
    .map((a) => ({ href: a.getAttribute('href'), text: (a.textContent || '').trim().slice(0, 40) }))
    .filter((x) => /\.json|download|file|sandbox/i.test(x.href || '') || /\.json/i.test(x.text));
  return JSON.stringify({ hits: hits.slice(0, 12), links: links.slice(0, 12) });
})()
