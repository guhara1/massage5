#!/usr/bin/env python3
"""
Patch the ~140 city/province-index region pages that the first two
enhancement scripts missed due to wording variations:

  - Their price-intro paragraph says "권역에서" instead of "권역 안에서".
  - Their FAQ heading is "처음 이용하는 분들이 자주 묻는 질문" instead of
    a leaf-style "{name} 자주 묻는 질문".

Applies the same two transformations from the first pass (price
attribution + rotated FAQ) using broader regex patterns. Idempotent.
"""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION_DIR = ROOT / 'region'

# Reuse exact assets from the prior scripts so behavior matches.
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from differentiate_region_pages import (  # noqa: E402
    FAQ_POOL,
    build_name_index,
    normalize_display_name,
    select_faqs,
    faq_html,
)
from enhance_region_pages import PRICE_INTRO_NEW  # noqa: E402


# Broader price-intro pattern that catches both wording variants.
PRICE_INTRO_OLD_BROAD = re.compile(
    r'<p>[^<]*권역\s*안?에서[^<]*일반적으로\s*운영되는\s*코스의\s*가격대\s*'
    r'가이드입니다[^<]*</p>',
    re.S,
)


def process(path: Path, name_by_path: dict) -> dict:
    html = path.read_text(encoding='utf-8')
    original = html
    actions = []
    rel = path.relative_to(REGION_DIR)
    rel_str = str(rel)

    m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', html)
    if not m:
        return {'path': rel_str, 'actions': []}
    page_name = normalize_display_name(m.group(1))

    # Determine parent name
    parent_index = path.parent / 'index.html'
    if path.name == 'index.html':
        # this IS the index → look one level up
        parent_index = path.parent.parent / 'index.html'
    parent_name = name_by_path.get(parent_index, '')

    # --- Price attribution -------------------------------------------
    if '권역 평균 참고가' not in html:
        new_html, n = PRICE_INTRO_OLD_BROAD.subn(
            PRICE_INTRO_NEW, html, count=1
        )
        if n:
            html = new_html
            actions.append('price-attribution')

    # --- Rotated FAQ on "처음 이용하는 분들이 자주 묻는 질문" sections --
    if 'class="faq-v2"' not in html and '자주 묻는 질문</h2>' in html:
        faqs = select_faqs(rel_str, page_name, parent_name or page_name)
        new_faq_html = '<div class="faq-v2">\n' + faq_html(faqs) + '\n  </div>'
        pattern = re.compile(
            r'(<section class="[^"]*subsection[^"]*">\s*<h2>[^<]*자주\s*묻는\s*질문</h2>\s*)'
            r'(?:<details[\s\S]*?</details>\s*)+'
            r'(\s*</section>)',
            re.S,
        )
        new_html, n = pattern.subn(
            lambda m: m.group(1) + new_faq_html + m.group(2), html, count=1
        )
        if n:
            html = new_html
            actions.append('faq-rotate')
        else:
            # Try a more general selector (any block containing the heading
            # followed by <details> children).
            pattern2 = re.compile(
                r'(<h2>[^<]*자주\s*묻는\s*질문</h2>\s*)'
                r'(?:<details[\s\S]*?</details>\s*)+',
                re.S,
            )
            new_html, n = pattern2.subn(
                lambda m: m.group(1) + new_faq_html + '\n  ',
                html,
                count=1,
            )
            if n:
                html = new_html
                actions.append('faq-rotate-fallback')

    if html != original:
        path.write_text(html, encoding='utf-8')
    return {'path': rel_str, 'actions': actions}


def main():
    name_by_path = build_name_index()
    pages = sorted(
        p for p in REGION_DIR.rglob('*.html') if '.git' not in p.parts
    )
    summary = {}
    no_change = 0
    for p in pages:
        r = process(p, name_by_path)
        if not r['actions']:
            no_change += 1
        for a in r['actions']:
            summary[a] = summary.get(a, 0) + 1
    summary['no-change'] = no_change
    print(f'Processed {len(pages)} pages')
    for k, v in sorted(summary.items()):
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
