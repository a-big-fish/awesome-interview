(() => {
  const form = document.querySelector('[data-export-settings]');
  if (!form) return;
  form.querySelectorAll('input[name="style"]').forEach((input) => {
    input.addEventListener('change', () => form.requestSubmit(form.querySelector('[data-export-preview]')));
  });
  form.querySelector('[data-export-hide-answers-time]')?.addEventListener('click', () => {
    const fields = ['hide_on_site_answer', 'hide_review_answer', 'hide_interviewer_answer', 'hide_interviewed_at']
      .map((name) => form.elements.namedItem(name));
    const hide = !fields.every((field) => field.checked);
    fields.forEach((field) => { field.checked = hide; });
    form.requestSubmit(form.querySelector('[data-export-preview]'));
  });
})();
