(() => {
  const panel = document.querySelector('[data-experience-editor]');
  if (!panel) return;
  let editorMode = panel.dataset.editorMode || 'manual';
  const seed = JSON.parse(panel.querySelector('[data-experience-seed]').textContent);
  const content = panel.querySelector('.experience-content');
  const composer = panel.querySelector('.experience-composer');
  const status = panel.querySelector('.experience-draft-status');
  const saveButton = panel.querySelector('[data-experience-save-now]');
  const returnsToList = panel.classList.contains('experience-detail-page');
  const labels = { project: '项目问题', fundamentals: '八股问题', algorithm: '算法题', other: '其他', reverse: '反问' };
  const key = `experience-draft:${panel.dataset.experienceId}`;
  let questions = seed.questions;
  let categoryMinutes = seed.category_minutes || {};
  let totalMinutes = seed.total_minutes ?? null;
  let feeling = seed.feeling || '';
  let rawText = seed.raw_text_draft || '';
  let version = seed.version;
  let category = panel.querySelector('.experience-tab.active')?.dataset.experienceCategory || 'all';
  const stylePreferenceKey = 'interview-experience-style-v3';
  let style = 'lines';
  try { style = localStorage.getItem(stylePreferenceKey) === 'cards' ? 'cards' : 'lines'; }
  catch { /* Browser storage may be disabled. */ }
  panel.dataset.experienceStyle = style;
  let followupParentId = null;
  let inlineRootText = '';
  let inlineFollowupText = '';
  let dirty = false, saving = false, conflict = false, revision = 0, timer = null, localTimer = null;
  let saveInFlight = null, navigating = false;
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
  const persistLocal = () => {
    try { sessionStorage.setItem(key, JSON.stringify({ version, questions, categoryMinutes, totalMinutes, feeling, rawText })); } catch { /* optional cache */ }
  };
  const scheduleLocal = () => {
    if (localTimer) clearTimeout(localTimer);
    localTimer = setTimeout(() => { localTimer = null; persistLocal(); }, 1000);
  };
  const schedule = () => {
    if (!timer && !saving && !conflict) timer = setTimeout(() => { timer = null; save(); }, 60000);
  };
  const changed = () => {
    dirty = true; revision += 1; scheduleLocal(); schedule();
    status.textContent = '未保存 · 1 分钟内自动保存';
    saveButton.disabled = false;
  };
  try {
    const local = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (local?.version === version && Array.isArray(local.questions)) {
      questions = local.questions;
      categoryMinutes = local.categoryMinutes || categoryMinutes;
      totalMinutes = Object.hasOwn(local, 'totalMinutes') ? local.totalMinutes : totalMinutes;
      feeling = Object.hasOwn(local, 'feeling') ? local.feeling : feeling;
      rawText = Object.hasOwn(local, 'rawText') ? local.rawText : rawText;
      dirty = true; saveButton.disabled = false;
      status.textContent = '已恢复未保存的草稿'; schedule();
    }
  } catch { /* ignore invalid cache */ }
  async function save() {
    if (saveInFlight) return saveInFlight;
    if (!dirty || conflict) return !dirty;
    if (timer) clearTimeout(timer);
    timer = null; saving = true; saveButton.disabled = true;
    status.textContent = '保存中…';
    const currentRevision = revision;
    const form = new FormData();
    form.set('csrf_token', panel.dataset.csrfToken || '');
    form.set('payload', JSON.stringify({ version, questions, category_minutes: categoryMinutes, total_minutes: totalMinutes, feeling, raw_text_draft: rawText }));
    saveInFlight = (async () => {
      try {
        const response = await fetch(`/my-schedule/experiences/${panel.dataset.experienceId}/draft`, {
          method: 'POST', body: form, credentials: 'same-origin', headers: { Accept: 'application/json' },
        });
        const result = response.headers.get('content-type')?.includes('application/json')
          ? await response.json().catch(() => ({})) : {};
        if (!response.ok) {
          if (response.status === 409) conflict = true;
          throw new Error(typeof result.detail === 'string' ? result.detail : `保存失败（${response.status}）`);
        }
        version = result.version;
        if (typeof BroadcastChannel === 'function') {
          try {
            const channel = new BroadcastChannel('awesome-interview-pages');
            channel.postMessage('invalidate');
            channel.close();
          } catch { /* Cache invalidation is optional. */ }
        }
        if (currentRevision === revision) {
          if (localTimer) clearTimeout(localTimer);
          localTimer = null;
          questions = result.questions;
          categoryMinutes = result.category_minutes || {};
          totalMinutes = result.total_minutes ?? null;
          feeling = result.feeling || '';
          rawText = result.raw_text_draft || '';
          dirty = false; sessionStorage.removeItem(key);
          status.textContent = `已保存 ${new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())}`;
        } else { persistLocal(); status.textContent = '仍有未保存的修改'; }
        return true;
      } catch (error) {
        status.textContent = `${error.message}；草稿保留在本页`;
        return false;
      } finally {
        saving = false; saveButton.disabled = conflict || (!returnsToList && !dirty);
        if (dirty && !conflict) schedule();
      }
    })();
    try { return await saveInFlight; }
    finally { saveInFlight = null; }
  }
  async function ensureSaved() {
    while (dirty || saving) {
      if (!await save()) return false;
    }
    return true;
  }
  saveButton.addEventListener('click', async () => {
    if (returnsToList) {
      if (await ensureSaved()) location.assign('/my-schedule/experiences');
    } else await save();
  });
  if (returnsToList) {
    const hint = panel.querySelector('[data-experience-edit-hint]');
    const openHint = () => { if (hint && !hint.open) hint.showModal(); };
    panel.querySelector('[data-experience-edit-hint-open]')?.addEventListener('click', openHint);
    panel.querySelector('[data-experience-edit-hint-close]')?.addEventListener('click', () => hint.close());
    if (hint && editorMode === 'manual') {
      try {
        if (!localStorage.getItem('experience-edit-hint-shown')) {
          setTimeout(openHint, 200);
          localStorage.setItem('experience-edit-hint-shown', '1');
        }
      } catch { setTimeout(openHint, 200); }
    }
  }
  window.addEventListener('beforeunload', (event) => {
    if (dirty) { persistLocal(); event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('click', async (event) => {
    const link = event.target.closest('a[href]');
    if (!link || !dirty && !saving || event.defaultPrevented || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const destination = new URL(link.href, location.href);
    if (destination.origin !== location.origin || destination.pathname === location.pathname && destination.search === location.search) return;
    event.preventDefault();
    if (navigating) return;
    navigating = true;
    try { if (await ensureSaved()) location.assign(destination.href); }
    finally { navigating = false; }
  });
  panel.querySelector('[data-experience-settings-form]')?.addEventListener('submit', async (event) => {
    if (!dirty && !saving) return;
    event.preventDefault();
    if (await ensureSaved()) event.target.submit();
  });
  const tree = () => {
    const groups = new Map(), result = [];
    questions.forEach((item) => {
      const parent = item.parent_question_id || null;
      if (!groups.has(parent)) groups.set(parent, []);
      groups.get(parent).push(item);
    });
    groups.forEach((group) => group.sort((a, b) => a.sibling_order - b.sibling_order || a.asked_order - b.asked_order));
    const visit = (parent, prefix, depth) => (groups.get(parent) || []).forEach((item, index, siblings) => {
      const number = prefix ? `${prefix}.${index + 1}` : `Q${index + 1}`;
      result.push({ item, number, depth, index, siblings });
      visit(item.id, number, depth + 1);
    });
    visit(null, '', 0);
    return result;
  };
  const durationInput = panel.querySelector('[data-experience-duration]');
  const durationLabel = panel.querySelector('[data-experience-duration-label]');
  const durationHint = panel.querySelector('[data-experience-duration-hint]');
  const moduleSum = () => Object.values(categoryMinutes).reduce((sum, value) => sum + value, 0);
  const effectiveTotal = () => totalMinutes ?? (Object.keys(categoryMinutes).length ? moduleSum() : null);
  function updateDurationUI() {
    panel.querySelectorAll('[data-experience-category]').forEach((tab) => {
      const badge = tab.querySelector('[data-duration-badge]');
      if (badge) {
        const minutes = tab.dataset.experienceCategory === 'all' ? effectiveTotal() : categoryMinutes[tab.dataset.experienceCategory];
        badge.textContent = minutes == null ? '' : ` · ${minutes} min`;
      }
    });
    durationLabel.textContent = category === 'all' ? '全部用时' : `${labels[category]}用时`;
    durationInput.value = category === 'all' ? (totalMinutes ?? '') : (categoryMinutes[category] ?? '');
    durationInput.setAttribute('aria-label', `${durationLabel.textContent}（分钟，可选）`);
    durationHint.textContent = category === 'all'
      ? (Object.keys(categoryMinutes).length ? `各模块合计 ${moduleSum()} 分钟；全部用时可单独填写` : '留空时按已填写的模块用时合计')
      : '留空表示未记录';
  }
  const questionViewMarkup = (item, number, meta) => `
    <div class="experience-question-top"><span class="experience-question-number">${escape(number)}</span><span class="experience-question-text" data-editable="question_text" title="双击编辑问题">${escape(item.question_text)}</span></div>
    ${meta ? `<div class="experience-question-meta">${escape(meta)}</div>` : ''}
    ${item.category === 'reverse' && item.interviewer_answer ? `<div class="experience-answer interviewer"><strong>面试官回答</strong><p data-editable="interviewer_answer" title="双击编辑面试官回答">${escape(item.interviewer_answer)}</p></div>` : ''}
    ${item.category !== 'reverse' && item.on_site_answer ? `<div class="experience-answer"><strong>现场回答</strong><p data-editable="on_site_answer" title="双击编辑现场回答">${escape(item.on_site_answer)}</p></div>` : ''}
    ${item.category !== 'reverse' && item.review_answer ? `<div class="experience-answer review"><strong>复盘答案</strong><p data-editable="review_answer" title="双击编辑复盘答案">${escape(item.review_answer)}</p></div>` : ''}`;
  const addAnswerMarkup = (item, actionAttribute) => item.category === 'reverse'
    ? (!item.interviewer_answer ? `<button type="button" class="experience-text-button" ${actionAttribute}="add-answer" data-field="interviewer_answer">添加面试官回答</button>` : '')
    : `${!item.on_site_answer ? `<button type="button" class="experience-text-button" ${actionAttribute}="add-answer" data-field="on_site_answer">添加现场回答</button>` : ''}${!item.review_answer ? `<button type="button" class="experience-text-button" ${actionAttribute}="add-answer" data-field="review_answer">添加复盘答案</button>` : ''}`;
  function render() {
    panel.dataset.experienceView = category;
    const rows = tree(), byId = new Map(rows.map((row) => [row.item.id, row]));
    const visible = category === 'all' ? [...rows].sort((a, b) => a.item.asked_order - b.item.asked_order)
      : rows.filter((row) => row.item.category === category);
    panel.querySelectorAll('[data-experience-category]').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.experienceCategory === category);
      const count = tab.querySelector('span');
      if (count) count.textContent = tab.dataset.experienceCategory === 'all' ? questions.length
        : questions.filter((item) => item.category === tab.dataset.experienceCategory).length;
    });
    if (category === 'feeling') {
      content.innerHTML = `<div class="experience-feeling-editor"><label for="experience-feeling-input">面试感受</label><p>记录面试氛围、自己的状态，以及值得复盘的观察。此内容会显示在导出标题下方。</p><textarea id="experience-feeling-input" data-experience-feeling maxlength="20000" rows="12" placeholder="记录这场面试的整体感受…">${escape(feeling)}</textarea></div>`;
      return;
    }
    updateDurationUI();
    if (!visible.length && style !== 'lines') {
      content.innerHTML = '<div class="interview-questions-empty"><span class="interview-questions-empty-icon">✎</span><h2>还没有问题记录</h2><p>可在下方记录主问题，再从题目下添加追问。</p></div>';
      return;
    }
    const questionMarkup = ({ item, number, depth, index, siblings }, children = '') => `
      <li class="experience-question" data-id="${escape(item.id)}" data-depth="${style === 'cards' && category === 'all' ? 0 : depth}" style="--question-depth:${style === 'cards' && category === 'all' ? 0 : depth}">
        ${questionViewMarkup(item, number, category === 'all' ? `${labels[item.category]}${item.parent_question_id ? ` · 追问 ${byId.get(item.parent_question_id)?.number || '?'}` : ''} · 第 ${item.asked_order} 问` : '')}
        <div class="experience-question-actions">
          ${addAnswerMarkup(item, 'data-action')}
          ${style === 'lines'
            ? '<button type="button" class="experience-text-button" data-action="followup">添加追问</button>'
            : `<details><summary>添加追问</summary><form data-follow-up class="experience-small-form"><textarea required maxlength="2000" placeholder="记录对 ${number} 的追问"></textarea><button class="btn small" type="submit">加入草稿</button></form></details>`}
          ${!item.parent_question_id ? `<select class="experience-question-category" data-field="category" aria-label="更改 ${number} 分类">${Object.entries(labels).map(([value, label]) => `<option value="${value}" ${item.category === value ? 'selected' : ''}>${label}</option>`).join('')}</select>` : ''}
          ${index > 0 ? '<button type="button" class="experience-text-button" data-action="up">上移</button>' : ''}
          ${index < siblings.length - 1 ? '<button type="button" class="experience-text-button" data-action="down">下移</button>' : ''}
          <button type="button" class="experience-text-button danger" data-action="delete">删除</button>
        </div>
        ${children}
      </li>`;
    const inlineMarkup = (parentId = null) => {
      const isFollowup = Boolean(parentId);
      const text = isFollowup ? inlineFollowupText : inlineRootText;
      const label = isFollowup ? '在这里记录追问' : '在这里新建问题';
      return `<li class="experience-inline-add">
        <form data-inline-question data-parent-id="${escape(parentId || '')}" class="experience-inline-form">
          <textarea rows="1" maxlength="2000" required aria-label="${label}" placeholder="${label}…">${escape(text)}</textarea>
          ${!isFollowup && category === 'all' ? `<select aria-label="新问题分类">${Object.entries(labels).map(([value, name]) => `<option value="${value}" ${composer.elements.category.value === value ? 'selected' : ''}>${name}</option>`).join('')}</select>` : ''}
          <button type="submit" class="experience-inline-submit">加入草稿</button>
          ${isFollowup ? '<button type="button" class="experience-inline-cancel" data-action="cancel-followup">取消</button>' : ''}
        </form>
      </li>`;
    };
    if (style === 'lines' && category !== 'all') {
      const nested = (parentId) => {
        const children = rows.filter((row) => row.item.parent_question_id === parentId && row.item.category === category);
        const inline = parentId ? (followupParentId === parentId ? inlineMarkup(parentId) : '') : inlineMarkup();
        if (!children.length && !inline) return '';
        return `<ol class="experience-question-list${parentId ? ' nested' : ''}">${children.map((row) => questionMarkup(row, nested(row.item.id))).join('')}${inline}</ol>`;
      };
      content.innerHTML = nested(null);
    } else {
      content.innerHTML = `<ol class="experience-question-list${style === 'lines' ? ' chronological' : ''}">${visible.map((row) => questionMarkup(row)).join('')}${style === 'lines' ? inlineMarkup() : ''}</ol>`;
    }
  }
  durationInput.addEventListener('change', () => {
    const raw = durationInput.value.trim();
    const minutes = raw === '' ? null : Number(raw);
    if (minutes !== null && (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440)) {
      durationInput.setCustomValidity('请输入 0 到 1440 之间的整数分钟数');
      durationInput.reportValidity();
      return;
    }
    durationInput.setCustomValidity('');
    if (category === 'all') {
      if (totalMinutes === minutes) return;
      totalMinutes = minutes;
    } else {
      if (minutes === null) {
        if (!(category in categoryMinutes)) return;
        delete categoryMinutes[category];
      } else {
        if (categoryMinutes[category] === minutes) return;
        categoryMinutes[category] = minutes;
      }
    }
    changed();
    updateDurationUI();
  });
  function add(text, selectedCategory, parent = null) {
    const siblings = questions.filter((item) => item.parent_question_id === parent);
    questions.push({ id: crypto.randomUUID(), parent_question_id: parent,
      category: parent ? questions.find((item) => item.id === parent).category : selectedCategory,
      question_text: text.trim(), on_site_answer: null, review_answer: null, interviewer_answer: null,
      asked_order: Math.max(0, ...questions.map((item) => item.asked_order)) + 1,
      sibling_order: Math.max(0, ...siblings.map((item) => item.sibling_order || 0)) + 1 });
    changed(); render();
  }
  composer.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = composer.elements.question_text;
    if (input.value.trim()) { add(input.value, composer.elements.category.value); input.value = ''; input.focus(); }
  });
  composer.addEventListener('focusout', (event) => {
    if (composer.contains(event.relatedTarget)) return;
    const input = composer.elements.question_text;
    if (input.value.trim()) { const value = input.value; input.value = ''; add(value, composer.elements.category.value); }
  });
  composer.elements.category.addEventListener('change', () => {
    const input = composer.elements.question_text;
    if (input.value.trim()) { const value = input.value; input.value = ''; add(value, composer.elements.category.value); }
  });
  const commitInline = (inline) => {
    if (!inline.isConnected) return;
    const input = inline.querySelector('textarea');
    if (!input.value.trim()) return;
    const parent = inline.dataset.parentId || null;
    const selectedCategory = parent ? questions.find((item) => item.id === parent)?.category
      : (inline.querySelector('select')?.value || category);
    const value = input.value;
    inlineRootText = ''; inlineFollowupText = ''; followupParentId = null;
    add(value, selectedCategory === 'all' ? composer.elements.category.value : selectedCategory, parent);
  };
  content.addEventListener('focusout', (event) => {
    const inline = event.target.closest('[data-inline-question]');
    if (inline && !inline.contains(event.relatedTarget)) commitInline(inline);
  });
  content.addEventListener('submit', (event) => {
    const inline = event.target.closest('[data-inline-question]');
    if (inline) {
      event.preventDefault();
      commitInline(inline);
      return;
    }
    const form = event.target.closest('[data-follow-up]');
    if (!form) return;
    event.preventDefault();
    const text = form.querySelector('textarea').value;
    const parent = form.closest('[data-id]').dataset.id;
    if (text.trim()) add(text, questions.find((item) => item.id === parent).category, parent);
  });
  content.addEventListener('input', (event) => {
    if (event.target.matches('[data-experience-feeling]')) {
      feeling = event.target.value;
      changed();
      const preview = panel.querySelector('[data-experience-feeling-preview]');
      if (preview) { preview.textContent = feeling.trim(); preview.hidden = !feeling.trim(); }
      return;
    }
    if (event.target.matches('[data-inline-question] textarea')) {
      if (event.target.closest('[data-inline-question]').dataset.parentId) inlineFollowupText = event.target.value;
      else inlineRootText = event.target.value;
      return;
    }
    const field = event.target.dataset.field;
    if (!field) return;
    const item = questions.find((question) => question.id === event.target.closest('[data-id]').dataset.id);
    item[field] = event.target.value;
    if (field === 'category') {
      const propagate = (id) => questions.filter((child) => child.parent_question_id === id)
        .forEach((child) => { child.category = item.category; propagate(child.id); });
      propagate(item.id);
    }
    changed();
    if (field === 'category') render();
  });
  content.addEventListener('change', (event) => {
    if (event.target.matches('[data-inline-question] select')) {
      commitInline(event.target.closest('[data-inline-question]'));
      return;
    }
    if (event.target.dataset.field === 'category') event.target.dispatchEvent(new Event('input', { bubbles: true }));
  });
  function beginInlineEdit(container, target, field, item, commit, redraw) {
    if (container.querySelector('[data-inline-editor]')) return;
    const original = item[field] || '';
    const editor = document.createElement('textarea');
    editor.dataset.inlineEditor = field;
    editor.className = 'experience-inline-editor';
    editor.value = original;
    editor.maxLength = field === 'question_text' ? 2000 : 20000;
    editor.rows = field === 'question_text' ? 2 : 3;
    editor.setAttribute('aria-label', field === 'question_text' ? '编辑问题' : `编辑${field === 'interviewer_answer' ? '面试官回答' : field === 'review_answer' ? '复盘答案' : '现场回答'}`);
    if (target.dataset.action === 'add-answer') {
      target.after(editor);
      target.hidden = true;
    } else target.replaceWith(editor);
    editor.focus(); editor.select();
    let finished = false;
    const finish = (cancel = false) => {
      if (finished) return;
      finished = true;
      const value = editor.value.trim();
      if (!cancel && (field !== 'question_text' || value) && value !== original) {
        item[field] = value || null;
        commit();
      }
      redraw();
    };
    editor.addEventListener('blur', () => finish());
    editor.addEventListener('keydown', (keyEvent) => {
      if (keyEvent.key === 'Escape') { keyEvent.preventDefault(); finish(true); }
      if (field === 'question_text' && keyEvent.key === 'Enter' && !keyEvent.shiftKey) {
        keyEvent.preventDefault(); finish();
      }
    });
  }
  function startInlineEdit(target, field) {
    const row = target.closest('[data-id]');
    const item = questions.find((question) => question.id === row.dataset.id);
    beginInlineEdit(content, target, field, item, changed, render);
  }
  content.addEventListener('dblclick', (event) => {
    const target = event.target.closest('[data-editable]');
    if (target) startInlineEdit(target, target.dataset.editable);
  });
  content.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    if (button.dataset.action === 'cancel-followup') {
      followupParentId = null;
      inlineFollowupText = '';
      render();
      return;
    }
    const row = button.closest('[data-id]');
    const item = questions.find((question) => question.id === row.dataset.id);
    const action = button.dataset.action;
    if (action === 'add-answer') {
      startInlineEdit(button, button.dataset.field);
      return;
    }
    if (action === 'followup') {
      if (category === 'all' && (dirty || saving) && !await ensureSaved()) return;
      followupParentId = item.id;
      inlineFollowupText = '';
      if (category === 'all') category = item.category;
      composer.elements.category.value = item.category;
      render();
      content.querySelector(`[data-inline-question][data-parent-id="${item.id}"] textarea`)?.focus();
      return;
    }
    if (action === 'delete') {
      if (!confirm('删除这道题及其所有追问？修改将在下一次自动保存时生效。')) return;
      const ids = new Set([item.id]);
      let before;
      do { before = ids.size; questions.forEach((q) => { if (ids.has(q.parent_question_id)) ids.add(q.id); }); }
      while (before !== ids.size);
      questions = questions.filter((q) => !ids.has(q.id));
    } else {
      const siblings = questions.filter((q) => q.parent_question_id === item.parent_question_id)
        .sort((a, b) => a.sibling_order - b.sibling_order);
      const index = siblings.findIndex((q) => q.id === item.id);
      const target = siblings[index + (action === 'up' ? -1 : 1)];
      [item.sibling_order, target.sibling_order] = [target.sibling_order, item.sibling_order];
    }
    changed(); render();
  });
  panel.querySelectorAll('[data-experience-category]').forEach((tab) => {
    tab.addEventListener('click', async () => {
      if ((dirty || saving) && !await ensureSaved()) return;
      category = tab.dataset.experienceCategory;
      if (category !== 'feeling') composer.elements.category.value = category === 'all' ? 'project' : category;
      render();
    });
  });
  panel.querySelectorAll('[data-experience-style-choice]').forEach((button) => {
    button.addEventListener('click', async () => {
      if ((dirty || saving) && !await ensureSaved()) return;
      style = button.dataset.experienceStyleChoice;
      panel.dataset.experienceStyle = style;
      panel.querySelectorAll('[data-experience-style-choice]').forEach((choice) => {
        choice.setAttribute('aria-pressed', String(choice === button));
      });
      try { localStorage.setItem(stylePreferenceKey, style); } catch { /* optional preference */ }
      render();
    });
    button.setAttribute('aria-pressed', String(button.dataset.experienceStyleChoice === style));
  });
  const layoutPanel = panel.matches('.interview-questions-panel') ? panel : panel.querySelector('.interview-questions-panel');
  const parserSource = panel.querySelector('[data-parser-source]');
  const parserStatus = panel.querySelector('[data-parser-status]');
  const parserRows = panel.querySelector('[data-parser-preview-rows]');
  const parserUnknown = panel.querySelector('[data-parser-unrecognized]');
  const parserPreviewKey = `experience-parse-preview:${panel.dataset.experienceId}`;
  let parsed = null;
  let parsedCategory = 'all';
  let parseCurrentSource = null;
  if (parserSource) {
    parserSource.value = rawText;
    let parsedSource = null;
    let liveTimer = null;
    let parseVersion = 0;
    try {
      const cached = JSON.parse(sessionStorage.getItem(parserPreviewKey) || 'null');
      if (cached?.source === rawText && Array.isArray(cached.parsed?.questions)) {
        parsed = cached.parsed;
        parsedSource = rawText;
      }
    } catch { /* ignore invalid preview cache */ }
    const persistPreview = () => {
      try {
        if (parsed && parsedSource === rawText) sessionStorage.setItem(parserPreviewKey, JSON.stringify({ source: rawText, parsed }));
        else sessionStorage.removeItem(parserPreviewKey);
      } catch { /* optional cache */ }
    };
    parserSource.addEventListener('input', () => {
      rawText = parserSource.value;
      parsedSource = null;
      panel.querySelector('[data-parser-import-area]').hidden = true;
      if (liveTimer) clearTimeout(liveTimer);
      parseVersion += 1;
      if (editorMode === 'write') {
        parserStatus.textContent = rawText.trim() ? '正在更新右侧预览…' : '输入内容后自动生成预览';
        if (rawText.trim()) liveTimer = setTimeout(() => parseSource(true), 700);
        else { parsed = null; renderParsed(); }
      } else {
        parsed = null;
        renderParsed();
        parserStatus.textContent = '原文已修改，请重新解析';
      }
      persistPreview();
      changed();
    });
    const renderParsed = () => {
      panel.querySelector('[data-parser-empty]').hidden = Boolean(parsed);
      panel.querySelector('[data-parser-import-area]').hidden = !parsed || parsedSource !== rawText;
      if (!parsed) {
        parserRows.innerHTML = '';
        parserUnknown.hidden = true;
        return;
      }
      const summary = `<div class="experience-parsed-summary"><strong>识别摘要 · ${parsed.questions.length} 道问题</strong><div class="experience-parsed-metadata"><label>标题<input data-parsed-meta="title" maxlength="200" value="${escape(parsed.title || '')}" placeholder="未识别"></label><label>公司<input data-parsed-meta="company" maxlength="200" value="${escape(parsed.company || '')}" placeholder="未识别"></label><label>岗位<input data-parsed-meta="position" maxlength="200" value="${escape(parsed.position || '')}" placeholder="未识别"></label><label>面试时间<input data-parsed-meta="interviewed_at" type="datetime-local" value="${escape(parsed.interviewed_at || '')}"></label></div><p>${parsed.feeling ? '已识别面试感受' : '未识别面试感受'} · ${Object.entries(parsed.category_minutes).map(([key, value]) => `${labels[key]} ${value} min`).join(' · ') || '未识别模块用时'}</p></div>`;
      const tabs = `<div class="experience-tabs experience-preview-tabs" aria-label="解析结果分类"><button type="button" data-parsed-category="all" class="experience-tab ${parsedCategory === 'all' ? 'active' : ''}">全部 <span>${parsed.questions.length}</span></button>${Object.entries(labels).map(([key, label]) => `<button type="button" data-parsed-category="${key}" class="experience-tab ${parsedCategory === key ? 'active' : ''}">${label} <span>${parsed.questions.filter((item) => item.category === key).length}</span></button>`).join('')}</div>`;
      parserRows.innerHTML = summary + tabs + `<ol class="experience-question-list chronological experience-parsed-list">${parsed.questions.map((item, index) => ({ item, index })).filter(({ item }) => parsedCategory === 'all' || item.category === parsedCategory).map(({ item, index }) => `
        <li class="experience-question" data-parsed-index="${index}" data-depth="${Math.max(0, item.number.split('.').length - 1)}" style="--question-depth:${Math.max(0, item.number.split('.').length - 1)}">
          ${questionViewMarkup(item, `Q${item.number}`, `${labels[item.category]} · 原文第 ${item.source_line} 行${item.needs_parent_review ? ' · 上级问题待确认' : ''}`)}
          <div class="experience-question-actions">
            ${addAnswerMarkup(item, 'data-parser-action')}
            <details class="experience-parsed-adjust"><summary>调整分类与层级</summary><div class="experience-parsed-options"><label>分类<select data-parsed-field="category">${Object.entries(labels).map(([value, label]) => `<option value="${value}" ${value === item.category ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label>上级问题<select data-parsed-field="parent_question_id"><option value="">主问题</option>${parsed.questions.slice(0, index).map((candidate) => `<option value="${candidate.id}" ${candidate.id === item.parent_question_id ? 'selected' : ''}>${escape(candidate.number)} ${escape(candidate.question_text.slice(0, 25))}</option>`).join('')}</select></label></div></details>
            <button type="button" class="experience-text-button danger" data-parser-remove="${index}">移除此题</button>
          </div>
        </li>`).join('')}</ol>`;
      const messages = [...parsed.warnings, ...parsed.unrecognized.map((line) => `第 ${line.line} 行未识别：${line.text}`)];
      parserUnknown.hidden = !messages.length;
      parserUnknown.innerHTML = messages.length ? `<strong>需要核对的原文</strong><ul>${messages.map((message) => `<li>${escape(message)}</li>`).join('')}</ul>` : '';
    };
    const showParsed = (result, source = rawText) => {
      if (source !== rawText) {
        rawText = source;
        parserSource.value = source;
        changed();
      }
      parsed = result;
      parsedSource = source;
      parsedCategory = 'all';
      persistPreview();
      renderParsed();
      parserStatus.textContent = `识别 ${result.questions.length} 道问题；请核对后导入`;
    };
    const parseSource = async (live = false) => {
      if (!rawText.trim()) { parserStatus.textContent = '请先输入面经原文'; return; }
      const source = rawText;
      const requestVersion = ++parseVersion;
      parserStatus.textContent = live ? '正在更新右侧预览…' : '正在解析…';
      const form = new FormData();
      form.set('csrf_token', panel.dataset.csrfToken || '');
      form.set('source', source);
      try {
        const response = await fetch(`/my-schedule/experiences/${panel.dataset.experienceId}/parse`, { method: 'POST', body: form, credentials: 'same-origin' });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || '解析失败');
        if (requestVersion === parseVersion && source === rawText) showParsed(result, source);
      } catch (error) {
        if (requestVersion === parseVersion) parserStatus.textContent = error.message || '解析失败';
      }
    };
    parseCurrentSource = parseSource;
    panel.querySelector('[data-parser-preview]').addEventListener('click', () => parseSource());
    panel.querySelector('[data-parser-file-preview]')?.addEventListener('click', async () => {
      const file = panel.querySelector('[data-parser-file]').files[0];
      if (!file) { parserStatus.textContent = '请先选择 Markdown 或 PDF 文件'; return; }
      if (file.size > 5 * 1024 * 1024) { parserStatus.textContent = '文件不能超过 5 MB'; return; }
      const requestVersion = ++parseVersion;
      parserStatus.textContent = '正在提取并解析文件…';
      const form = new FormData();
      form.set('csrf_token', panel.dataset.csrfToken || '');
      form.set('file', file);
      try {
        const response = await fetch(`/my-schedule/experiences/${panel.dataset.experienceId}/parse-file`, { method: 'POST', body: form, credentials: 'same-origin' });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || '文件解析失败');
        if (requestVersion !== parseVersion) return;
        showParsed(result, result.source_text);
      } catch (error) { parserStatus.textContent = error.message || '文件解析失败'; }
    });
    parserRows.addEventListener('input', (event) => {
      if (event.target.dataset.parsedMeta) {
        parsed[event.target.dataset.parsedMeta] = event.target.value;
        persistPreview();
        return;
      }
      const row = event.target.closest('[data-parsed-index]');
      if (!row || !parsed || !event.target.dataset.parsedField) return;
      parsed.questions[Number(row.dataset.parsedIndex)][event.target.dataset.parsedField] = event.target.value;
      persistPreview();
    });
    parserRows.addEventListener('change', (event) => {
      if (event.target.dataset.parsedField === 'category' || event.target.dataset.parsedField === 'parent_question_id') renderParsed();
    });
    parserRows.addEventListener('dblclick', (event) => {
      const target = event.target.closest('[data-editable]');
      const row = target?.closest('[data-parsed-index]');
      if (!row || !parsed) return;
      beginInlineEdit(parserRows, target, target.dataset.editable,
        parsed.questions[Number(row.dataset.parsedIndex)], persistPreview, renderParsed);
    });
    parserRows.addEventListener('click', (event) => {
      const tab = event.target.closest('[data-parsed-category]');
      if (tab) { parsedCategory = tab.dataset.parsedCategory; renderParsed(); return; }
      const addAnswer = event.target.closest('[data-parser-action="add-answer"]');
      if (addAnswer && parsed) {
        const row = addAnswer.closest('[data-parsed-index]');
        beginInlineEdit(parserRows, addAnswer, addAnswer.dataset.field,
          parsed.questions[Number(row.dataset.parsedIndex)], persistPreview, renderParsed);
        return;
      }
      const button = event.target.closest('[data-parser-remove]');
      if (!button || !parsed) return;
      const removed = parsed.questions.splice(Number(button.dataset.parserRemove), 1)[0];
      parsed.questions.forEach((item) => { if (item.parent_question_id === removed.id) { item.parent_question_id = null; item.needs_parent_review = true; } });
      persistPreview();
      renderParsed();
    });
    panel.querySelector('[data-parser-import]').addEventListener('click', () => {
      if (!parsed || parsedSource !== rawText || !parsed.questions.length) { parserStatus.textContent = '请先完成当前原文的解析'; return; }
      if (parsed.questions.some((item) => !item.question_text.trim())) { parserStatus.textContent = '请填写所有问题内容'; return; }
      const mode = panel.querySelector('[data-parser-import-mode]').value;
      if (mode === 'replace' && !confirm(`将替换当前 ${questions.length} 道问题，继续吗？`)) return;
      if ((mode === 'append' ? questions.length : 0) + parsed.questions.length > 500) { parserStatus.textContent = '一份面经最多 500 道问题'; return; }
      const imported = parsed.questions.map((item, index) => ({
        id: item.id, parent_question_id: item.parent_question_id || null,
        category: item.category, question_text: item.question_text.trim(),
        on_site_answer: item.category === 'reverse' ? null : item.on_site_answer || null,
        review_answer: item.category === 'reverse' ? null : item.review_answer || null,
        interviewer_answer: item.category === 'reverse' ? item.interviewer_answer || null : null,
        asked_order: (mode === 'append' ? Math.max(0, ...questions.map((question) => question.asked_order)) : 0) + index + 1,
        sibling_order: parsed.questions.slice(0, index + 1).filter((candidate) => candidate.parent_question_id === item.parent_question_id).length,
      }));
      questions = mode === 'replace' ? imported : [...questions, ...imported];
      categoryMinutes = mode === 'replace' ? { ...parsed.category_minutes } : { ...categoryMinutes, ...parsed.category_minutes };
      if (parsed.feeling) feeling = parsed.feeling;
      const settingsForm = panel.querySelector('[data-experience-settings-form]');
      if (settingsForm) {
        for (const field of ['title', 'company', 'position', 'interviewed_at']) {
          if (parsed[field]) settingsForm.elements[field].value = parsed[field];
        }
      }
      parsed = null;
      parsedSource = null;
      persistPreview();
      panel.querySelector('[data-parser-empty]').textContent = '已加入草稿。可切换到“逐题录入”查看和继续编辑。';
      renderParsed();
      parserStatus.textContent = `已加入 ${imported.length} 道问题到草稿；元信息如有变更，请在左侧保存`;
      changed(); render();
    });
    renderParsed();
  }
  const modeCopy = {
    manual: ['面试问题', '输入问题后失焦即加入草稿；双击问题或答案可直接编辑。'],
    write: ['全文录入', '左侧连续输入面经原文，右侧查看结构化预览；确认后加入草稿。'],
    import: ['文件导入', '左侧导入文件并核对提取文本，右侧检查解析结果。'],
  };
  let manualRendered = false;
  function setEditorMode(mode, updateUrl = false) {
    if (!modeCopy[mode] || !parserSource) return;
    editorMode = mode;
    panel.dataset.editorMode = mode;
    layoutPanel.classList.toggle('is-parsing', mode !== 'manual');
    panel.querySelector('[data-editor-heading]').textContent = modeCopy[mode][0];
    panel.querySelector('[data-editor-description]').textContent = modeCopy[mode][1];
    panel.querySelector('[data-parser-heading]').textContent = mode === 'import' ? '文件导入与解析' : '全文录入';
    panel.querySelector('[data-parser-description]').textContent = mode === 'import'
      ? '支持带标题和列表的 Markdown、含文字层的 PDF；提取后可以修正原文再解析。'
      : '连续输入整份面经，停顿后自动更新右侧预览。';
    panel.querySelector('[data-parser-file-controls]').hidden = mode !== 'import';
    panel.querySelector('[data-parser-write-controls]').hidden = mode !== 'write';
    panel.querySelector('[data-parser-source-label]').textContent = mode === 'import' ? '提取的原文（可修正）' : '面经全文';
    parserSource.placeholder = mode === 'import' ? '导入文件后将在这里显示提取的原文…' : '从这里开始连续输入面经内容…';
    panel.querySelector('[data-parser-preview]').textContent = mode === 'import' ? '重新解析原文' : '立即更新预览';
    const empty = panel.querySelector('[data-parser-empty]');
    if (!empty.textContent.trim() || /^(开始输入后|选择文件并)/.test(empty.textContent.trim())) {
      empty.textContent = mode === 'import' ? '选择文件并解析后，结果会显示在这里。' : '开始输入后，解析结果会显示在这里。';
    }
    panel.querySelectorAll('[data-editor-mode-link]').forEach((link) => {
      if (link.dataset.editorModeLink === mode) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (mode === 'manual' && !manualRendered) { render(); manualRendered = true; }
    if (mode === 'write' && rawText.trim() && !parsed) parseCurrentSource?.();
    if (updateUrl) {
      const link = panel.querySelector(`[data-editor-mode-link="${mode}"]`);
      history.pushState({ editorMode: mode }, '', link.href);
    }
  }
  if (parserSource) {
    panel.addEventListener('click', (event) => {
      const link = event.target.closest('[data-editor-mode-link]');
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      if (link.dataset.editorModeLink !== editorMode) setEditorMode(link.dataset.editorModeLink, true);
    });
    window.addEventListener('popstate', () => {
      const base = `/my-schedule/experiences/${panel.dataset.experienceId}`;
      const mode = location.pathname === `${base}/write` ? 'write' : location.pathname === `${base}/import` ? 'import' : 'manual';
      setEditorMode(mode);
    });
    setEditorMode(editorMode);
  } else if (editorMode === 'manual') render();
})();

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches('[data-experience-save]') || form.closest('[data-experience-editor]')) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector('.experience-form-error') || document.createElement('p');
  status.className = 'experience-form-error'; status.setAttribute('role', 'alert'); status.textContent = '';
  if (!status.isConnected) form.append(status);
  if (button) button.disabled = true;
  try {
    const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!response.ok) {
      const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
      status.textContent = typeof body?.detail === 'string' ? body.detail : '保存失败，请重试。'; return;
    }
    const destination = new URL(response.url);
    if (response.redirected && destination.origin === location.origin) location.assign(destination.href);
    else status.textContent = '保存结果无法确认，请刷新页面检查。';
  } catch { status.textContent = '网络连接中断，内容尚未保存，请重试。'; }
  finally { if (button) button.disabled = false; }
});
