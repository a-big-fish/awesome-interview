const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/experience_plaza.js', 'utf8');

function browser() {
  const cards = [{dataset: {plazaId: 'existing'}}], events = {}, calls = [];
  const status = {textContent: ''};
  const more = {setAttribute() {}, removeAttribute() {}, remove() {this.removed = true;},
    addEventListener(name, callback) {this[name] = callback;}};
  const loader = {dataset: {company: '公司 & %_', order: 'oldest', nextPage: '2'},
    querySelector: key => key.includes('status') ? status : more,
    getBoundingClientRect: () => ({top: 5000})};
  const grid = {querySelectorAll: () => cards, append: card => cards.push(card)};
  let observed;
  const context = {URL, URLSearchParams, AbortController, innerHeight: 800, setTimeout, clearTimeout,
    location: {origin: 'https://test.local', assign(url) {this.redirect = url;}},
    document: {querySelector: selector => selector.includes('loader') ? loader : grid,
      addEventListener: (name, callback) => {events[name] = callback;}},
    DOMParser: class {parseFromString(html) {return {querySelectorAll: () =>
      html.split(',').filter(Boolean).map(plazaId => ({dataset: {plazaId}}))};}},
    fetch(url, options) {return new Promise((resolve, reject) => calls.push({url, options, resolve, reject}));},
    window: {IntersectionObserver: true},
    IntersectionObserver: class {constructor(callback) {observed = callback;} observe() {} disconnect() {}},
  };
  vm.runInNewContext(source, context);
  return {cards, calls, loader, status, more, events, context,
    intersect: () => observed([{isIntersecting: true}]),
    async reply(html, next_page = null) {
      calls.at(-1).resolve({url: 'https://test.local/my-schedule/experiences/plaza', ok: true,
        headers: {get: () => 'application/json'}, json: async () => ({html, next_page})});
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('scroll and clicks share one request; append without duplicates and stop at end', async () => {
  const app = browser();
  app.intersect(); app.intersect(); app.more.click({preventDefault() {}});
  assert.equal(app.calls.length, 1);
  const params = app.calls[0].url.searchParams;
  assert.equal(params.get('company'), '公司 & %_');
  assert.equal(params.get('order'), 'oldest');
  assert.equal(params.get('page'), '2');
  await app.reply('existing,new,new');
  assert.deepEqual(app.cards.map(card => card.dataset.plazaId), ['existing', 'new']);
  assert.equal(app.status.textContent, '已显示全部面经');
  assert.equal(app.more.removed, true);
  app.intersect();
  assert.equal(app.calls.length, 1);
});

test('failed loads keep position and require retry rather than looping', async () => {
  const app = browser();
  app.intersect();
  app.calls[0].reject(new Error('offline'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.status.textContent, '加载失败，请重试');
  app.intersect();
  assert.equal(app.calls.length, 1);
  app.more.click({preventDefault() {}});
  assert.equal(app.calls.length, 2);
  assert.equal(app.calls[1].url.searchParams.get('page'), '2');
  await app.reply('retried', 3);
  assert.equal(app.loader.dataset.nextPage, 3);
});

test('navigation aborts the old request and its late result cannot append cards', async () => {
  const app = browser();
  app.intersect();
  app.events['personal:navigated']();
  assert.equal(app.calls[0].options.signal.aborted, true);
  await app.reply('late-result');
  assert.deepEqual(app.cards.map(card => card.dataset.plazaId), ['existing']);
});
