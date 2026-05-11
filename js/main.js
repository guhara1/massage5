(function () {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      nav.classList.toggle('open');
      document.body.style.overflow = nav.classList.contains('open') ? 'hidden' : '';
    });
    nav.querySelectorAll('a').forEach((a) => {
      a.addEventListener('click', () => {
        if (nav.classList.contains('open')) {
          nav.classList.remove('open');
          document.body.style.overflow = '';
        }
      });
    });
  }

  // Mark current page active in nav
  const path = location.pathname.replace(/\/+$/, '') || '/';
  document.querySelectorAll('.nav-item').forEach((item) => {
    const match = item.getAttribute('data-section');
    if (!match) return;
    if (path === '/' && match === 'home') item.classList.add('active');
    else if (path.indexOf('/' + match) !== -1) item.classList.add('active');
  });
})();
