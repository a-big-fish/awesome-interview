const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/personal_resume_cache.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function browser({scope = 'session-a', records = new Map(), storage = true, inlinePdf = true} = {}) {
  const elements = new Map(), events = new Map(), calls = [], revoked = [], timers = new Map();
  let nextUrl = 0, nextTimer = 0, offline = false, blocked = false, unauthorized = false;
  let current = {id: 'r1', version: 'r1:v1', file_name: 'synthetic.pdf'}, pdfContent = '%PDF- synthetic', serverScope = scope;
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {hidden: false, dataset: {}, textContent: '',
      addEventListener(name, callback) {this[name] = callback;},
      removeAttribute(name) {delete this[name];},
      click() {}, requestSubmit() {this.submit?.({preventDefault() {}});}});
    return elements.get(selector);
  }
  const panel = {dataset: {cacheScope: scope}, querySelector: element, classList: {add() {}, remove() {}}, addEventListener() {}};
  const indexedDB = {open() {
    const request = {};
    queueMicrotask(() => {
      request.result = {close() {}, transaction() {
        const tx = {};
        tx.objectStore = () => ({
          get(key) {return perform(() => records.get(key));},
          put(value) {return perform(() => records.set('current', value));},
          clear() {return perform(() => records.clear());},
        });
        function perform(action) {
          const result = {};
          queueMicrotask(() => {result.result = action(); result.onsuccess?.(); tx.oncomplete?.();});
          return result;
        }
        return tx;
      }};
      request.onsuccess();
    });
    return request;
  }};
  class BrowserURL extends URL {
    static createObjectURL() {return `blob:synthetic-${++nextUrl}`;}
    static revokeObjectURL(url) {revoked.push(url);}
  }
  const context = {
    window: {indexedDB: storage ? indexedDB : undefined}, indexedDB,
    URL: BrowserURL, Blob, AbortController, Date, navigator: {pdfViewerEnabled: inlinePdf},
    document: {querySelector: () => panel, addEventListener: (name, callback) => events.set(name, callback)},
    addEventListener: (name, callback) => events.set(name, callback),
    location: {assign(url) {this.redirect = url;}},
    setTimeout(callback, delay) {const id = ++nextTimer; timers.set(id, {callback, delay}); return id;},
    clearTimeout(id) {timers.delete(id);},
    fetch(url, options) {
      calls.push({url, options});
      if (offline) return Promise.reject(Error('offline'));
      if (blocked) return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(Error('abort'))));
      const pdf = url.endsWith('/pdf');
      return Promise.resolve({ok: !unauthorized, status: unauthorized ? 401 : 200,
        url: 'https://test.local' + url,
        headers: {get: () => pdf ? 'application/pdf' : 'application/json'},
        json: async () => ({resume: current, cache_scope: serverScope}), blob: async () => new Blob([pdfContent], {type: 'application/pdf'}),
      });
    },
  };
  vm.runInNewContext(source, context);
  return {records, calls, elements, events, revoked, context,
    node: name => element(`[data-resume-${name}]`),
    state: value => {current = value;}, offline: value => {offline = value;},
    pdf: value => {pdfContent = value;},
    serverScope: value => {serverScope = value;},
    block: value => {blocked = value;}, unauthorized: value => {unauthorized = value;},
    async ready() {await tick(); await tick();},
    async sync() {element('[data-resume-sync]').click(); await tick(); await tick();},
    async navigate() {events.get('personal:navigated')(); await tick(); await tick();},
    stop() {events.get('pagehide')();},
  };
}

test('cache persists the PDF; unchanged version skips download; manual sync forces it', async () => {
  const app = browser();
  await app.ready();
  assert.match(app.node('frame').src, /^blob:/);
  assert.equal(app.records.get('current').scope, 'session-a');
  assert.equal(app.calls.filter(call => call.url.endsWith('/pdf')).length, 1);
  await app.navigate();
  assert.equal(app.calls.filter(call => call.url.endsWith('/pdf')).length, 1);
  assert.match(app.node('status').textContent, /已同步/);
  await app.sync();
  assert.equal(app.calls.filter(call => call.url.endsWith('/pdf')).length, 2);
  app.stop();
  assert.ok(app.revoked.length >= 2);
});

test('hard reload restores cached PDF before a blocked network check', async () => {
  const initial = browser(); await initial.ready(); initial.stop();
  const app = browser({records: initial.records});
  app.block(true);
  await app.ready();
  assert.match(app.node('frame').src, /^blob:/);
  assert.match(app.node('status').textContent, /缓存/);
  assert.equal(app.calls.length, 1);
  app.stop(); await tick();
});

test('offline retains old preview; a new version replaces it after successful download', async () => {
  const app = browser(); await app.ready();
  const old = app.node('frame').src;
  app.offline(true); await app.sync();
  assert.equal(app.node('frame').src, old);
  assert.match(app.node('status').textContent, /同步失败.*缓存/);
  app.offline(false); app.state({id: 'r2', version: 'r2:v1', file_name: 'new.pdf'});
  await app.sync();
  assert.notEqual(app.node('frame').src, old);
  assert.equal(app.node('name').textContent, 'new.pdf');
  assert.equal(app.records.get('current').id, 'r2');
  app.stop();
});

test('no resume or expired session clears cached files; other login scopes cannot display them', async () => {
  const initial = browser(); await initial.ready(); initial.stop();
  const other = browser({scope: 'session-b', records: initial.records}); other.block(true);
  await other.ready();
  assert.equal(other.node('frame').src, undefined);
  other.stop(); await tick();
  const app = browser(); await app.ready();
  app.state(null); await app.sync();
  assert.equal(app.records.size, 0);
  assert.equal(app.node('viewer').hidden, true);
  assert.match(app.node('status').textContent, /还没有/);
  app.state({id: 'r3', version: 'r3:v1', file_name: 'resume.pdf'}); await app.sync();
  app.unauthorized(true); await app.sync();
  assert.equal(app.records.size, 0);
  assert.equal(app.node('frame').src, undefined);
  assert.equal(app.context.location.redirect, '/auth/login');
  app.stop();
});

test('private storage unavailable falls back to memory and logout removes the preview', async () => {
  const app = browser({storage: false}); await app.ready();
  assert.match(app.node('frame').src, /^blob:/);
  await app.navigate();
  assert.equal(app.calls.filter(call => call.url.endsWith('/pdf')).length, 1);
  app.events.get('submit')({target: {matches: () => true}}); await tick();
  assert.equal(app.node('frame').src, undefined);
});

test('unsupported inline PDF viewer has an owner-checked open-file fallback', async () => {
  const app = browser({inlinePdf: false}); await app.ready();
  assert.equal(app.node('viewer').hidden, true);
  assert.equal(app.node('fallback').hidden, false);
  assert.equal(app.node('open').href, '/resumes/r1/pdf');
  app.stop();
});

test('an invalid new PDF cannot replace the existing cached preview', async () => {
  const app = browser(); await app.ready();
  const previous = app.node('frame').src;
  app.state({id: 'r2', version: 'r2:v1', file_name: 'new.pdf'});
  app.pdf('<html>not a PDF</html>'); await app.sync();
  assert.equal(app.node('frame').src, previous);
  assert.equal(app.records.get('current').id, 'r1');
  assert.match(app.node('status').textContent, /同步失败/);
  app.stop();
});

test('a login changed in another tab cannot cache the new account PDF under the old scope', async () => {
  const app = browser(); await app.ready();
  app.serverScope('new-login-scope');
  await app.sync();
  assert.equal(app.node('frame').src, undefined);
  assert.equal(app.records.size, 0);
  assert.equal(app.calls.filter(call => call.url.endsWith('/pdf')).length, 1);
  assert.equal(app.context.location.redirect, '/my-schedule/interviews');
  app.stop();
});
