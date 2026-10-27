(() => {
  const config = document.querySelector('meta[name="performance-csrf"]');
  if (!config?.content || window.awesomeInterviewPerformance) return;
  const originalFetch = window.fetch.bind(window);
  const key = 'awesome-interview-performance-v1';
  const metrics = new Set(['request', 'ttfb', 'load', 'lcp', 'longtask', 'cache_render']);
  const nodes = new Set(['calendar', 'event', 'event_write', 'event_parse', 'plaza', 'experiences',
    'editor', 'draft', 'experience_write', 'parse', 'pdf', 'markdown', 'export', 'interviews',
    'profile', 'login', 'register', 'mobile']);
  const nodeFor = (value, method = 'GET') => {
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin) return null;
      const path = url.pathname.replace(/\/$/, '');
      if (path === '/auth/login') return 'login';
      if (path === '/auth/register') return 'register';
      if (path.startsWith('/api/mobile/v1/')) return 'mobile';
      if (!path.startsWith('/my-schedule')) return null;
      const tail = path.slice('/my-schedule'.length);
      if (tail.startsWith('/admin') || tail.startsWith('/telemetry')) return null;
      if (tail === '' || tail === '/new') return 'calendar';
      if (tail === '/parse') return 'event_parse';
      if (tail.startsWith('/events')) return method === 'GET' ? 'event' : 'event_write';
      if (tail.startsWith('/interviews') || tail === '/resume') return 'interviews';
      if (tail.startsWith('/profile')) return 'profile';
      if (tail.startsWith('/experiences/plaza')) return 'plaza';
      if (tail === '/experiences') return 'experiences';
      if (tail.startsWith('/experiences/')) return ({'export.pdf': 'pdf', 'export.md': 'markdown',
        export: 'export', draft: 'draft', parse: 'parse', 'parse-file': 'parse'})[tail.split('/').pop()]
        || (method === 'GET' ? 'editor' : 'experience_write');
    } catch { /* Invalid or unsupported request URL. */ }
    return null;
  };
  const valid = (sample) => sample && nodes.has(sample.node) && metrics.has(sample.metric)
    && Number.isFinite(sample.duration) && sample.duration >= 0 && sample.duration <= 120000
    && Number.isInteger(sample.status) && (sample.status === 0 || sample.status >= 100 && sample.status <= 599)
    && Number.isFinite(sample.at) && sample.at > Date.now() - 3600000 && sample.at <= Date.now();
  let queue = [];
  try {
    const stored = JSON.parse(sessionStorage.getItem(key) || '[]');
    if (Array.isArray(stored)) queue = stored.filter(valid).slice(-100).map(
      ({node, metric, duration, status, at}) => ({node, metric, duration, status, at}));
  } catch { /* Keep an in-memory queue when storage is disabled. */ }
  let sending = false, stopped = false, timer, persistTimer, backoff = 15000;
  let latestLcp = 0, sentLcp = 0;
  const initialNode = nodeFor(location.href);
  const save = () => {
    clearTimeout(persistTimer);
    persistTimer = undefined;
    queue = queue.filter(valid).slice(-100);
    try { sessionStorage.setItem(key, JSON.stringify(queue)); } catch { /* Best effort. */ }
  };
  const schedule = (delay = document.hidden ? 60000 : backoff) => {
    clearTimeout(timer);
    if (!stopped) timer = setTimeout(() => flush(), delay);
  };
  const add = (node, metric, duration, status = 200) => {
    if (stopped) return;
    const sample = {node, metric, duration: Math.round(duration * 10) / 10, status, at: Date.now()};
    if (!valid(sample)) return;
    queue.push(sample);
    queue = queue.filter(valid).slice(-100);
    if (!persistTimer) persistTimer = setTimeout(save, 500);
    if (queue.length >= 20 && !sending && backoff === 15000) schedule(0);
  };
  async function flush(keepalive = false) {
    if (sending || stopped) return;
    if (latestLcp > sentLcp) {
      sentLcp = latestLcp;
      add(initialNode, 'lcp', latestLcp);
    }
    save();
    if (!queue.length || navigator.onLine === false) { schedule(); return; }
    sending = true;
    const batch = queue.slice(0, 20);
    const form = new FormData();
    form.set('csrf_token', config.content);
    form.set('payload', JSON.stringify({samples: batch.map(({node, metric, duration, status}) =>
      ({node, metric, duration, status}))}));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await originalFetch('/my-schedule/telemetry', {
        method: 'POST', body: form, credentials: 'same-origin', cache: 'no-store',
        keepalive, signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403) {
        stopped = true;
        queue = [];
      } else if (response.ok || response.status === 422 || response.status === 413) {
        queue = queue.filter(sample => !batch.includes(sample));
        backoff = 15000;
      } else backoff = Math.min(backoff * 2, 300000);
    } catch { backoff = Math.min(backoff * 2, 300000); }
    finally { clearTimeout(timeout); sending = false; save(); schedule(); }
  }
  window.fetch = function(input, init) {
    const method = (init?.method || input?.method || 'GET').toUpperCase();
    const node = nodeFor(typeof input === 'string' || input instanceof URL ? input : input.url, method);
    if (!node) return originalFetch(input, init);
    const started = performance.now();
    return originalFetch(input, init).then(response => {
      add(node, 'request', performance.now() - started, response.status);
      return response;
    }, error => {
      add(node, 'request', performance.now() - started, 0);
      throw error;
    });
  };
  window.awesomeInterviewPerformance = {
    recordRender: (duration) => add(nodeFor(location.href), 'cache_render', duration),
  };
  const navigation = () => setTimeout(() => {
    const entry = performance.getEntriesByType('navigation')[0];
    if (!entry) return;
    add(initialNode, 'ttfb', entry.responseStart - entry.startTime);
    if (entry.loadEventEnd > 0) add(initialNode, 'load', entry.loadEventEnd - entry.startTime);
  }, 0);
  if (document.readyState === 'complete') navigation();
  else addEventListener('load', navigation, {once: true});
  if ('PerformanceObserver' in window) {
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) if (entry.duration >= 200)
          add(nodeFor(location.href), 'longtask', entry.duration);
      }).observe({type: 'longtask', buffered: true});
    } catch { /* Unsupported in this browser. */ }
    try {
      new PerformanceObserver(list => {
        const last = list.getEntries().at(-1);
        if (last) latestLcp = last.startTime;
      }).observe({type: 'largest-contentful-paint', buffered: true});
    } catch { /* Unsupported in this browser. */ }
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) flush(true); });
  addEventListener('pagehide', () => flush(true));
  addEventListener('online', () => { backoff = 15000; schedule(); });
  document.addEventListener('submit', event => {
    if (event.target.matches('form[action="/auth/logout"]')) {
      stopped = true;
      queue = [];
      save();
      clearTimeout(timer);
    }
  });
  schedule();
})();
