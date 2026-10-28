(() => {
  let cleanup = () => {};
  function init() {
    cleanup();
    const loader = document.querySelector('[data-plaza-loader]');
    const grid = document.querySelector('[data-plaza-grid]');
    if (!loader || !grid || !loader.dataset.nextPage) return;
    const more = loader.querySelector('[data-plaza-more]');
    const status = loader.querySelector('[data-plaza-status]');
    let busy = false, active = true, failed = false, observer, controller;
    cleanup = () => { active = false; observer?.disconnect(); controller?.abort(); };
    const urlFor = (page, batch = true) => {
      const url = new URL('/my-schedule/experiences/plaza', location.origin);
      url.search = new URLSearchParams({company: loader.dataset.company, order: loader.dataset.order, page});
      if (batch) url.searchParams.set('batch', 'true');
      return url;
    };
    async function load() {
      if (!active || busy || !loader.dataset.nextPage) return;
      busy = true;
      failed = false;
      more.setAttribute('aria-disabled', 'true');
      status.textContent = '正在加载…';
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(urlFor(loader.dataset.nextPage), {
          credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
          headers: {Accept: 'application/json'},
        });
        if (new URL(response.url).pathname.startsWith('/auth/login') || response.status === 401) {
          if (active) location.assign('/auth/login');
          return;
        }
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error('load');
        const batch = await response.json();
        if (!active) return;
        if (typeof batch.html !== 'string' || !(batch.next_page === null || Number.isInteger(batch.next_page))) throw Error('batch');
        const fragment = new DOMParser().parseFromString(batch.html, 'text/html');
        const ids = new Set([...grid.querySelectorAll('[data-plaza-id]')].map(card => card.dataset.plazaId));
        fragment.querySelectorAll('[data-plaza-id]').forEach(card => {
          if (!ids.has(card.dataset.plazaId)) { grid.append(card); ids.add(card.dataset.plazaId); }
        });
        loader.dataset.nextPage = batch.next_page || '';
        status.textContent = batch.next_page ? '下滑加载更多面经' : '已显示全部面经';
        if (batch.next_page) more.href = urlFor(batch.next_page, false).href;
        else { more.remove(); observer?.disconnect(); }
      } catch {
        if (active) {
          failed = true;
          status.textContent = '加载失败，请重试';
          more.textContent = '重新加载';
        }
      } finally {
        clearTimeout(timeout);
        busy = false;
        more.removeAttribute('aria-disabled');
        if (active && !failed && loader.dataset.nextPage && loader.getBoundingClientRect().top < innerHeight + 200)
          setTimeout(load, 0);
      }
    }
    more.addEventListener('click', event => { event.preventDefault(); load(); });
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting) && !failed) load();
      }, {rootMargin: '200px'});
      observer.observe(loader);
    }
  }
  document.addEventListener('personal:navigated', init);
  init();
})();
