(() => JSON.stringify({
  canTouch: ('ontouchstart' in window) || (navigator.maxTouchPoints || 0) > 0,
  hasOnTouchStart: 'ontouchstart' in window,
  maxTouchPoints: navigator.maxTouchPoints || 0,
  coarse: matchMedia('(pointer: coarse)').matches,
  mounted: !!window.__touch,
  path: window.__touch ? window.__touch.path : null,
  url: location.search || '(none)'
}))()