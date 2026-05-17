#!/usr/bin/env python3
"""
Read-only SEO/E-E-A-T audit across all HTML pages.

Outputs a JSON-line report to stdout summarizing per-page signals AND a
final aggregate section with policy-mapped findings.

No file modifications.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TAG_RE = re.compile(r'<[^>]+>')
SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.S)
STYLE_RE = re.compile(r'<style\b[^>]*>.*?</style>', re.S)
COMMENT_RE = re.compile(r'<!--.*?-->', re.S)

ARTICLE_BODY_RE = re.compile(
    r'<div class="article-content">(.*?)</div>\s*</div>', re.S
)


def visible_text(html: str) -> str:
    h = SCRIPT_RE.sub(' ', html)
    h = STYLE_RE.sub(' ', h)
    h = COMMENT_RE.sub(' ', h)
    h = TAG_RE.sub(' ', h)
    h = re.sub(r'\s+', ' ', h).strip()
    return h


def article_text(html: str) -> str:
    m = ARTICLE_BODY_RE.search(html)
    if not m:
        return ''
    return visible_text(m.group(1))


def first(pattern, html, group=1, flags=0):
    m = re.search(pattern, html, flags)
    return m.group(group) if m else ''


def count_re(pattern, html, flags=0):
    return len(re.findall(pattern, html, flags))


def audit(path: Path):
    rel = str(path.relative_to(ROOT))
    html = path.read_text(encoding='utf-8', errors='replace')
    text = visible_text(html)
    art = article_text(html)

    title = first(r'<title>([^<]*)</title>', html)
    meta_desc = first(
        r'<meta\s+name="description"\s+content="([^"]*)"', html
    )
    canonical = first(
        r'<link\s+rel="canonical"\s+href="([^"]*)"', html
    )
    og_image = first(
        r'<meta\s+property="og:image"\s+content="([^"]*)"', html
    )
    has_viewport = 'name="viewport"' in html
    has_https_canonical = canonical.startswith('https://')

    h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S)

    imgs = re.findall(r'<img\b[^>]*>', html)
    imgs_with_alt = [i for i in imgs if re.search(r'\balt=', i)]
    imgs_with_nonempty_alt = [
        i for i in imgs if re.search(r'\balt="[^"]+"', i)
    ]

    a_tags = re.findall(r'<a\b[^>]*href="([^"]*)"', html)
    internal = [a for a in a_tags if not a.startswith('http') or 'gandago.me' in a]
    external = [a for a in a_tags if a.startswith('http') and 'gandago.me' not in a]
    tel_links = [a for a in a_tags if a.startswith('tel:')]

    has_article_schema = '"@type": "Article"' in html
    has_service_schema = '"@type": "Service"' in html
    has_faq_schema = '"@type": "FAQPage"' in html
    has_person_author = (
        '"@type": "Person"' in html
        and '"author"' in html
    )
    has_review_schema = '"@type": "Review"' in html
    has_breadcrumb = '"@type": "BreadcrumbList"' in html

    byline_link = 'rel="author"' in html

    word_count_total = len(text.split())
    word_count_article = len(art.split()) if art else 0

    # Detect probable templated content: very short article body with stock phrases.
    template_signals = 0
    stock_phrases = [
        '이용 가능한 마사지 프로그램',
        '자주 묻는 질문',
        '안전 안내:',
        '선입금 요구는 응하지',
        '5~8만원대',  # appears on many region pages as a hard-coded price
        '60분',
        '거주민 정기',
    ]
    for p in stock_phrases:
        if p in html:
            template_signals += 1

    return {
        'path': rel,
        'depth': rel.count('/'),
        'section': rel.split('/', 1)[0] if '/' in rel else 'root',
        'title': title,
        'title_len': len(title),
        'meta_desc_len': len(meta_desc),
        'canonical_https': has_https_canonical,
        'og_image': og_image,
        'has_viewport': has_viewport,
        'h1_count': len(h1s),
        'h2_count': len(h2s),
        'img_count': len(imgs),
        'img_with_alt': len(imgs_with_alt),
        'img_with_nonempty_alt': len(imgs_with_nonempty_alt),
        'internal_links': len(internal),
        'external_links': len(external),
        'tel_links': len(tel_links),
        'has_article_schema': has_article_schema,
        'has_service_schema': has_service_schema,
        'has_faq_schema': has_faq_schema,
        'has_person_author': has_person_author,
        'has_review_schema': has_review_schema,
        'has_breadcrumb': has_breadcrumb,
        'byline_link': byline_link,
        'word_count_total': word_count_total,
        'word_count_article': word_count_article,
        'template_signal_score': template_signals,
        'file_bytes': len(html.encode('utf-8')),
    }


def main():
    out = []
    for html in sorted(ROOT.rglob('*.html')):
        if '.git' in html.parts:
            continue
        out.append(audit(html))

    # Aggregate
    by_section = defaultdict(list)
    for r in out:
        by_section[r['section']].append(r)

    section_summary = {}
    for sec, rows in by_section.items():
        n = len(rows)
        section_summary[sec] = {
            'pages': n,
            'avg_word_count_total': round(
                sum(r['word_count_total'] for r in rows) / n, 1
            ),
            'avg_word_count_article': round(
                sum(r['word_count_article'] for r in rows) / n, 1
            ),
            'short_article_count_lt_300': sum(
                1 for r in rows if r['word_count_article'] < 300
            ),
            'short_article_count_lt_500': sum(
                1 for r in rows if r['word_count_article'] < 500
            ),
            'imgs_missing_alt': sum(
                r['img_count'] - r['img_with_nonempty_alt'] for r in rows
            ),
            'pages_with_byline_link': sum(1 for r in rows if r['byline_link']),
            'pages_with_article_schema': sum(
                1 for r in rows if r['has_article_schema']
            ),
            'pages_with_service_schema': sum(
                1 for r in rows if r['has_service_schema']
            ),
            'pages_with_faq_schema': sum(
                1 for r in rows if r['has_faq_schema']
            ),
            'pages_with_review_schema': sum(
                1 for r in rows if r['has_review_schema']
            ),
            'pages_canonical_https': sum(
                1 for r in rows if r['canonical_https']
            ),
            'pages_og_default': sum(
                1 for r in rows if 'og-default' in r['og_image']
            ),
            'avg_template_signal_score': round(
                sum(r['template_signal_score'] for r in rows) / n, 2
            ),
            'avg_internal_links': round(
                sum(r['internal_links'] for r in rows) / n, 1
            ),
            'pages_with_external_links': sum(
                1 for r in rows if r['external_links'] > 0
            ),
        }

    # Title duplicates
    title_counts = Counter(r['title'] for r in out)
    duplicate_titles = [
        (t, c) for t, c in title_counts.most_common() if c > 1
    ][:20]

    desc_counts = Counter(r['meta_desc_len'] for r in out)

    # Total external links across the site
    total_external_links = sum(r['external_links'] for r in out)
    total_pages_with_external = sum(1 for r in out if r['external_links'] > 0)

    # Probable templated-region pages: depth>=2 in region/, short article,
    # high template signal.
    region_rows = [r for r in out if r['section'] == 'region']
    likely_templated = [
        r for r in region_rows
        if r['word_count_article'] < 600 and r['template_signal_score'] >= 4
    ]

    print('===== SECTION SUMMARY =====')
    for sec, s in sorted(section_summary.items()):
        print(f'\n## {sec} ({s["pages"]} pages)')
        for k, v in s.items():
            if k == 'pages':
                continue
            print(f'  {k}: {v}')

    print('\n===== DUPLICATE TITLES (top 20) =====')
    for t, c in duplicate_titles:
        print(f'  {c}x  {t[:80]}')

    print('\n===== EXTERNAL LINKS =====')
    print(f'  total external links across site: {total_external_links}')
    print(f'  pages with at least one external link: {total_pages_with_external}')

    print('\n===== TEMPLATED REGION PAGES =====')
    print(
        f'  region pages flagged as likely-templated '
        f'(<600 article words AND >=4 template signals): '
        f'{len(likely_templated)} / {len(region_rows)}'
    )

    # Path distribution by template_signal_score
    score_dist = Counter(r['template_signal_score'] for r in region_rows)
    print('  region template_signal_score distribution:')
    for s in sorted(score_dist):
        print(f'    score={s}: {score_dist[s]} pages')

    # word count distribution
    wc_buckets = Counter()
    for r in region_rows:
        w = r['word_count_article']
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
    print('  region article-word-count distribution:')
    for b in ['<100', '100-300', '300-500', '500-800', '>=800']:
        print(f'    {b}: {wc_buckets.get(b, 0)} pages')


if __name__ == '__main__':
    main()
