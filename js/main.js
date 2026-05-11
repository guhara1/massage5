(function () {
  // ===== Mobile menu toggle =====
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

  // ===== Mark current page active in nav =====
  const path = location.pathname.replace(/\/+$/, '') || '/';
  document.querySelectorAll('.nav-item').forEach((item) => {
    const match = item.getAttribute('data-section');
    if (!match) return;
    if (path === '/' && match === 'home') item.classList.add('active');
    else if (path.indexOf('/' + match) !== -1) item.classList.add('active');
  });

  // ===== Region/district/dong alphabetical sort (ㄱㄴㄷ) =====
  function sortChildren(container, keyFn) {
    if (!container) return;
    const items = Array.from(container.children).filter(el => el.tagName);
    if (items.length < 2) return;
    items.sort((a, b) => keyFn(a).localeCompare(keyFn(b), 'ko-KR'));
    items.forEach(item => container.appendChild(item));
  }
  const plainText = el => (el.textContent || '').trim();
  const headingText = el => {
    const h = el.querySelector('h3, h2');
    return ((h ? h.textContent : el.textContent) || '').trim();
  };

  // 3차·4차: district directory buttons (시·군·구 + 행정동)
  document.querySelectorAll('.district-row').forEach(c => sortChildren(c, plainText));

  // 2차: region/index.html curated mega/grid sections
  document.querySelectorAll('.region-mega-grid, .region-grid-6, .region-grid-8').forEach(c => sortChildren(c, headingText));

  // Card grids inside province/district index sections (전체 시·군·구 / 전체 행정동)
  document.querySelectorAll('section.section').forEach(sec => {
    const head = sec.querySelector('.section-head');
    if (!head) return;
    const headText = (head.textContent || '').trim();
    // Only sort region/admin lists, NOT service grids
    if (/전체\s*시·?군·?구|전체\s*행정동|광역시·?도|광역시|도\s*\(/.test(headText)) {
      const grid = sec.querySelector('.grid');
      if (grid) sortChildren(grid, headingText);
    }
  });
})();
