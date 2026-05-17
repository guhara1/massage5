#!/usr/bin/env python3
"""
Inject a footer-legal nav row right before the existing footer-bottom div
in every HTML page. Idempotent: skips files that already contain
class="footer-legal".

The links use root-relative paths so they work at any directory depth.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEGAL_BLOCK = '''  <div class="footer-legal">
    <div class="container">
      <a href="/about/index.html">간다GO 소개</a>
      <span class="sep">·</span>
      <a href="/about/authors/index.html">편집팀</a>
      <span class="sep">·</span>
      <a href="/legal/privacy.html">개인정보처리방침</a>
      <span class="sep">·</span>
      <a href="/legal/terms.html">이용약관</a>
      <span class="sep">·</span>
      <span>통신판매업: 등록 진행 중</span>
    </div>
  </div>

'''

FOOTER_BOTTOM_PATTERN = re.compile(
    r'([ \t]*)<div class="footer-bottom">',
    re.MULTILINE,
)


def process(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    if 'class="footer-legal"' in text:
        return False
    m = FOOTER_BOTTOM_PATTERN.search(text)
    if not m:
        return False
    insertion_point = m.start()
    new_text = text[:insertion_point] + LEGAL_BLOCK + text[insertion_point:]
    path.write_text(new_text, encoding='utf-8')
    return True


def main():
    changed = 0
    skipped = 0
    for html in ROOT.rglob('*.html'):
        if '.git' in html.parts:
            continue
        if process(html):
            changed += 1
        else:
            skipped += 1
    print(f'changed={changed}  skipped={skipped}')


if __name__ == '__main__':
    main()
