#!/usr/bin/env python3
"""
Replace og:image references pointing at favicon.svg (or any non-default
asset) with the new branded og-default.svg.

Also updates Article/WebPage schema's `image` and `primaryImageOfPage.url`
when they pointed to favicon.svg.

Idempotent.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = 'https://gandago.me/favicon.svg'
NEW = 'https://gandago.me/assets/og-default.svg'


def process(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    # Only touch og:image and JSON-LD image fields, NOT favicon link tags.
    changed = False

    new_text = re.sub(
        r'(<meta\s+property="og:image"\s+content=")' + re.escape(OLD) + r'(")',
        r'\1' + NEW + r'\2',
        text,
    )
    if new_text != text:
        changed = True
        text = new_text

    # JSON-LD: "image": "https://gandago.me/favicon.svg"
    new_text = re.sub(
        r'("image"\s*:\s*")' + re.escape(OLD) + r'(")',
        r'\1' + NEW + r'\2',
        text,
    )
    if new_text != text:
        changed = True
        text = new_text

    # JSON-LD primaryImageOfPage.url
    new_text = re.sub(
        r'("url"\s*:\s*")' + re.escape(OLD) + r'("[^}]*"@type"\s*:\s*"ImageObject")',
        r'\1' + NEW + r'\2',
        text,
    )
    if new_text != text:
        changed = True
        text = new_text

    if changed:
        path.write_text(text, encoding='utf-8')
    return changed


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
