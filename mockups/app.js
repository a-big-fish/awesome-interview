document.addEventListener('DOMContentLoaded', () => {
  // Date tab filtering for schedule mockup
  const dateTabs = Array.from(document.querySelectorAll('.date-tab'));
  const groups = Array.from(document.querySelectorAll('.schedule-group'));

  function showDate(targetId) {
    groups.forEach(group => {
      group.hidden = group.id !== targetId;
    });
    dateTabs.forEach(tab => {
      tab.classList.toggle('active', tab.getAttribute('href') === `#${targetId}`);
    });
  }

  if (dateTabs.length && groups.length) {
    dateTabs.forEach(tab => {
      tab.addEventListener('click', event => {
        event.preventDefault();
        const targetId = tab.getAttribute('href').slice(1);
        showDate(targetId);
        history.replaceState(null, '', `#${targetId}`);
      });
    });

    const initialId = location.hash.slice(1);
    showDate(groups.some(group => group.id === initialId) ? initialId : groups[0].id);
  }

  // Resume upload drag & drop mockup
  const uploadZone = document.querySelector('[data-upload-zone]');
  const fileInput = document.querySelector('[data-file-input]');
  const fileList = document.querySelector('[data-file-list]');
  const parseResult = document.querySelector('[data-parse-result]');

  function formatSize(size) {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }

  function addFiles(files) {
    if (!fileList) return;
    fileList.innerHTML = '';
    Array.from(files).forEach(file => {
      const row = document.createElement('div');
      row.className = 'file-row';
      row.innerHTML = `
        <span class="file-icon">PDF</span>
        <span class="file-name">${file.name}</span>
        <span class="file-size">${formatSize(file.size)}</span>
        <span class="file-status">已选择</span>
      `;
      fileList.appendChild(row);
    });
    if (parseResult) parseResult.hidden = false;
  }

  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('dragover', event => {
      event.preventDefault();
      uploadZone.classList.add('dragover');
    });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', event => {
      event.preventDefault();
      uploadZone.classList.remove('dragover');
      addFiles(event.dataTransfer.files);
    });
    fileInput.addEventListener('change', () => addFiles(fileInput.files));
  }

  // Resume modal
  const modal = document.querySelector('[data-resume-modal]');
  const openButtons = Array.from(document.querySelectorAll('[data-open-resume]'));
  const closeButton = document.querySelector('[data-close-resume]');

  openButtons.forEach(button => {
    button.addEventListener('click', () => {
      if (modal) modal.hidden = false;
    });
  });

  if (closeButton && modal) {
    closeButton.addEventListener('click', () => {
      modal.hidden = true;
    });
    modal.addEventListener('click', event => {
      if (event.target === modal) modal.hidden = true;
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') modal.hidden = true;
    });
  }
});

// Current time indicator on schedule grid
function updateNowLine() {
  const grids = Array.from(document.querySelectorAll('.time-grid'));
  if (!grids.length) return;

  const params = new URLSearchParams(window.location.search);
  const nowParam = params.get('now');
  let now = new Date();

  if (nowParam) {
    const [hours, minutes] = nowParam.split(':').map(Number);
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      now = new Date(2026, 8, 6, hours, minutes, 0, 0);
    }
  }

  const minutes = now.getHours() * 60 + now.getMinutes();

  grids.forEach(grid => {
    const wrapper = grid.closest(".time-grid-wrap");
    const startHour = Number(wrapper?.style.getPropertyValue("--start-hour")) || 9;
    const endHour = Number(wrapper?.style.getPropertyValue("--end-hour")) || 19;
    const isWithinRange = minutes >= startHour * 60 && minutes <= endHour * 60;
    let line = grid.querySelector('.now-line');

    if (!isWithinRange) {
      if (line) line.remove();
      return;
    }

    if (!line) {
      line = document.createElement('div');
      line.className = 'now-line';
      line.innerHTML = '<span class="now-line-label"></span>';
      grid.appendChild(line);
    }

    const hourHeight = Number(grid.style.getPropertyValue('--hour-height')) || 96;
    const top = ((minutes - startHour * 60) / 60) * hourHeight;
    line.style.top = `${top}px`;
    const label = line.querySelector('.now-line-label');
    if (label) {
      label.textContent = `当前时间 ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    }
  });
}

// Dynamic schedule range controls
function parseTimeValue(value, fallback) {
  const [hours, minutes] = (value || "").split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return fallback;
  return hours + minutes / 60;
}

function formatHour(value) {
  const hours = Math.floor(value);
  const minutes = Math.round((value - hours) * 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function getTimeRange() {
  const activeGroup = document.querySelector(".schedule-group:not([hidden])");
  const start = parseTimeValue(activeGroup?.querySelector("[data-range-start]")?.value || document.querySelector("[data-range-start]")?.value, 9);
  const end = parseTimeValue(activeGroup?.querySelector("[data-range-end]")?.value || document.querySelector("[data-range-end]")?.value, 19);
  return end > start ? { start, end } : { start, end: start + 0.5 };
}

function renderTimeGrids() {
  const { start, end } = getTimeRange();
  const hourHeight = 96;

  document.querySelectorAll(".time-grid-wrap").forEach(wrap => {
    const labels = wrap.querySelector(".time-labels");
    const grid = wrap.querySelector(".time-grid");
    if (!labels || !grid) return;

    wrap.style.setProperty("--start-hour", start);
    wrap.style.setProperty("--end-hour", end);
    grid.style.height = `${(end - start) * hourHeight}px`;

    labels.innerHTML = "";
    for (let minutes = start * 60; minutes <= end * 60; minutes += 30) {
      const label = document.createElement("span");
      label.className = "time-label";
      label.style.top = `${(minutes - start * 60) / 60 * hourHeight}px`;
      label.textContent = formatHour(minutes / 60);
      labels.appendChild(label);
    }

    Array.from(grid.children).forEach(child => {
      if (child.matches(".lunch-block, .tea-break-block, .now-line")) {
        child.remove();
      }
    });

    const addBlock = (className, text, blockStart, blockEnd) => {
      if (blockEnd <= start || blockStart >= end) return;
      const block = document.createElement("div");
      block.className = className;
      block.setAttribute("aria-label", text);
      block.style.setProperty("--lunch-start-hour", blockStart);
      block.style.setProperty("--lunch-end-hour", blockEnd);
      block.style.setProperty("--tea-start-hour", blockStart);
      block.style.setProperty("--tea-end-hour", blockEnd);
      block.innerHTML = `<span>${text} ${formatHour(blockStart)} - ${formatHour(blockEnd)}</span>`;
      grid.appendChild(block);
    };

    addBlock("lunch-block", "\u5348\u4f11", 12, 13);
    addBlock("tea-break-block", "\u8336\u6b47", 16, 16.5);

    grid.querySelectorAll(".event-card").forEach(card => {
      const cardStart = Number(card.style.getPropertyValue("--start-min"));
      const duration = Number(card.style.getPropertyValue("--duration"));
      const cardEnd = cardStart + duration;
      card.hidden = cardEnd <= start * 60 || cardStart >= end * 60;
    });
  });
}

const TIME_OPTIONS = [];
for (let minutes = 6 * 60; minutes <= 22 * 60; minutes += 30) {
  TIME_OPTIONS.push(minutes);
}

function parseTimeInput(value) {
  const normalized = value.trim().replace(/\uFF1A/g, ":");
  const match = normalized.match(/^(\d{1,2})(?::(\d{1,2}))?$/);
  if (!match) return null;

  const hours = Number(match[1]);
  const minutes = match[2] === undefined ? 0 : Number(match[2]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || hours > 23 || minutes > 59) {
    return null;
  }
  return hours * 60 + minutes;
}

function snapToTimeOption(minutes) {
  return TIME_OPTIONS.reduce((nearest, option) => {
    return Math.abs(option - minutes) < Math.abs(nearest - minutes) ? option : nearest;
  });
}

function fuzzyTimeOptions(query) {
  const normalized = query.trim().replace(/[:\uFF1A\s]/g, "");
  if (!normalized) return TIME_OPTIONS;

  return TIME_OPTIONS
    .map(minutes => {
      const time = formatHour(minutes / 60);
      const digits = time.replace(":", "");
      let score = Number.POSITIVE_INFINITY;

      if (time === query.trim().replace(/\uFF1A/g, ":")) score = 0;
      else if (digits.startsWith(normalized)) score = 1;
      else if (digits.endsWith(normalized)) score = 2;
      else if (digits.includes(normalized)) score = 3;
      else {
        let cursor = -1;
        const matched = Array.from(normalized).every(char => {
          cursor = digits.indexOf(char, cursor + 1);
          return cursor !== -1;
        });
        if (matched) score = 4;
      }

      return score === Number.POSITIVE_INFINITY ? null : { minutes, score };
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score || a.minutes - b.minutes)
    .map(item => item.minutes);
}

function closeCombo(combo) {
  const input = combo.querySelector("input");
  const menu = combo.querySelector(".combo-menu");
  menu.hidden = true;
  input.setAttribute("aria-expanded", "false");
  menu.querySelectorAll(".active").forEach(item => item.classList.remove("active"));
}

function renderComboMenu(combo, showAll = false) {
  const input = combo.querySelector("input");
  const menu = combo.querySelector(".combo-menu");
  const minutesList = showAll ? TIME_OPTIONS : fuzzyTimeOptions(input.value);
  const currentValue = input.dataset.lastValidValue || input.value;

  menu.innerHTML = minutesList.map(minutes => {
    const time = formatHour(minutes / 60);
    const active = time === currentValue ? ' class="combo-option active"' : ' class="combo-option"';
    return `<button type="button" role="option" aria-selected="${time === currentValue}"${active} data-value="${time}">${time}</button>`;
  }).join("");

  menu.hidden = false;
  input.setAttribute("aria-expanded", "true");
}

function selectRangeValue(input, value) {
  input.value = value;
  input.dataset.lastValidValue = value;
  closeCombo(input.closest(".time-combo"));
  syncRangeInputs(input, value);
  renderTimeGrids();
  updateNowLine();
}

function setupTimeCombos() {
  const combos = Array.from(document.querySelectorAll(".time-combo"));

  combos.forEach(combo => {
    const input = combo.querySelector("input");
    const toggle = combo.querySelector(".combo-toggle");
    const menu = combo.querySelector(".combo-menu");
    if (!input || !toggle || !menu) return;
    input.dataset.lastValidValue = input.value;

    input.addEventListener("focus", () => renderComboMenu(combo));
    input.addEventListener("input", () => renderComboMenu(combo));
    input.addEventListener("click", () => renderComboMenu(combo));

    toggle.addEventListener("pointerdown", event => event.preventDefault());
    toggle.addEventListener("click", () => {
      if (menu.hidden) {
        renderComboMenu(combo, true);
        menu.scrollTop = 0;
      } else {
        closeCombo(combo);
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(() => closeCombo(combo), 120);
      normalizeRangeInput(input);
      syncRangeInputs(input, input.value);
      renderTimeGrids();
      updateNowLine();
    });

    input.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        closeCombo(combo);
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        const active = menu.querySelector(".combo-option.active");
        if (active && !menu.hidden) {
          selectRangeValue(input, active.dataset.value);
        } else {
          normalizeRangeInput(input);
          syncRangeInputs(input, input.value);
          renderTimeGrids();
          updateNowLine();
          closeCombo(combo);
        }
        return;
      }

      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      if (menu.hidden) renderComboMenu(combo);

      const options = Array.from(menu.querySelectorAll("button"));
      if (!options.length) return;
      let index = options.findIndex(option => option.classList.contains("active"));
      index = event.key === "ArrowDown"
        ? (index + 1) % options.length
        : (index <= 0 ? options.length - 1 : index - 1);
      options.forEach(option => option.classList.remove("active"));
      options[index].classList.add("active");
      options[index].scrollIntoView({ block: "nearest" });
    });

    menu.addEventListener("mousedown", event => event.preventDefault());
    menu.addEventListener("click", event => {
      const option = event.target.closest("button");
      if (!option) return;
      selectRangeValue(input, option.dataset.value);
    });
  });

  document.addEventListener("click", event => {
    if (!event.target.closest(".time-combo")) {
      combos.forEach(closeCombo);
    }
  });
}

const rangeStarts = Array.from(document.querySelectorAll("[data-range-start]"));
const rangeEnds = Array.from(document.querySelectorAll("[data-range-end]"));

function syncRangeInputs(source, value) {
  const isStart = source.matches("[data-range-start]");
  const targets = isStart ? rangeStarts : rangeEnds;
  targets.forEach(input => {
    input.value = value;
    input.dataset.lastValidValue = value;
  });
}

function normalizeRangeInput(input) {
  const minutes = parseTimeInput(input.value);
  if (minutes === null) {
    input.value = input.dataset.lastValidValue || (input.matches("[data-range-start]") ? "09:00" : "19:00");
  } else {
    input.value = formatHour(snapToTimeOption(minutes) / 60);
  }
  input.dataset.lastValidValue = input.value;
  return input.value;
}

[...rangeStarts, ...rangeEnds].forEach(input => {
  input.dataset.lastValidValue = input.value;
  input?.addEventListener("change", () => {
    normalizeRangeInput(input);
    syncRangeInputs(input, input.value);
    renderTimeGrids();
    updateNowLine();
  });
});

setupTimeCombos();
renderTimeGrids();
updateNowLine();
setInterval(updateNowLine, 30000);
