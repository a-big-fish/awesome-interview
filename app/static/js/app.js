document.addEventListener('DOMContentLoaded', () => {
  const uploadZone = document.querySelector('[data-upload-zone]');
  const fileInput = document.querySelector('[data-file-input]');
  const fileList = document.querySelector('[data-file-list]');
  const settingsForm = document.querySelector('[data-enterprise-settings-form]');
  settingsForm?.addEventListener('click', event => {
    const add = event.target.closest('[data-add-break]');
    if (add) {
      const weekday = add.dataset.addBreak;
      const list = settingsForm.querySelector(`[data-break-list="${weekday}"]`);
      const row = document.createElement('div');
      row.className = 'settings-break-row';
      for (const [field, label, type] of [
        ['name', '休息名称', 'text'],
        ['start', '休息开始时间', 'time'],
        ['end', '休息结束时间', 'time'],
      ]) {
        const input = document.createElement('input');
        input.className = 'input';
        input.name = `break_${field}_${weekday}`;
        input.type = type;
        input.setAttribute('aria-label', label);
        if (field === 'name') input.placeholder = '名称';
        row.append(input);
      }
      const enabled = document.createElement('select');
      enabled.className = 'input';
      enabled.name = `break_enabled_${weekday}`;
      enabled.setAttribute('aria-label', '休息是否启用');
      enabled.innerHTML = '<option value="on">启用</option><option value="off">停用</option>';
      row.append(enabled);
      const remove = document.createElement('button');
      remove.className = 'btn secondary small';
      remove.type = 'button';
      remove.dataset.removeBreak = '';
      remove.textContent = '移除';
      row.append(remove);
      list.append(row);
      return;
    }
    if (event.target.closest('[data-remove-break]')) {
      event.target.closest('.settings-break-row')?.remove();
    }
  });

  const resumeUploadForm = document.querySelector('[data-resume-upload-form]');
  let resumeSubmitInFlight = false;

  const submitButtons = resumeUploadForm
    ? Array.from(resumeUploadForm.querySelectorAll('[data-primary-submit]'))
    : [];
  const primarySubmitButton = submitButtons[0];
  const fileSelectButton = resumeUploadForm?.querySelector('[data-file-select]');
  const personalSubmitButton = resumeUploadForm?.querySelector('[data-personal-submit]');

  function setResumeUploading(uploading) {
    resumeSubmitInFlight = uploading;
    resumeUploadForm?.classList.toggle('is-uploading', uploading);
    uploadZone?.classList.toggle('is-uploading', uploading);
    submitButtons.forEach(button => {
      button.disabled = uploading;
      if (uploading) {
        button.dataset.originalText = button.textContent;
        button.textContent = '正在解析...';
      } else if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
      }
    });
    if (fileList && uploading) {
      fileList.dataset.previousStatus = fileList.querySelector('.file-status')?.textContent || '';
      const status = fileList.querySelector('.file-status');
      if (status) status.textContent = '正在解析...';
    }
  }

  resumeUploadForm?.addEventListener('submit', event => {
    if (resumeSubmitInFlight) {
      event.preventDefault();
      return;
    }
    if (fileInput && !fileInput.files.length) return;
    setResumeUploading(true);
  });

  const isPdfFile = file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

  if (fileSelectButton && fileInput) {
    fileSelectButton.addEventListener('click', event => {
      event.preventDefault();
      fileInput.click();
    });
    if (!uploadZone) {
      fileInput.addEventListener('change', () => {
        const file = fileInput.files[0];
        if (!file) return;
        if (!isPdfFile(file)) {
          fileInput.value = '';
          return;
        }
        resumeUploadForm.requestSubmit(primarySubmitButton || undefined);
      });
    }
  }

  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        fileInput.click();
      }
    });
    uploadZone.addEventListener('dragover', event => {
      event.preventDefault();
      uploadZone.classList.add('dragover');
    });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', event => {
      event.preventDefault();
      uploadZone.classList.remove('dragover');
      const file = event.dataTransfer.files[0];
      if (!file) return;
      if (!isPdfFile(file)) {
        showResumeFile(file, false);
        fileInput.value = '';
        return;
      }
      fileInput.files = event.dataTransfer.files;
      showResumeFile(file, true);
      if (resumeUploadForm) resumeUploadForm.requestSubmit(primarySubmitButton || undefined);
    });
    fileInput.addEventListener('change', () => {
      if (!fileInput.files.length) return;
      const file = fileInput.files[0];
      const valid = isPdfFile(file);
      showResumeFile(file, valid);
      if (!valid) {
        fileInput.value = '';
      } else if (resumeUploadForm) {
        resumeUploadForm.requestSubmit(primarySubmitButton || undefined);
      }
    });
  }
  function showResumeFile(file, valid = true) {
    if (!fileList) return;
    const row = document.createElement('div');
    row.className = 'file-row';

    const icon = document.createElement('span');
    icon.className = 'file-icon';
    icon.textContent = 'PDF';

    const name = document.createElement('span');
    name.className = 'file-name';
    name.textContent = file.name;

    const size = document.createElement('span');
    size.className = 'file-size';
    size.textContent = formatSize(file.size);

    const status = document.createElement('span');
    status.className = 'file-status';
    status.textContent = valid ? '已选择' : '仅支持 PDF';

    row.append(icon, name, size, status);
    fileList.replaceChildren(row);
  }

  function formatSize(size) {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }

  const timeFormatters = new Map();

  function timeInZone(zone, now) {
    if (!timeFormatters.has(zone)) {
      timeFormatters.set(zone, new Intl.DateTimeFormat('en-GB', {
        timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      }));
    }
    const parts = Object.fromEntries(
      timeFormatters.get(zone).formatToParts(now)
        .filter(part => part.type !== 'literal')
        .map(part => [part.type, part.value])
    );
    return {
      date: `${parts.year}-${parts.month}-${parts.day}`,
      minutes: Number(parts.hour) * 60 + Number(parts.minute),
      label: `${parts.hour}:${parts.minute}`,
    };
  }

  function updateNowLines() {
    const now = new Date();
    document.querySelectorAll('[data-now-grid]').forEach(grid => {
      const line = grid.querySelector('[data-now-line]');
      if (!line) return;
      const start = Number(grid.dataset.startMinute);
      const end = Number(grid.dataset.endMinute);
      const current = timeInZone(grid.dataset.timeZone, now);
      const visible = current.date === grid.dataset.calendarDate
        && current.minutes >= start && current.minutes <= end;
      line.hidden = !visible;
      if (!visible) return;
      line.style.top = `${(current.minutes - start) / (end - start) * grid.clientHeight}px`;
      line.querySelector('.now-line-label').textContent = `当前时间 ${current.label}`;
    });
  }

  let nowLineTimer;
  function scheduleNowLineUpdate() {
    clearTimeout(nowLineTimer);
    if (document.hidden || !document.querySelector('[data-now-grid]')) return;
    nowLineTimer = setTimeout(() => {
      updateNowLines();
      scheduleNowLineUpdate();
    }, 60000 - Date.now() % 60000 + 25);
  }

  function centerNowLine() {
    const wrap = document.querySelector('.time-grid-wrap');
    const line = document.querySelector('[data-now-line]');
    if (!wrap || !line || line.hidden) return;
    requestAnimationFrame(() => {
      const wrapRect = wrap.getBoundingClientRect();
      const lineRect = line.getBoundingClientRect();
      const lineTop = lineRect.top - wrapRect.top + wrap.scrollTop;
      const targetTop = lineTop + lineRect.height / 2 - wrap.clientHeight / 2;
      wrap.scrollTop = Math.max(0, targetTop);
    });
  }

  updateNowLines();
  centerNowLine();
  scheduleNowLineUpdate();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) updateNowLines();
    scheduleNowLineUpdate();
  });
  document.addEventListener('personal:navigated', () => {
    updateNowLines();
    scheduleNowLineUpdate();
  });

  const dateScope = document.querySelector('[data-date-scope]');
  let dateLoadInFlight = false;

  function softDateLoad(link) {
    if (dateLoadInFlight) return;
    const scope = document.querySelector('[data-date-scope]');
    if (!scope) return;
    dateLoadInFlight = true;
    const cleanHref = link.getAttribute('href');
    const fragHref = cleanHref + (cleanHref.includes('?') ? '&' : '?') + 'fragment=1';
    fetch(fragHref, { headers: { Accept: 'text/html' } })
      .then(response => {
        if (!response.ok) throw new Error('soft date load failed');
        return response.text();
      })
      .then(html => {
        scope.innerHTML = html;
        const params = new URL(cleanHref, window.location.origin).searchParams;
        history.pushState({ date: params.get('date') }, '', cleanHref);
        updateNowLines();
        centerNowLine();
      })
      .catch(() => {
        window.location.href = cleanHref;
      })
      .finally(() => {
        dateLoadInFlight = false;
      });
  }

  if (dateScope) {
    dateScope.addEventListener('click', event => {
      const link = event.target.closest('a.date-nav, a.date-tab');
      if (!link) return;
      event.preventDefault();
      softDateLoad(link);
    });
  }

  const copyButton = document.querySelector('[data-copy]');
  if (copyButton) {
    copyButton.addEventListener('click', async () => {
      const value = copyButton.dataset.copy || '';
      try {
        await navigator.clipboard.writeText(value);
        const original = copyButton.textContent;
        copyButton.textContent = '已复制';
        setTimeout(() => { copyButton.textContent = original; }, 1200);
      } catch {
        copyButton.textContent = '复制失败';
      }
    });
  }

  const deleteButton = document.querySelector('[data-delete]');
  if (deleteButton) {
    deleteButton.addEventListener('click', async event => {
      event.preventDefault();
      if (!confirm('确定要删除这条面试记录吗？')) return;
      const response = await fetch(deleteButton.dataset.delete, { method: 'DELETE' });
      if (response.ok) {
        window.location.href = '/schedule';
      }
    });
  }

  const openResumeButton = document.querySelector('[data-open-resume]');
  const resumeModal = document.querySelector('[data-resume-modal]');
  const closeButton = document.querySelector('[data-close-resume]');
  if (openResumeButton && resumeModal) {
    openResumeButton.addEventListener('click', () => { resumeModal.hidden = false; });
    closeButton?.addEventListener('click', () => { resumeModal.hidden = true; });
    resumeModal.addEventListener('click', event => {
      if (event.target === resumeModal) resumeModal.hidden = true;
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') resumeModal.hidden = true;
    });
  }

  // ---- AI 面试辅助弹窗（按需加载简历上下文并调用后端 API） ----
  const aiModal = document.querySelector('[data-ai-modal]');
  const aiToggle = document.querySelector('[data-toggle-ai-assistant]');
  const aiClose = document.querySelector('[data-close-ai-assistant]');
  const aiStatus = document.querySelector('[data-ai-status]');
  const systemPromptInput = document.querySelector('[data-system-prompt-input]');
  const aiBaseUrlInput = document.querySelector('[data-ai-base-url-input]');
  const aiModelInput = document.querySelector('[data-ai-model-input]');
  const aiApiKeyInput = document.querySelector('[data-ai-api-key-input]');
  const chatForm = document.querySelector('[data-chat-form]');
  const chatInput = document.querySelector('[data-chat-input]');
  const chatMessages = document.querySelector('[data-chat-messages]');
  const suggestionButtons = document.querySelectorAll('[data-suggest]');
  const entryId = aiModal?.dataset.entryId;
  const historyKey = entryId ? `ai-interview-history-${entryId}` : null;

  const aiPanel = aiModal?.querySelector('.ai-panel');
  const aiDragHandle = aiModal?.querySelector('.ai-assistant-header');
  let aiDragState = null;
  let aiContextLoaded = false;
  let aiReady = false;
  let aiRequestInFlight = false;
  let chatHistory = [];

  function readHistory() {
    if (!historyKey) return [];
    try {
      const parsed = JSON.parse(sessionStorage.getItem(historyKey) || '[]');
      return Array.isArray(parsed) ? parsed.filter(item => {
        return item && (item.role === 'user' || item.role === 'assistant') && item.content;
      }) : [];
    } catch {
      return [];
    }
  }

  function saveHistory() {
    if (historyKey) sessionStorage.setItem(historyKey, JSON.stringify(chatHistory.slice(-40)));
  }

  function setAiStatus(text, isError = false) {
    if (!aiStatus) return;
    aiStatus.innerHTML = '<i></i>';
    aiStatus.append(text);
    aiStatus.classList.toggle('error', isError);
  }

  function setComposerEnabled(enabled) {
    aiReady = enabled;
    chatInput?.toggleAttribute('disabled', !enabled);
    suggestionButtons.forEach(button => {
      button.toggleAttribute('disabled', !enabled);
    });
  }

  async function loadAiContext() {
    if (!entryId || aiContextLoaded || aiRequestInFlight) return;
    aiRequestInFlight = true;
    setAiStatus('正在加载简历上下文…');
    try {
      const response = await fetch(`/api/v1/interviews/${encodeURIComponent(entryId)}/ai/context`);
      const body = await response.json();
      if (!response.ok) throw new Error(body?.detail || 'AI 上下文加载失败');
      const context = body.data;
      if (!context.has_resume_context || !context.resume_text_available) {
        throw new Error('简历解析文本不可用，请重新上传简历');
      }
      if (systemPromptInput && !systemPromptInput.value.trim()) {
        systemPromptInput.value = context.default_system_prompt;
      }
      setAiStatus(`已加载：${context.candidate_name}`);
      aiContextLoaded = true;
      setComposerEnabled(true);
      chatHistory = readHistory();
      if (chatHistory.length) {
        chatMessages.replaceChildren();
        chatHistory.forEach(item => addMessage(item.role === 'assistant' ? 'agent' : 'user', item.content));
      }
    } catch (error) {
      setAiStatus(error.message || 'AI 上下文加载失败', true);
      setComposerEnabled(false);
    } finally {
      aiRequestInFlight = false;
    }
  }

  function setAiPanel(open) {
    if (!aiModal) return;
    aiModal.hidden = !open;
    if (open) {
      loadAiContext();
      setTimeout(() => chatInput?.focus({ preventScroll: true }), 60);
    }
  }

  aiToggle?.addEventListener('click', () => {
    setAiPanel(aiModal?.hidden ?? false);
  });
  aiClose?.addEventListener('click', () => setAiPanel(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && aiModal && !aiModal.hidden) setAiPanel(false);
  });

  // 非模态浮窗：按住标题栏拖动，仍可直接操作详情页。
  aiDragHandle?.addEventListener('pointerdown', event => {
    if (!aiPanel || event.target.closest('.ai-close')) return;

    const rect = aiPanel.getBoundingClientRect();
    aiPanel.style.left = `${rect.left}px`;
    aiPanel.style.top = `${rect.top}px`;
    aiPanel.style.transform = 'none';
    aiDragState = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    aiDragHandle.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  aiDragHandle?.addEventListener('pointermove', event => {
    if (!aiDragState || event.pointerId !== aiDragState.pointerId) return;

    const width = aiPanel.offsetWidth;
    const x = Math.min(
      Math.max(event.clientX - aiDragState.offsetX, 80 - width),
      window.innerWidth - 80
    );
    const y = Math.min(
      Math.max(event.clientY - aiDragState.offsetY, 0),
      window.innerHeight - 64
    );
    aiPanel.style.left = `${x}px`;
    aiPanel.style.top = `${y}px`;
  });

  const stopAiDrag = event => {
    if (aiDragState?.pointerId !== event.pointerId) return;
    aiDragState = null;
    aiDragHandle?.releasePointerCapture(event.pointerId);
  };
  aiDragHandle?.addEventListener('pointerup', stopAiDrag);
  aiDragHandle?.addEventListener('pointercancel', stopAiDrag);

  function currentTime() {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  }

  function renderMarkdown(element, content) {
    if (!element) return;

    if (window.marked && window.DOMPurify) {
      element.classList.add('markdown-body');
      element.innerHTML = DOMPurify.sanitize(
        marked.parse(content, { async: false, gfm: true, breaks: true })
      );
      return;
    }

    element.textContent = content;
  }

  function createMarkdownStreamRenderer(element) {
    let content = '';
    let frameId = null;

    const paint = () => {
      frameId = null;
      renderMarkdown(element, content);
    };

    return {
      append(delta) {
        content += delta || '';
        // The thinking bubble is nowrap; remove it before the first markdown paint.
        element?.closest('.ai-msg')?.classList.remove('thinking');
        if (frameId === null) {
          frameId = requestAnimationFrame(paint);
        }
      },
      flush() {
        if (frameId !== null) {
          cancelAnimationFrame(frameId);
          frameId = null;
        }
        renderMarkdown(element, content);
        return content;
      },
    };
  }

  function addMessage(role, content, { markdown = role === 'agent' } = {}) {
    if (!chatMessages) return null;
    const msg = document.createElement('div');
    msg.className = `ai-msg ${role}`;

    const avatar = document.createElement('span');
    avatar.className = 'ai-avatar';
    avatar.textContent = role === 'agent' ? '🤖' : '🧑';

    const body = document.createElement('div');
    body.className = 'ai-body';

    const bubble = document.createElement('div');
    bubble.className = 'ai-bubble';
    if (markdown) {
      renderMarkdown(bubble, content);
    } else {
      bubble.textContent = content;
    }

    const time = document.createElement('span');
    time.className = 'ai-time';
    time.textContent = currentTime();

    body.append(bubble, time);
    msg.append(avatar, body);
    chatMessages.append(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return msg;
  }

  function readAiModelConfig() {
    return {
      base_url: aiBaseUrlInput?.value.trim() || null,
      model: aiModelInput?.value.trim() || null,
      api_key: aiApiKeyInput?.value || null,
    };
  }

  async function streamAiReply(question, bubble) {
    const response = await fetch(
      `/api/v1/interviews/${encodeURIComponent(entryId)}/ai/chat/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          history: chatHistory.slice(-20),
          system_prompt: systemPromptInput?.value.trim() || null,
          ai_model_config: readAiModelConfig(),
        }),
      }
    );

    if (!response.ok) {
      let message = 'AI 回复失败';
      try {
        const body = await response.json();
        message = body?.detail || message;
      } catch {
        // Keep the generic message when the error response is not JSON.
      }
      throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answer = '';
    const markdownRenderer = createMarkdownStreamRenderer(bubble);

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();

      for (const event of events) {
        const dataLine = event
          .split('\n')
          .find(line => line.startsWith('data:'));
        if (!dataLine) continue;

        let payload;
        try {
          payload = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }

        if (payload.type === 'delta') {
          answer += payload.content || '';
          markdownRenderer.append(payload.content || '');
          if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
        } else if (payload.type === 'error') {
          throw new Error(payload.message || 'AI 回复失败');
        } else if (payload.type === 'done') {
          return markdownRenderer.flush();
        }
      }
    }

    if (!answer.trim()) {
      throw new Error('AI 没有返回内容，请稍后重试。');
    }
    return markdownRenderer.flush();
  }

  async function sendChat(text) {
    const value = (text ?? chatInput?.value ?? '').trim();
    if (!value || !aiReady || aiRequestInFlight) return;
    if (!entryId) return;

    addMessage('user', value);
    chatHistory.push({ role: 'user', content: value });
    if (chatInput) chatInput.value = '';

    const thinking = addMessage('agent', '', { markdown: false });
    thinking?.classList.add('thinking');
    const bubble = thinking?.querySelector('.ai-bubble');

    if (bubble) {
      const thinkingText = document.createElement('span');
      thinkingText.className = 'thinking-text';
      thinkingText.textContent = '正在分析';

      const thinkingDots = document.createElement('span');
      thinkingDots.className = 'thinking-dots';
      thinkingDots.innerHTML = '<i></i><i></i><i></i>';

      bubble.append(thinkingText, thinkingDots);
    }
    aiRequestInFlight = true;
    setComposerEnabled(false);

    try {
      const answer = await streamAiReply(value, bubble);
      thinking?.classList.remove('thinking');
      if (bubble) renderMarkdown(bubble, answer);
      chatHistory.push({ role: 'assistant', content: answer });
      saveHistory();
    } catch (error) {
      const partialAnswer = bubble?.textContent === '正在分析' ? '' : bubble?.textContent || '';
      if (thinking && partialAnswer) {
        thinking.classList.remove('thinking');
        const errorLine = document.createElement('span');
        errorLine.className = 'ai-error-note';
        errorLine.textContent = `（流式中断：${error.message || 'AI 回复失败'}）`;
        thinking.querySelector('.ai-body')?.append(errorLine);
      } else {
        thinking?.remove();
        chatHistory.pop();
        addMessage('agent', error.message || 'AI 回复失败，请稍后重试。');
      }
    } finally {
      aiRequestInFlight = false;
      setComposerEnabled(true);
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  chatForm?.addEventListener('submit', event => {
    event.preventDefault();
    sendChat();
  });

  chatInput?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });

  suggestionButtons.forEach(button => {
    button.addEventListener('click', () => sendChat(button.dataset.suggest));
  });
});
