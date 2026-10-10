(() => {
  // Private HTML stays in this page's memory; the server sends no-store.
  const paths = ['/my-schedule', '/my-schedule/experiences/plaza', '/my-schedule/experiences'];
  const allowed = new Set(paths);
  if (!document.querySelector('.personal-app .page-nav a[href="/my-schedule/experiences/plaza"]')) return;
  const ttl = 30000;
  const pages = new Map();
  const pending = new Map();
  let navigationId = 0;
  let pageEdited = false;
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('awesome-interview-pages') : null;
  channel?.addEventListener('message', () => pages.clear());

  async function load(url, force = false) {
    const stored = pages.get(url);
    if (!force && stored && Date.now() - stored.time < ttl) return stored.html;
    if (pending.has(url)) return pending.get(url);
    const task = (async () => {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'text/html' } });
      const resolved = new URL(response.url, location.href);
      if (resolved.pathname.startsWith('/auth/login') || response.status === 401) {
        pages.clear();
        location.assign(resolved.pathname.startsWith('/auth/login') ? resolved.href : '/auth/login');
        throw new Error('登录已过期');
      }
      if (!response.ok || resolved.pathname !== url ||
          !response.headers.get('content-type')?.includes('text/html')) throw new Error('页面需要重新加载');
      const html = await response.text();
      pages.set(url, { html, time: Date.now() });
      return html;
    })();
    pending.set(url, task);
    try { return await task; }
    finally { pending.delete(url); }
  }

  const prefetch = () => {
    if (document.querySelector('[data-experience-editor]')) return;
    paths.filter((path) => path !== location.pathname).forEach((path, index) => {
      setTimeout(() => { load(path).catch(() => {}); }, 250 + index * 500);
    });
  };

  const setNavState = (page) => {
    const active = page.querySelector('.page-nav a[aria-current="page"]')?.getAttribute('href');
    document.querySelectorAll('.page-nav a').forEach((link) => {
      if (link.getAttribute('href') === active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  };

  function render(html, resetScroll) {
    const page = new DOMParser().parseFromString(html, 'text/html');
    const nextMain = page.querySelector('.page > main');
    const currentMain = document.querySelector('.page > main');
    if (!nextMain || !currentMain || !page.body.classList.contains('personal-app'))
      throw new Error('页面结构已变化');
    document.title = page.title;
    document.body.className = page.body.className;
    currentMain.replaceWith(nextMain);
    setNavState(page);
    pageEdited = false;
    if (resetScroll) window.scrollTo(0, 0);
    document.dispatchEvent(new Event('personal:navigated'));
  }

  async function navigate(url, addHistory = true) {
    const target = new URL(url, location.href);
    if (target.origin !== location.origin || !allowed.has(target.pathname) || target.search) {
      location.assign(target.href);
      return;
    }
    const id = ++navigationId;
    const cached = pages.get(target.pathname)?.html;
    if (cached) {
      try {
        if (addHistory) history.pushState({ personalPage: true }, '', target.pathname);
        render(cached, true);
      } catch {
        location.assign(target.href);
        return;
      }
      // The cached page is visible before this request completes.
      load(target.pathname, true).then((html) => {
        if (id !== navigationId || location.pathname !== target.pathname || pageEdited || html === cached)
          return;
        const focused = document.activeElement;
        if (focused?.matches('input, textarea, select, [contenteditable]')) return;
        try { render(html, false); } catch { location.assign(target.href); }
      }).catch(() => {});
      return;
    }
    document.body.classList.add('personal-navigation-loading');
    try {
      const html = await load(target.pathname);
      if (id !== navigationId) return;
      if (addHistory) history.pushState({ personalPage: true }, '', target.pathname);
      render(html, true);
      prefetch();
    } catch { location.assign(target.href); }
    finally { document.body.classList.remove('personal-navigation-loading'); }
  }

  if (allowed.has(location.pathname) && !location.search) {
    pages.set(location.pathname, { html: document.documentElement.outerHTML, time: Date.now() });
  }
  if ('requestIdleCallback' in window) requestIdleCallback(prefetch, { timeout: 1800 });
  else setTimeout(prefetch, 800);

  // Native Android and Windows navigation can use the same cache-first path.
  window.awesomeInterviewNavigate = (url) => {
    const target = new URL(url, location.href);
    if (target.origin !== location.origin || !allowed.has(target.pathname) || target.search ||
        document.querySelector('[data-experience-editor]')) return false;
    if (target.pathname !== location.pathname || location.search || !pageEdited)
      navigate(target.href, target.pathname !== location.pathname || !!location.search);
    else load(target.pathname, true).catch(() => {});
    return true;
  };

  document.addEventListener('click', (event) => {
    const link = event.target.closest('.page-nav a[href], a.brand[href]');
    if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
        link.target || document.querySelector('[data-experience-editor]')) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || !allowed.has(target.pathname) || target.search ||
        target.pathname === location.pathname && !location.search) return;
    event.preventDefault();
    navigate(target.href);
  });
  window.addEventListener('popstate', () => {
    const editor = document.querySelector('[data-experience-editor]');
    if (editor) {
      const base = `/my-schedule/experiences/${editor.dataset.experienceId}`;
      if ([base, `${base}/write`, `${base}/import`].includes(location.pathname)) return;
    }
    if (allowed.has(location.pathname) && !location.search) navigate(location.href, false);
    else location.reload();
  });
  document.addEventListener('input', (event) => {
    if (event.target.closest('.page > main')) pageEdited = true;
  });
  document.addEventListener('change', (event) => {
    if (event.target.closest('.page > main')) pageEdited = true;
  });
  document.addEventListener('submit', (event) => {
    if (event.target.method?.toUpperCase() === 'POST') {
      pages.clear();
      channel?.postMessage('invalidate');
    }
  });
})();
