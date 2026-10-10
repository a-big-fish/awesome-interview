document.addEventListener('DOMContentLoaded', () => {
  const eventType = document.querySelector('[data-event-type]');
  const positionField = document.querySelector('[data-position-field]');
  if (eventType && positionField) {
    const updatePositionField = () => {
      const isInterview = eventType.value === 'interview';
      positionField.hidden = !isInterview;
      positionField.querySelector('input').disabled = !isInterview;
    };
    eventType.addEventListener('change', updatePositionField);
    updatePositionField();
  }

  const dialog = document.querySelector('[data-time-dialog]');
  const fields = [...document.querySelectorAll('.personal-time-field')];
  if (!dialog || !fields.length) return;

  const heading = dialog.querySelector('[data-time-heading]');
  const progress = dialog.querySelector('[data-time-progress]');
  const options = dialog.querySelector('[data-time-options]');
  const back = dialog.querySelector('[data-time-back]');
  let activeField = null;
  let step = 0;
  let selectedDate = '';
  let selectedHour = '';
  let viewYear = 0;
  let viewMonth = 0;
  let calendarMode = 'days';
  let yearPageStart = 0;

  const pad = number => String(number).padStart(2, '0');
  const validValue = value => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value);
  const formatValue = value => validValue(value)
    ? `${value.slice(0, 4)}/${value.slice(5, 7)}/${value.slice(8, 10)} ${value.slice(11)}`
    : value || '请选择日期和时间';

  fields.forEach(field => {
    const value = field.querySelector('[data-time-value]');
    const trigger = field.querySelector('[data-time-trigger]');
    trigger.textContent = formatValue(value.value);
    trigger.addEventListener('click', () => {
      activeField = field;
      step = 0;
      selectedDate = validValue(value.value) ? value.value.slice(0, 10) : '';
      selectedHour = validValue(value.value) ? value.value.slice(11, 13) : '';
      const today = new Date();
      const shownDate = selectedDate || `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
      viewYear = Number(shownDate.slice(0, 4));
      viewMonth = Number(shownDate.slice(5, 7));
      calendarMode = 'days';
      render();
      dialog.showModal();
    });
  });

  function calendarButton(label, className, onClick, ariaLabel = label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.setAttribute('aria-label', ariaLabel);
    button.addEventListener('click', onClick);
    return button;
  }

  function renderCalendar() {
    options.replaceChildren();
    const calendar = document.createElement('div');
    calendar.className = 'personal-calendar-picker';
    const header = document.createElement('div');
    header.className = 'personal-calendar-header';

    if (calendarMode === 'years') {
      header.append(
        calendarButton('‹', 'personal-calendar-nav', () => { yearPageStart -= 12; renderCalendar(); }, '前 12 年'),
        Object.assign(document.createElement('strong'), { textContent: `${yearPageStart}—${yearPageStart + 11} 年` }),
        calendarButton('›', 'personal-calendar-nav', () => { yearPageStart += 12; renderCalendar(); }, '后 12 年')
      );
      const grid = document.createElement('div');
      grid.className = 'personal-calendar-pick-grid';
      for (let year = yearPageStart; year < yearPageStart + 12; year += 1) {
        const choice = calendarButton(String(year), 'personal-calendar-pick', () => {
          viewYear = year;
          calendarMode = 'months';
          renderCalendar();
        });
        if (year === viewYear) choice.classList.add('selected');
        grid.append(choice);
      }
      calendar.append(header, grid, calendarButton('返回日历', 'personal-calendar-return', () => {
        calendarMode = 'days';
        renderCalendar();
      }));
      options.append(calendar);
      return;
    }

    if (calendarMode === 'months') {
      header.append(
        calendarButton('‹', 'personal-calendar-nav', () => { viewYear -= 1; renderCalendar(); }, '上一年'),
        Object.assign(document.createElement('strong'), { textContent: `${viewYear} 年` }),
        calendarButton('›', 'personal-calendar-nav', () => { viewYear += 1; renderCalendar(); }, '下一年')
      );
      const grid = document.createElement('div');
      grid.className = 'personal-calendar-pick-grid';
      for (let month = 1; month <= 12; month += 1) {
        const choice = calendarButton(`${month} 月`, 'personal-calendar-pick', () => {
          viewMonth = month;
          calendarMode = 'days';
          renderCalendar();
        });
        if (month === viewMonth) choice.classList.add('selected');
        grid.append(choice);
      }
      calendar.append(header, grid, calendarButton('返回日历', 'personal-calendar-return', () => {
        calendarMode = 'days';
        renderCalendar();
      }));
      options.append(calendar);
      return;
    }

    const moveMonth = delta => {
      const target = new Date(viewYear, viewMonth - 1 + delta, 1);
      viewYear = target.getFullYear();
      viewMonth = target.getMonth() + 1;
      renderCalendar();
    };
    header.append(
      calendarButton('‹', 'personal-calendar-nav', () => moveMonth(-1), '上个月'),
      calendarButton(`${viewYear} 年`, 'personal-calendar-title', () => {
        yearPageStart = Math.floor(viewYear / 12) * 12;
        calendarMode = 'years';
        renderCalendar();
      }, '选择年份'),
      calendarButton(`${viewMonth} 月`, 'personal-calendar-title', () => {
        calendarMode = 'months';
        renderCalendar();
      }, '选择月份'),
      calendarButton('›', 'personal-calendar-nav', () => moveMonth(1), '下个月')
    );
    const grid = document.createElement('div');
    grid.className = 'personal-calendar-day-grid';
    for (const weekday of ['一', '二', '三', '四', '五', '六', '日']) {
      const label = document.createElement('span');
      label.className = 'personal-calendar-weekday';
      label.textContent = weekday;
      grid.append(label);
    }
    const firstWeekday = (new Date(viewYear, viewMonth - 1, 1).getDay() + 6) % 7;
    for (let index = 0; index < firstWeekday; index += 1) {
      const blank = document.createElement('span');
      blank.className = 'personal-calendar-blank';
      grid.append(blank);
    }
    const days = new Date(viewYear, viewMonth, 0).getDate();
    for (let day = 1; day <= days; day += 1) {
      const date = `${viewYear}-${pad(viewMonth)}-${pad(day)}`;
      const choice = calendarButton(String(day), 'personal-calendar-day', () => {
        selectedDate = date;
        step = 1;
        render();
      }, `${viewYear}年${viewMonth}月${day}日`);
      if (date === selectedDate) choice.classList.add('selected');
      grid.append(choice);
    }
    calendar.append(header, grid);
    options.append(calendar);

    if (selectedDate.startsWith(`${viewYear}-${pad(viewMonth)}-`)) {
      const next = calendarButton('下一步：选择小时', 'btn secondary personal-time-next', () => {
        step = 1;
        render();
      });
      options.append(next);
    }
  }

  function render() {
    const labels = ['选择年月日', '选择小时', '选择分钟'];
    heading.textContent = `${activeField.querySelector('span').textContent} · ${labels[step]}`;
    progress.textContent = labels.map((label, index) => index === step ? `● ${label}` : label).join('  →  ');
    back.hidden = step === 0;
    dialog.classList.toggle('is-calendar', step === 0);
    options.replaceChildren();

    if (step === 0) {
      renderCalendar();
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'personal-time-grid';
    const count = step === 1 ? 24 : 60;
    for (let index = 0; index < count; index += 1) {
      const number = pad(index);
      const choice = document.createElement('button');
      choice.type = 'button';
      choice.className = 'personal-time-choice';
      choice.textContent = step === 1 ? `${number} 时` : `${number} 分`;
      if (step === 1 && number === selectedHour) choice.classList.add('selected');
      if (step === 2 && validValue(activeField.querySelector('[data-time-value]').value)
          && number === activeField.querySelector('[data-time-value]').value.slice(14, 16)) {
        choice.classList.add('selected');
      }
      choice.addEventListener('click', () => {
        if (step === 1) {
          selectedHour = number;
          step = 2;
          render();
          return;
        }
        const value = activeField.querySelector('[data-time-value]');
        value.value = `${selectedDate}T${selectedHour}:${number}`;
        activeField.querySelector('[data-time-trigger]').textContent = formatValue(value.value);
        dialog.close();
        activeField.querySelector('[data-time-trigger]').focus();
      });
      grid.append(choice);
    }
    options.append(grid);
    grid.querySelector('.selected')?.scrollIntoView({ block: 'nearest' });
  }

  back.addEventListener('click', () => {
    if (step > 0) {
      step -= 1;
      render();
    }
  });
  dialog.querySelector('[data-time-close]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-time-cancel]').addEventListener('click', () => dialog.close());
});
