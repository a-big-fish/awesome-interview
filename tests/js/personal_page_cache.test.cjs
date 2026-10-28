const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/personal_page_cache.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function browser({hidden = true} = {}) {
  const calls = [], rendered = [], events = {}, timers = [];
  let clock = 0;
  const location = new URL('https://test.local/my-schedule/experiences/plaza');
  location.assign = () => {};
  const main = {replaceWith(next) {rendered.push(next.html);}};
  const document = {
    hidden, activeElement: null, title: 'plaza', documentElement: {outerHTML: 'initial-plaza'},
    body: {className: 'personal-app', classList: {add() {}, remove() {}}},
    querySelector(selector) {
      if (selector === '.page > main') return main;
      if (selector.includes('.personal-app .page-nav')) return {};
      return null;
    },
    querySelectorAll: () => [], addEventListener: (name, callback) => {events[name] = callback;},
    dispatchEvent() {},
  };
  const context = {document, location, URL, Date: {now: () => clock},
    window: {addEventListener() {}, scrollTo() {}},
    history: {pushState(_, __, url) {location.href = new URL(url, location).href;}},
    performance: {now: () => 0}, requestAnimationFrame: callback => callback(),
    Event: class {},
    DOMParser: class {parseFromString(html) {return {title: html, body: {className: 'personal-app', classList: {contains: () => true}},
      querySelector: selector => selector === '.page > main' ? {html} : null};}},
    setTimeout(callback, delay) {timers.push({callback, delay});},
    fetch(url) {return new Promise(resolve => calls.push({url, resolve, done: false}));},
  };
  vm.runInNewContext(source, context);
  return {calls, rendered, events, document, context,
    age: () => {clock += 31000;},
    async navigate(path) {assert.equal(context.window.awesomeInterviewNavigate(path), true); await tick();},
    async reply(call, html = call.url) {
      call.done = true;
      call.resolve({ok: true, status: 200, url: 'https://test.local' + call.url,
        headers: {get: () => 'text/html'}, text: async () => html});
      await tick();
    },
    prefetch: () => timers.find(timer => timer.delay === 800).callback(),
  };
}

test('profile and interviews use fresh cached pages without duplicate full-page fetches', async () => {
  const app = browser();
  await app.navigate('/my-schedule/profile');
  await app.reply(app.calls[0], 'profile-html');
  await app.navigate('/my-schedule/interviews');
  await app.reply(app.calls[1], 'interviews-html');
  await app.navigate('/my-schedule/profile');
  await app.navigate('/my-schedule/interviews');
  assert.equal(app.calls.length, 2);
  assert.equal(app.rendered.at(-1), 'interviews-html');
});

test('expired page displays first but background refresh does not overwrite focused input', async () => {
  const app = browser();
  await app.navigate('/my-schedule/profile'); await app.reply(app.calls[0], 'old-profile');
  await app.navigate('/my-schedule/experiences/plaza');
  app.age();
  await app.navigate('/my-schedule/profile');
  assert.equal(app.rendered.at(-1), 'old-profile');
  app.document.activeElement = {matches: () => true};
  await app.reply(app.calls[1], 'new-profile');
  assert.equal(app.rendered.at(-1), 'old-profile');
});

test('prefetch of expanded navigation remains sequential', async () => {
  const app = browser({hidden: false});
  app.prefetch(); await tick();
  assert.equal(app.calls.length, 1);
  for (let index = 0; index < 4; index++) {
    assert.equal(app.calls.filter(call => !call.done).length, 1);
    await app.reply(app.calls[index]);
  }
  assert.equal(app.calls.length, 4);
  assert.equal(app.calls.filter(call => !call.done).length, 0);
});
