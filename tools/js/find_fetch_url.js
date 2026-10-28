(() => {
  const urls = performance.getEntriesByType('resource').map(r => r.name)
    .filter(u => /file|download|sandbox|json|attachment|content/i.test(u));
  return JSON.stringify({ count: urls.length, urls: urls.slice(-12) });
})()