(() => {
  const panel = document.querySelector('[data-performance-dashboard]');
  if (!panel) return;
  const status = panel.querySelector('[data-performance-status]');
  const range = panel.querySelector('[data-performance-range]');
  const refresh = panel.querySelector('[data-performance-refresh]');
  const sourceName = source => source === 'server' ? '服务端' : '浏览器';
  const ms = value => `${Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 1})} ms`;
  const date = value => new Date(value * 1000).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function table(target, headings, rows) {
    target.replaceChildren();
    if (!rows.length) { target.append(element('p', '暂无样本', 'admin-performance-empty')); return; }
    const table = element('table'), head = element('thead'), tr = element('tr'), body = element('tbody');
    headings.forEach(heading => tr.append(element('th', heading)));
    head.append(tr);
    rows.forEach(values => {
      const row = element('tr');
      values.forEach(value => row.append(element('td', value)));
      body.append(row);
    });
    table.append(head, body);
    target.append(table);
  }
  function render(data) {
    const requests = data.groups.filter(row => row.metric === 'request');
    const totals = panel.querySelector('[data-performance-totals]');
    totals.replaceChildren();
    for (const [label, value] of [['服务端请求样本', data.server_count], ['浏览器请求样本', data.browser_count],
      ['服务端错误样本', data.errors], ['主线程长任务', data.longtasks]]) {
      const card = element('div', undefined, 'admin-total');
      card.append(element('span', label), element('strong', value));
      totals.append(card);
    }
    const nodes = panel.querySelector('[data-performance-nodes]');
    nodes.replaceChildren();
    const maximum = Math.max(1, ...requests.map(row => row.p95));
    for (const row of requests.slice(0, 12)) {
      const item = element('div', undefined, 'admin-performance-node');
      const heading = element('div');
      heading.append(element('span', `${row.node} · ${sourceName(row.source)}`), element('strong', ms(row.p95)));
      const track = element('div', undefined, 'admin-performance-track');
      const bar = element('i', undefined, row.source);
      bar.style.width = `${Math.max(.5, row.p95 * 100 / maximum)}%`;
      track.append(bar);
      item.append(heading, track);
      nodes.append(item);
    }
    if (!requests.length) nodes.append(element('p', '暂无请求样本', 'admin-performance-empty'));
    const trend = panel.querySelector('[data-performance-trend]');
    trend.replaceChildren();
    if (data.trend.some(row => row.count)) {
      const chart = element('div', undefined, 'admin-performance-trend');
      chart.setAttribute('role', 'img');
      chart.setAttribute('aria-label', '请求 P95 趋势，青色服务端，蓝色浏览器，悬停查看时段和数值');
      const peak = Math.max(1, ...data.trend.flatMap(row => [row.server, row.browser]));
      data.trend.forEach((row, index) => {
        const column = element('div');
        column.title = `${date(row.received)} · ${row.count} 条 · 服务端 ${ms(row.server)} · 浏览器 ${ms(row.browser)}`;
        const bars = element('div');
        for (const source of ['server', 'browser']) {
          const bar = element('i', undefined, source);
          bar.style.height = `${row[source] * 100 / peak}%`;
          bars.append(bar);
        }
        column.append(bars, element('small', index % 6 === 0 || index === 23 ? date(row.received).slice(-5) : ''));
        chart.append(column);
      });
      trend.append(chart);
    } else trend.append(element('p', '暂无趋势数据', 'admin-performance-empty'));
    const columns = ['节点', '来源', '样本', 'P50', 'P95', '最大', '错误'];
    const values = row => [row.node, sourceName(row.source), row.count, ms(row.p50), ms(row.p95), ms(row.max), row.errors];
    table(panel.querySelector('[data-performance-requests]'), columns, requests.map(values));
    table(panel.querySelector('[data-performance-phases]'),
      ['节点', '阶段', '样本', 'P50', 'P95', '最大'], data.groups.filter(row => row.source === 'server' && row.metric !== 'request')
        .map(row => [row.node, row.metric_label, row.count, ms(row.p50), ms(row.p95), ms(row.max)]));
    table(panel.querySelector('[data-performance-page]'),
      ['节点', '指标', '样本', 'P50', 'P95', '最大'], data.groups.filter(row => row.source === 'browser' && row.metric !== 'request')
        .map(row => [row.node, row.metric_label, row.count, ms(row.p50), ms(row.p95), ms(row.max)]));
    table(panel.querySelector('[data-performance-slow]'), ['接收时间', '节点', '来源', '指标', '耗时', '状态'],
      data.slow.map(row => [date(row.received), row.node, sourceName(row.source), row.metric, ms(row.duration),
        row.metric_key === 'request' ? row.status === 0 ? '网络失败' : row.status : '—']));
    status.textContent = !data.enabled ? '性能采集已关闭。' :
      `${data.ready ? '采集存储正常' : '存储暂不可用或正在初始化'} · 排队 ${data.queued} 条 · 本进程丢弃 ${data.dropped} 条 · 写入失败 ${data.write_failures} 次 · 更新于 ${new Date().toLocaleTimeString('zh-CN')}`;
  }
  let loading = false;
  async function load() {
    if (loading) return;
    loading = true;
    refresh.disabled = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`/my-schedule/admin/performance?hours=${range.value}`, {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403 || response.redirected)
        throw new Error('管理员会话已失效，请重新登录');
      if (!response.ok) throw new Error('暂时无法读取性能数据，请稍后刷新');
      render(await response.json());
    } catch (error) { status.textContent = error.name === 'AbortError' ? '读取超时，可点击刷新重试。' : error.message; }
    finally { clearTimeout(timeout); loading = false; refresh.disabled = false; }
  }
  range.addEventListener('change', load);
  refresh.addEventListener('click', load);
  setInterval(() => { if (!document.hidden && panel.isConnected) load(); }, 60000);
  load();
})();
