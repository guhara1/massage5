#!/usr/bin/env python3
"""
Enhance all region/ HTML pages to mitigate Scaled Content Abuse / FAQ schema
spam signals while preserving the page set.

Each pass is idempotent: a second run on the same file is a no-op.

Changes per page:
  1. Inject a Han Jiwoo author byline below the page-header description.
  2. Insert an Article (author=Person) into the JSON-LD @graph.
  3. Remove the FAQPage block from the JSON-LD @graph.
  4. Replace the price-section intro paragraph with a source-attribution
     sentence (industry average reference, not a per-region quote).
  5. Inject a one-sentence hierarchy context line under the article's
     opening paragraph using the breadcrumb already on the page.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION_DIR = ROOT / 'region'

PRICE_INTRO_NEW = (
    '<p>아래 가격은 <strong>전국 권역 평균 참고가</strong>로, 간다GO 편집팀이 '
    '주요 도시 출장마사지 시세를 모니터링하여 정리한 자료입니다. 지역별 차등 '
    '없이 동일 범위를 적용하며, 출장비·심야 가산·코스 옵션에 따라 달라집니다. '
    '실제 결제 금액은 예약 단계에서 업체로부터 직접 안내받아 주세요.</p>'
)

PRICE_INTRO_OLD = (
    r'<p>[^<]*권역 안에서 일반적으로 운영되는 코스의 가격대 가이드입니다[^<]*</p>'
)

JSONLD_BLOCK_RE = re.compile(
    r'(<script type="application/ld\+json">\s*)(\{[\s\S]*?\})(\s*</script>)'
)


def relative_about_prefix(path: Path) -> str:
    depth = len(path.relative_to(ROOT).parts) - 1
    return '../' * depth


def korean_subject_particle(word: str) -> str:
    """Return '은' or '는' based on last syllable's 받침 presence."""
    if not word:
        return '는'
    last = word[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        if (code - 0xAC00) % 28 == 0:
            return '는'  # no final consonant -> vowel-ending
        return '은'  # has final consonant
    # non-Korean character fallback
    return '는'


def parse_breadcrumb_items(html: str):
    """Return list of breadcrumb names in order (without separators)."""
    m = re.search(r'<div class="breadcrumb">(.*?)</div>', html, re.S)
    if not m:
        return []
    chunk = m.group(1)
    items = []
    for sub in re.finditer(
        r'(?:<a\s+href="[^"]+"\s*>\s*([^<]+?)\s*</a>)'
        r'|(?:<span(?:\s[^>]*)?>\s*([^<]+?)\s*</span>)',
        chunk,
    ):
        name = (sub.group(1) or sub.group(2) or '').strip()
        if name and name not in ('/', '·'):
            items.append(name)
    return items


def build_hierarchy_sentence(items, current_name):
    chain = [n for n in items if n not in ('홈', '지역별 찾기')]
    if chain and chain[-1] == current_name:
        chain = chain[:-1]
    if not chain:
        return ''
    parents = ' > '.join(chain)
    particle = korean_subject_particle(current_name)
    return (
        f'\n    <p class="region-context"><strong>{current_name}</strong>'
        f'{particle} <em>{parents}</em>에 속한 권역입니다. 인근 권역 정보는 '
        f'상위 페이지에서 함께 확인하실 수 있습니다.</p>'
    )


def modify_jsonld(jsonld_str: str, url: str, headline: str, desc: str):
    """Return (new_jsonld_str, changes_set) after manipulating @graph."""
    changes = set()
    data = json.loads(jsonld_str)
    graph = data.get('@graph', [])

    # 1. Drop FAQPage objects
    new_graph = [obj for obj in graph if obj.get('@type') != 'FAQPage']
    if len(new_graph) != len(graph):
        changes.add('drop-faqpage')
    graph = new_graph

    # 2. Add Article object if absent
    has_article = any(obj.get('@type') == 'Article' for obj in graph)
    if not has_article and url and headline:
        article = {
            '@type': 'Article',
            '@id': f'{url}#article',
            'headline': headline,
            'description': desc or headline,
            'datePublished': '2026-05-12T09:00:00+09:00',
            'dateModified': '2026-05-17T09:00:00+09:00',
            'author': {
                '@type': 'Person',
                '@id': 'https://gandago.me/about/authors/han-jiwoo.html#person',
                'name': '한지우',
                'url': 'https://gandago.me/about/authors/han-jiwoo.html',
                'jobTitle': '시니어 에디터',
                'worksFor': {'@id': 'https://gandago.me/#org'},
            },
            'publisher': {'@id': 'https://gandago.me/#org'},
            'mainEntityOfPage': {'@id': url},
            'inLanguage': 'ko-KR',
            'image': 'https://gandago.me/assets/og-default.svg',
        }
        # Insert after Organization for readability
        insert_at = 1
        for i, obj in enumerate(graph):
            if obj.get('@type') == 'Organization':
                insert_at = i + 1
                break
        graph.insert(insert_at, article)
        changes.add('article')

    data['@graph'] = graph
    new_jsonld = json.dumps(data, ensure_ascii=False, indent=2)
    return new_jsonld, changes


def process(path: Path) -> dict:
    html = path.read_text(encoding='utf-8')
    actions = []
    original = html

    # Extract metadata
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html)
    canonical = m.group(1) if m else ''

    m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', html)
    h1 = m.group(1).strip() if m else ''

    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    desc = m.group(1).strip() if m else ''

    breadcrumb_items = parse_breadcrumb_items(html)
    current_name = breadcrumb_items[-1] if breadcrumb_items else ''

    # --- 1. Byline ----------------------------------------------------
    if 'class="post-meta region-byline"' not in html:
        rel_about = relative_about_prefix(path)
        byline = (
            f'\n  <p class="post-meta region-byline">\n'
            f'    <a href="{rel_about}about/authors/han-jiwoo.html" rel="author">한지우</a>'
            f' · 시니어 에디터 · 2026년 5월 17일 갱신\n'
            f'  </p>'
        )
        pattern = re.compile(r'(<h1[^>]*>[^<]+</h1>\s*<p>[^<]*</p>)', re.S)
        new_html, n = pattern.subn(lambda m: m.group(1) + byline, html, count=1)
        if n:
            html = new_html
            actions.append('byline')

    # --- 2 + 3. JSON-LD manipulation ---------------------------------
    m = JSONLD_BLOCK_RE.search(html)
    if m and canonical and h1:
        prefix, jsonld_str, suffix = m.group(1), m.group(2), m.group(3)
        try:
            new_jsonld, changes = modify_jsonld(
                jsonld_str, canonical, h1, desc
            )
            if changes:
                html = (
                    html[: m.start(2)] + new_jsonld + html[m.end(2):]
                )
                actions.extend(sorted(changes))
        except json.JSONDecodeError as e:
            actions.append(f'jsonld-skip:{e.msg[:30]}')

    # --- 4. Price intro replacement ----------------------------------
    if '권역 평균 참고가' not in html:
        new_html, n = re.subn(
            PRICE_INTRO_OLD,
            PRICE_INTRO_NEW,
            html,
            count=1,
        )
        if n:
            html = new_html
            actions.append('price-attribution')

    # --- 5. Hierarchy context ----------------------------------------
    if (
        'class="region-context"' not in html
        and current_name
        and len(breadcrumb_items) > 2
    ):
        sentence = build_hierarchy_sentence(breadcrumb_items, current_name)
        if sentence:
            pattern = re.compile(
                r'(<section class="article-section">\s*<h2>[^<]*?안내</h2>\s*<p>[^<]*?</p>)',
                re.S,
            )
            new_html, n = pattern.subn(
                lambda m: m.group(1) + sentence, html, count=1
            )
            if n:
                html = new_html
                actions.append('hierarchy')

    if html != original:
        path.write_text(html, encoding='utf-8')
    return {'path': str(path.relative_to(ROOT)), 'actions': actions}


def main():
    region_pages = [
        p for p in REGION_DIR.rglob('*.html') if '.git' not in p.parts
    ]
    print(f'Found {len(region_pages)} region pages')

    summary = {}
    no_change = 0
    errors = []
    for p in region_pages:
        result = process(p)
        if not result['actions']:
            no_change += 1
        for act in result['actions']:
            summary[act] = summary.get(act, 0) + 1
            if act.startswith('jsonld-skip'):
                errors.append((result['path'], act))

    summary['no-change'] = no_change
    print('Summary:')
    for k, v in sorted(summary.items()):
        print(f'  {k}: {v}')
    if errors:
        print(f'\n{len(errors)} JSON parse errors. First 5:')
        for path, err in errors[:5]:
            print(f'  {path}: {err}')


if __name__ == '__main__':
    main()
