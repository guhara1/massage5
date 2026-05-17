#!/usr/bin/env python3
"""
Comprehensive verification pass over every region/ page.

For each page check that:
  - JSON-LD parses as valid JSON
  - @graph contains Article + WebPage + BreadcrumbList + Organization
  - @graph does NOT contain FAQPage (region pages were cleaned)
  - Person author exists in Article
  - Byline link to /about/authors/han-jiwoo.html present
  - Either region-context OR region-overview paragraph present (hierarchy)
  - Price attribution sentence present (where the page has a price table)
  - Sibling navigation present (where the page has siblings)
  - Rotated FAQ block present (where the page has any FAQ)
  - Canonical URL uses https://gandago.me/
  - og:image points at og-default.svg, not favicon.svg
  - <h1> exists and is non-empty
  - No leftover Korean particle bugs (e.g. "동은 " written as "동는 " or vice versa)

Reports counts + a sample of any failing files.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION_DIR = ROOT / 'region'

JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">\s*(\{[\s\S]*?\})\s*</script>'
)


def has_siblings(path: Path) -> bool:
    parent = path.parent
    others = [
        f for f in parent.iterdir()
        if f.is_file() and f.suffix == '.html'
        and f.name != 'index.html' and f != path
    ]
    return len(others) > 0


CHECKS = [
    'jsonld_valid',
    'has_article',
    'has_webpage',
    'has_breadcrumb',
    'has_organization',
    'no_faqpage',
    'person_author',
    'byline_link',
    'hierarchy_context',
    'price_attribution',
    'sibling_block',
    'rotated_faq',
    'canonical_https',
    'og_default',
    'h1_present',
    'particle_ok',
]


def verify(path: Path) -> dict:
    rel = str(path.relative_to(ROOT))
    html = path.read_text(encoding='utf-8')
    r = {c: False for c in CHECKS}
    issues = []

    # JSON-LD
    m = JSONLD_RE.search(html)
    if m:
        try:
            data = json.loads(m.group(1))
            r['jsonld_valid'] = True
            types = [obj.get('@type') for obj in data.get('@graph', [])]
            r['has_article'] = 'Article' in types
            r['has_webpage'] = 'WebPage' in types
            r['has_breadcrumb'] = 'BreadcrumbList' in types
            r['has_organization'] = 'Organization' in types
            r['no_faqpage'] = 'FAQPage' not in types
            for obj in data.get('@graph', []):
                if obj.get('@type') == 'Article':
                    author = obj.get('author', {})
                    if (
                        isinstance(author, dict)
                        and author.get('@type') == 'Person'
                        and author.get('name')
                    ):
                        r['person_author'] = True
        except json.JSONDecodeError as e:
            issues.append(f'jsonld_error:{e.msg[:40]}')

    # HTML markers
    r['byline_link'] = (
        'about/authors/han-jiwoo.html" rel="author"' in html
    )
    r['hierarchy_context'] = (
        'class="region-context"' in html
        or 'class="region-overview"' in html
    )
    # Price attribution only required if the page actually has a price table
    has_price_table = 'course-grid' in html or 'course-prices' in html
    if has_price_table:
        r['price_attribution'] = '권역 평균 참고가' in html
    else:
        r['price_attribution'] = True  # N/A → pass
    r['sibling_block'] = 'class="region-siblings-grid"' in html
    # Differentiated FAQ accepts either marker:
    #   - class="faq-v2" (leaf-page rotated FAQ pool, ours)
    #   - class="faq-list" (city-index pages, already differentiated with
    #     city-specific question sets — left intact)
    has_faq_section = '자주 묻는 질문</h2>' in html
    if has_faq_section:
        r['rotated_faq'] = (
            'class="faq-v2"' in html or 'class="faq-list"' in html
        )
    else:
        r['rotated_faq'] = True  # N/A → pass
    r['canonical_https'] = bool(
        re.search(
            r'<link\s+rel="canonical"\s+href="https://gandago\.me/', html
        )
    )
    r['og_default'] = 'og-default.svg' in html and 'favicon.svg' not in (
        re.search(
            r'<meta\s+property="og:image"\s+content="([^"]+)"', html
        ).group(1)
        if re.search(r'<meta\s+property="og:image"', html) else ''
    )
    h1_m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', html)
    r['h1_present'] = bool(h1_m and h1_m.group(1).strip())

    # Particle bug detection — naive scan for impossible combos in our injected text
    # Look for "...동는 " (jongseong 동 should take 은) or "...구는 " etc.
    # Only check inside our injected blocks to avoid false positives.
    particle_bad = re.findall(
        r'class="region-(?:context|overview)"[^>]*>'
        r'<strong>([^<]+?)</strong>([은는])',
        html,
    )
    bad_particles = []
    for word, p in particle_bad:
        last = word.strip()[-1] if word.strip() else ''
        c = ord(last) if last else 0
        if 0xAC00 <= c <= 0xD7A3:
            has_jongseong = (c - 0xAC00) % 28 != 0
            expected = '은' if has_jongseong else '는'
            if p != expected:
                bad_particles.append((word, p, expected))
    r['particle_ok'] = not bad_particles
    if bad_particles:
        issues.append(f'particle:{bad_particles[0]}')

    # Adjust expectations: sibling_block is only required if siblings exist.
    if not has_siblings(path):
        r['sibling_block'] = True  # not applicable, treat as pass

    return {'path': rel, 'checks': r, 'issues': issues}


def main():
    pages = sorted(
        p for p in REGION_DIR.rglob('*.html') if '.git' not in p.parts
    )
    print(f'Verifying {len(pages)} region pages …\n')

    counts = {c: 0 for c in CHECKS}
    failing_examples = {c: [] for c in CHECKS}
    fully_passing = 0

    for p in pages:
        result = verify(p)
        all_pass = True
        for c, ok in result['checks'].items():
            if ok:
                counts[c] += 1
            else:
                all_pass = False
                if len(failing_examples[c]) < 5:
                    failing_examples[c].append(result['path'])
        if all_pass:
            fully_passing += 1

    total = len(pages)
    print('Per-check pass rates:')
    print(f'  {"check":<22} {"pass":>5} / {"total":<5}  {"failing examples"}')
    for c in CHECKS:
        miss = total - counts[c]
        examples = (
            '  e.g. ' + ', '.join(failing_examples[c][:2])
            if miss > 0 else ''
        )
        print(f'  {c:<22} {counts[c]:>5} / {total:<5}  ({miss} miss){examples}')

    print()
    print(f'Pages passing ALL checks: {fully_passing} / {total}')

    # Word-count distribution
    TAG_RE = re.compile(r'<[^>]+>')
    SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.S)
    ARTICLE_BODY_RE = re.compile(
        r'<div class="article-content">(.*?)</div>\s*</div>', re.S
    )

    wc_buckets = {'<100': 0, '100-300': 0, '300-500': 0, '500-800': 0, '>=800': 0}
    for p in pages:
        html = p.read_text(encoding='utf-8')
        m = ARTICLE_BODY_RE.search(html)
        if not m:
            continue
        body = SCRIPT_RE.sub(' ', m.group(1))
        body = TAG_RE.sub(' ', body)
        w = len(body.split())
        if w < 100:
            wc_buckets['<100'] += 1
        elif w < 300:
            wc_buckets['100-300'] += 1
        elif w < 500:
            wc_buckets['300-500'] += 1
        elif w < 800:
            wc_buckets['500-800'] += 1
        else:
            wc_buckets['>=800'] += 1
    print()
    print('Article word-count distribution:')
    for b in ['<100', '100-300', '300-500', '500-800', '>=800']:
        print(f'  {b}: {wc_buckets[b]}')


if __name__ == '__main__':
    main()
