(() => {
  const header = document.querySelector('.personal-app .page-header');
  const button = header?.querySelector('[data-mobile-nav-toggle]');
  if (!header || !button) return;

  // Collapsing the menu changes page height and can move scrollY back across
  // the threshold. Arm each expansion once instead of reopening on scroll.
  let collapseAt = window.scrollY < 96 ? 96 : null;
  const setOpen = (open) => {
    header.dataset.mobileNavOpen = String(open);
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? '收起导航' : '展开导航');
  };
  setOpen(window.scrollY < 96);
  button.addEventListener('click', () => {
    const open = header.dataset.mobileNavOpen !== 'true';
    collapseAt = open ? window.scrollY + 96 : null;
    setOpen(open);
  });
  window.addEventListener('scroll', () => {
    if (window.matchMedia('(max-width: 1000px)').matches &&
        collapseAt !== null && window.scrollY >= collapseAt) {
      collapseAt = null;
      setOpen(false);
    }
  }, { passive: true });
  header.querySelectorAll('.page-nav a').forEach((link) => {
    link.addEventListener('click', () => { collapseAt = null; setOpen(false); });
  });
  document.addEventListener('personal:navigated', () => {
    collapseAt = 96;
    setOpen(true);
  });
})();
