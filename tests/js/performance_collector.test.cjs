const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/performance_collector.js', 'utf8');

function browser({storageFails = false} = {}) {
  const timers = new Map(), storage = new Map(), calls = [], events = new Map();
  let nextTimer = 0, reply = 204, failed = false;
  const location = new URL('https://test.local/my-schedule/experiences/private-id?title=private-title');
  const fetch = async (url, options) => {
    calls.push({url, options});
    if (failed) throw new TypeError('network unavailable');
    return {status: url === '/my-schedule/telemetry' ? reply : 200, ok: reply < 400};
  };
  const context = {
    window: {fetch}, location, URL, FormData, AbortController, navigator: {onLine: true},
    document: {hidden: false, readyState: 'loading',
      querySelector: () => ({content: 'synthetic-csrf'}),
      addEventListener: (name, callback) => events.set(name, callback)},
    performance: {now: () => 10, getEntriesByType: () => []},
    sessionStorage: {
      getItem(key) { if (storageFails) throw new Error('storage blocked'); return storage.get(key); },
      setItem(key, value) { if (storageFails) throw new Error('storage blocked'); storage.set(key, value); },
    },
    setTimeout(callback, delay) { const id = ++nextTimer; timers.set(id, {callback, delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    addEventListener: (name, callback) => events.set(name, callback),
  };
  vm.runInNewContext(source, context);
  return {context, calls, events, timers,
    add: value => context.window.awesomeInterviewPerformance.recordRender(value),
    queued: () => JSON.parse([...storage.values()][0] || '[]'),
    reply: value => { reply = value; },
    fail: value => { failed = value; },
    async fire(delay) {
      const timer = [...timers.entries()].find(([, value]) => value.delay === delay);
      assert.ok(timer, `Expected a ${delay}ms timer`);
      timers.delete(timer[0]);
      timer[1].callback();
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('collect locally with a bounded queue and no resource IDs; only send after scheduled flush', async () => {
  const app = browser();
  for (let i = 0; i < 120; i++) app.add(i);
  assert.equal(app.calls.length, 0);
  await app.fire(500);
  assert.equal(app.queued().length, 100);
  assert.equal(JSON.stringify(app.queued()).includes('private'), false);
  await app.fire(0);
  assert.equal(app.calls.length, 1);
  const samples = JSON.parse(app.calls[0].options.body.get('payload')).samples;
  assert.equal(samples.length, 20);
  assert.deepEqual(Object.keys(samples[0]).sort(), ['duration', 'metric', 'node', 'status']);
  assert.equal(samples[0].node, 'editor');
  assert.equal(app.queued().length, 80);
});

test('failed background reports retain samples and back off before retrying', async () => {
  const app = browser();
  app.add(50);
  app.fail(true);
  await app.fire(15000);
  assert.equal(app.queued().length, 1);
  app.fail(false);
  await app.fire(30000);
  assert.equal(app.queued().length, 0);
});

test('403 clears queued samples and stops retrying', async () => {
  const app = browser();
  app.add(50);
  app.reply(403);
  await app.fire(15000);
  assert.equal(app.queued().length, 0);
  assert.equal(app.timers.size, 0);
});

test('blocked browser storage and network failures preserve business fetch behavior', async () => {
  const app = browser({storageFails: true});
  app.fail(true);
  await assert.rejects(app.context.window.fetch('/my-schedule/experiences/private-id/draft', {method: 'POST'}),
    /network unavailable/);
  app.fail(false);
  await app.fire(15000);
  const report = app.calls.find(call => call.url === '/my-schedule/telemetry');
  const sample = JSON.parse(report.options.body.get('payload')).samples[0];
  assert.equal(sample.node, 'draft');
  assert.equal(sample.status, 0);
});

test('telemetry and administrator fetches never collect themselves', async () => {
  const app = browser();
  await app.context.window.fetch('/my-schedule/admin/performance');
  await app.context.window.fetch('/my-schedule/telemetry', {method: 'POST'});
  assert.equal(app.queued().length, 0);
});
