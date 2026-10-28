(() => {
  // 判断当前会话是否还在生成：
  // 1) 找停止/暂停按钮（aria-label 或 data-testid 含 stop）；
  // 2) 找发送按钮（data-testid=send-button 且未禁用）；
  // 3) 统计消息气泡里已出现的图片数量与最大尺寸。
  const btns = [...document.querySelectorAll('button')].map((b) => ({
    label: (b.getAttribute('aria-label') || '').trim(),
    testid: (b.getAttribute('data-testid') || '').trim(),
    disabled: b.disabled,
  }));
  const stop = btns.filter(
    (b) => /stop|停止|暂停/i.test(b.label) || /stop/i.test(b.testid)
  );
  const send = btns.filter((b) => /send/i.test(b.testid) || /发送/i.test(b.label));
  const imgs = [...document.querySelectorAll('img')]
    .filter((i) => i.naturalWidth >= 256)
    .map((i) => ({ w: i.naturalWidth, h: i.naturalHeight }));

  // 最后一条助手消息的文本长度，用于判断是否还在流式输出
  const nodes = [...document.querySelectorAll('[data-message-author-role]')];
  const lastText = nodes.length ? nodes[nodes.length - 1].innerText || '' : '';

  return JSON.stringify({
    generating: stop.length > 0,
    stopButtons: stop.length,
    sendEnabled: send.length > 0 && send.some((b) => !b.disabled),
    imageCount: imgs.length,
    images: imgs.slice(-3),
    lastTextLen: lastText.length,
    buttonSample: btns.slice(0, 24),
  });
})()
