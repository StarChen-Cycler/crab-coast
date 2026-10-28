(async () => {
  const url = 'https://chatgpt.com/backend-api/estuary/content?id=file_00000000d8608230b325519cf31b6ec2&fn=seaside_bgm_40s_96bpm.json&cd=attachment&ts=498104&p=fs&cid=1&sig=52a7325d55eb6f99fb5391d3ac57757cbfa91d1f7c4221a645c6bea546efddb9&v=0';
  const r = await fetch(url, { credentials: 'include' });
  const t = await r.text();
  if (!r.ok) return JSON.stringify({ ok: false, status: r.status, head: t.slice(0, 100) });
  window.__score = t;
  return JSON.stringify({ ok: true, len: t.length, head: t.slice(0, 120) });
})()