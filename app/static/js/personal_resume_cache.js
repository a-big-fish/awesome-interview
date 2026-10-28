(() => {
  const limit = 20 * 1024 * 1024;
  let memory = null, stop = () => {}, database, cacheEpoch = 0;
  function openDatabase() {
    if (!database) database = new Promise((resolve, reject) => {
      if (!window.indexedDB) { reject(Error('unavailable')); return; }
      const request = indexedDB.open('awesome-interview-private-resume-v1', 1);
      const timeout = setTimeout(() => reject(Error('timeout')), 500);
      request.onupgradeneeded = () => request.result.createObjectStore('resume', {keyPath: 'key'});
      request.onsuccess = () => {
        clearTimeout(timeout);
        request.result.onversionchange = () => request.result.close();
        resolve(request.result);
      };
      request.onerror = () => { clearTimeout(timeout); reject(request.error); };
      request.onblocked = () => { clearTimeout(timeout); reject(Error('blocked')); };
    });
    return database;
  }
  async function stored(action, value) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('resume', action === 'get' ? 'readonly' : 'readwrite');
      const store = tx.objectStore('resume');
      const request = action === 'get' ? store.get('current') : action === 'put' ? store.put(value) : store.clear();
      let result;
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(result);
      tx.onabort = tx.onerror = () => reject(tx.error || Error('storage'));
    });
  }
  const valid = (entry, scope) => entry?.scope === scope && typeof entry.version === 'string'
    && typeof entry.file_name === 'string' && typeof entry.id === 'string'
    && entry.blob instanceof Blob && entry.blob.size > 0 && entry.blob.size <= limit;
  async function read(scope) {
    const epoch = cacheEpoch;
    if (valid(memory, scope)) return memory;
    try {
      const entry = await stored('get');
      if (epoch !== cacheEpoch) return null;
      if (valid(entry, scope)) return (memory = entry);
      if (entry) await stored('clear');
    } catch { /* Memory/network fallback when private storage is unavailable. */ }
    return null;
  }
  async function forget() {
    cacheEpoch++;
    memory = null;
    try { await stored('clear'); } catch { /* Best effort; the next session uses a different scope. */ }
  }
  function remember(entry) {
    memory = entry;
    return stored('put', {...entry, key: 'current'}).catch(() => {});
  }
  function init() {
    stop();
    const panel = document.querySelector('[data-resume-cache]');
    if (!panel) return;
    const scope = panel.dataset.cacheScope;
    const status = panel.querySelector('[data-resume-status]');
    const name = panel.querySelector('[data-resume-name]');
    const viewer = panel.querySelector('[data-resume-viewer]');
    const frame = panel.querySelector('[data-resume-frame]');
    const fallback = panel.querySelector('[data-resume-fallback]');
    const inlinePdf = typeof navigator === 'undefined' || navigator.pdfViewerEnabled === true;
    panel.dataset.inlinePdf = String(inlinePdf);
    const empty = panel.querySelector('[data-resume-empty]');
    const open = panel.querySelector('[data-resume-open]');
    const button = panel.querySelector('[data-resume-sync]');
    const form = panel.querySelector('[data-cached-resume-upload]');
    const file = panel.querySelector('[data-resume-file]');
    const choose = panel.querySelector('[data-resume-choose]');
    let active = true, busy = false, controller, entry, objectUrl;
    const hide = () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
      frame.removeAttribute('src');
      open.removeAttribute('href');
      viewer.hidden = open.hidden = fallback.hidden = true;
      empty.hidden = false;
      name.textContent = '';
      entry = null;
    };
    stop = () => { active = false; controller?.abort(); hide(); };
    function show(value) {
      if (!active) return;
      if (entry?.blob !== value.blob) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(value.blob);
        if (inlinePdf) frame.src = objectUrl;
        open.href = inlinePdf ? objectUrl : `/resumes/${encodeURIComponent(value.id)}/pdf`;
      }
      entry = value;
      viewer.hidden = !inlinePdf;
      fallback.hidden = inlinePdf;
      open.hidden = false;
      empty.hidden = true;
      name.textContent = value.file_name;
    }
    const restored = read(scope).then(cached => {
      if (active && cached) {
        show(cached);
        status.textContent = '已显示缓存简历，正在检查更新…';
      }
    });
    async function request(url, accept) {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store',
        headers: {Accept: accept}, signal: controller.signal});
      if (response.status === 401 || response.status === 403 || new URL(response.url).pathname.startsWith('/auth/login')) {
        if (active) {
          hide();
          active = false;
          await forget();
          location.assign('/auth/login');
        }
        throw Error('auth');
      }
      if (!response.ok || !response.headers.get('content-type')?.includes(accept)) throw Error('response');
      return response;
    }
    async function sync(force = false) {
      if (!active || busy) return;
      busy = true;
      button.disabled = true;
      button.textContent = '同步中…';
      await restored;
      if (!active) return;
      status.textContent = entry ? '已显示缓存简历，正在检查更新…' : '正在获取简历…';
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const state = await (await request('/my-schedule/resume/current', 'application/json')).json();
        if (!active) return;
        if (state.cache_scope !== scope) {
          hide();
          active = false;
          await forget();
          location.assign('/my-schedule/interviews');
          return;
        }
        if (state.resume === null) {
          hide();
          await forget();
          if (active) status.textContent = '还没有我的简历，请上传 PDF。';
          return;
        }
        const current = state.resume;
        if (!current || typeof current.id !== 'string' || typeof current.version !== 'string'
            || typeof current.file_name !== 'string') throw Error('state');
        // Derive the owner-checked same-origin URL; never trust arbitrary returned URLs.
        if (force || !entry || current.version !== entry.version || current.id !== entry.id) {
          const pdf = await request(`/resumes/${encodeURIComponent(current.id)}/pdf`, 'application/pdf');
          const blob = await pdf.blob();
          if (!active) return;
          if (!blob.size || blob.size > limit || await blob.slice(0, 5).text() !== '%PDF-') throw Error('pdf');
          if (!active) return;
          const next = {...current, scope, blob};
          show(next);
          void remember(next);
        }
        status.textContent = `已同步 ${new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
      } catch {
        if (active) status.textContent = entry ? '同步失败，正在显示缓存简历；可点击同步重试。' : '简历加载失败，请点击同步重试。';
      } finally {
        clearTimeout(timeout);
        busy = false;
        if (active) { button.disabled = false; button.textContent = '同步简历'; }
      }
    }
    button.addEventListener('click', () => sync(true));
    choose.addEventListener('click', () => file.click());
    function upload() {
      const selected = file.files?.[0];
      if (!selected) return;
      if (!selected.name.toLowerCase().endsWith('.pdf') || selected.size > limit || !selected.size) {
        status.textContent = '请选择不超过 20 MB 的 PDF 文件。';
        file.value = '';
        return;
      }
      form.requestSubmit();
    }
    file.addEventListener('change', upload);
    form.addEventListener('submit', event => {
      if (form.dataset.uploading) { event.preventDefault(); return; }
      form.dataset.uploading = 'true';
      choose.disabled = true;
      choose.textContent = '正在上传解析…';
      stop();
      void forget();
    });
    panel.addEventListener('dragover', event => { event.preventDefault(); panel.classList.add('is-resume-dragging'); });
    panel.addEventListener('dragleave', () => panel.classList.remove('is-resume-dragging'));
    panel.addEventListener('drop', event => {
      event.preventDefault(); panel.classList.remove('is-resume-dragging');
      if (event.dataTransfer?.files?.length) { file.files = event.dataTransfer.files; upload(); }
    });
    sync();
  }
  document.addEventListener('personal:navigated', init);
  document.addEventListener('submit', event => {
    if (event.target.matches('form[action="/auth/logout"]')) { stop(); void forget(); }
  });
  document.addEventListener('awesome-interview:session-expired', () => { stop(); void forget(); });
  addEventListener('pagehide', () => stop());
  init();
})();
