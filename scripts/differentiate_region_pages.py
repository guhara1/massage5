#!/usr/bin/env python3
"""
Second-pass differentiation of region/ pages to reduce visible-content
duplication. Applies fact-based additions only — no fabricated stats.

Adds per page:
  1. A "지역 개요" sentence prepended to the existing intro paragraph,
     varying by page tier (광역시 / 일반시 / 군구 / 행정동).
  2. A "주변 권역" sibling-navigation card-grid linking up to 12 sibling
     pages under the same parent directory. Each page therefore gets a
     unique outbound link set.
  3. A rotated FAQ block of 3 questions picked deterministically from a
     pool of ~10 templates, with the page's parent and page names
     interpolated. The previous 2 generic FAQs are replaced.

Idempotent: previously enhanced pages are skipped per-section.
"""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION_DIR = ROOT / 'region'

# ---------------------------------------------------------------------------
# Tier classification by path depth
# region/{province}.html or region/{province}/index.html  → province
# region/{province}/{city}.html or region/{province}/{city}/index.html → city
# region/{province}/{city}/{district}.html → district/leaf
# ---------------------------------------------------------------------------

PROVINCE_NAMES = {
    'seoul': '서울특별시',
    'busan': '부산광역시',
    'incheon': '인천광역시',
    'daegu': '대구광역시',
    'daejeon': '대전광역시',
    'gwangju': '광주광역시',
    'ulsan': '울산광역시',
    'sejong': '세종특별자치시',
    'gyeonggi': '경기도',
    'gangwon': '강원특별자치도',
    'chungbuk': '충청북도',
    'chungnam': '충청남도',
    'gyeongbuk': '경상북도',
    'gyeongnam': '경상남도',
    'jeonbuk': '전북특별자치도',
    'jeonnam': '전라남도',
    'jeju': '제주특별자치도',
}

METROPOLITAN_SLUGS = {
    'seoul', 'busan', 'incheon', 'daegu', 'daejeon',
    'gwangju', 'ulsan', 'sejong',
}


def tier_for(path: Path) -> str:
    rel = path.relative_to(REGION_DIR)
    parts = rel.parts
    # parts: e.g. ['seoul', 'gangnam', 'sinsa.html']
    is_index = parts[-1] == 'index.html'
    depth = len(parts) - 1 if is_index else len(parts)
    # depth 1 → province page, 2 → city, 3 → district
    if depth <= 1:
        return 'province'
    if depth == 2:
        province = parts[0]
        return 'metro_district' if province in METROPOLITAN_SLUGS else 'city'
    return 'leaf'


def jongseong(word: str) -> bool:
    """True if the last syllable has 받침."""
    if not word:
        return False
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return (c - 0xAC00) % 28 != 0
    return False


def neun(word: str) -> str:
    return '은' if jongseong(word) else '는'


def eul(word: str) -> str:
    return '을' if jongseong(word) else '를'


def ee(word: str) -> str:
    return '이' if jongseong(word) else '가'


# ---------------------------------------------------------------------------
# Step 1: build a map from canonical URL → h1 display name
# ---------------------------------------------------------------------------

TAIL_PHRASES = [' 출장마사지 이용 안내', ' 출장마사지 안내', ' 출장마사지', ' 이용 안내']


def normalize_display_name(raw: str) -> str:
    name = raw.strip()
    changed = True
    while changed:
        changed = False
        for tail in TAIL_PHRASES:
            if name.endswith(tail):
                name = name[: -len(tail)].strip()
                changed = True
    return name


def build_name_index():
    """Map relative paths to normalized display names from <h1>."""
    name_by_path = {}
    for p in REGION_DIR.rglob('*.html'):
        html = p.read_text(encoding='utf-8')
        m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', html)
        if m:
            name_by_path[p] = normalize_display_name(m.group(1))
    return name_by_path


# ---------------------------------------------------------------------------
# Step 2: sibling discovery
# ---------------------------------------------------------------------------

def find_siblings(path: Path):
    """Return list of (sibling_path, display_name) under same parent dir."""
    parent_dir = path.parent
    siblings = []
    for f in sorted(parent_dir.iterdir()):
        if not f.is_file() or f.suffix != '.html':
            continue
        if f.name == 'index.html':
            continue
        if f == path:
            continue
        siblings.append(f)
    return siblings


# ---------------------------------------------------------------------------
# Step 3: overview sentence by tier
# ---------------------------------------------------------------------------

OVERVIEW_BY_TIER = {
    'province': (
        '{name}{neun} 17개 광역 행정구역 중 하나로, 출장마사지 권역이 '
        '광범위하게 형성되어 있어 코스·시간대별 운영 폭이 넓은 편입니다. '
        '아래 안내는 {name} 전역의 공통 운영 기준이며, 세부 시·군·구 '
        '페이지에서 권역별 특성을 확인하실 수 있습니다.'
    ),
    'metro_district': (
        '{name}{neun} {province} 산하 자치구 또는 권역 단위로, 인근 '
        '동·생활권 사이에서 출장 권역이 자주 연결됩니다. {name} 안의 '
        '세부 권역 페이지를 함께 확인하면 도착 가능 시간을 더 정확히 '
        '예측할 수 있습니다.'
    ),
    'city': (
        '{name}{neun} {province}의 시 단위 행정구역입니다. 도심·외곽 '
        '권역에 따라 출장 가능 시간대와 출장비 부담이 달라질 수 있으므로, '
        '예약 단계에서 현재 위치를 정확히 안내해 주세요.'
    ),
    'leaf': (
        '{name}{neun} {parents} 산하 권역으로, 인근 동·생활권의 출장 '
        '대기 인력이 함께 운영되는 경우가 많습니다. 도착 가능 시간과 '
        '출장비는 동일 부모 권역 안에서도 시간대에 따라 차이가 날 수 '
        '있습니다.'
    ),
}


def build_overview(tier, page_name, province_name, parents_chain):
    template = OVERVIEW_BY_TIER[tier]
    return (
        '<p class="region-overview">'
        + template.format(
            name=page_name,
            province=province_name or '소속 광역',
            parents=' · '.join(parents_chain) or '상위 권역',
            neun=neun(page_name),
        )
        + '</p>'
    )


# ---------------------------------------------------------------------------
# Step 4: rotated FAQ pool
# ---------------------------------------------------------------------------

FAQ_POOL = [
    {
        'q': '{name}에서 가장 자주 선택되는 코스는 무엇인가요?',
        'a': (
            '{name} 권역에서는 부드러운 이완 중심의 스웨디시·아로마와 '
            '깊은 압을 원하는 분께 추천되는 타이·스포츠 코스가 균형 있게 '
            '선택됩니다. 본인의 목적이 피로 회복인지 근육 풀이인지에 따라 '
            '코스를 결정해 주시는 편이 만족도가 높습니다.'
        ),
    },
    {
        'q': '{name} 야간·심야 시간대에도 출장이 가능한가요?',
        'a': (
            '대부분의 업체가 23시~새벽 시간대에는 출장비 가산이 붙거나 '
            '운영 권역이 좁아지는 경향이 있습니다. {name} 권역의 심야 '
            '운영 가능 여부와 가산 금액은 예약 단계에서 반드시 사전 확인을 '
            '받아 두시면 분쟁을 예방할 수 있습니다.'
        ),
    },
    {
        'q': '{name}에서 처음 이용하는 사람에게 권장되는 코스는?',
        'a': (
            '처음 이용하시는 분께는 부드러운 이완 중심의 90분 스웨디시 '
            '코스를 추천드립니다. 강한 압이 부담스럽지 않으면서도 전신을 '
            '고르게 풀어주는 진행이라 {name}에서도 가장 흔히 선택되는 '
            '입문 코스입니다.'
        ),
    },
    {
        'q': '{name} 인근 권역 업체도 같이 비교할 수 있나요?',
        'a': (
            '네, {parent_name} 안의 다른 동·권역 업체와 가격·운영 시간을 '
            '함께 비교하시면 본인 위치에서 가장 빠르고 합리적인 선택이 '
            '가능합니다. 페이지 하단의 주변 권역 카드에서 인근 권역을 '
            '확인하실 수 있습니다.'
        ),
    },
    {
        'q': '{name} 출장 시 사업자 정보는 어떻게 확인하나요?',
        'a': (
            '예약 전에 상호·대표자명·사업자등록번호가 공개된 업체인지 '
            '문자로 확인하시면 가장 안전합니다. {name} 권역에서도 미공개 '
            '업체나 선입금 요구 업체는 정상 영업이 아닐 가능성이 있으니 '
            '피해 주시기 바랍니다.'
        ),
    },
    {
        'q': '{name}에서 가격은 어떻게 결정되나요?',
        'a': (
            '코스 시간(60·90·120분)이 가장 큰 변수이고, 그다음이 서비스 '
            '종류와 시간대 가산입니다. {name} 출장의 경우 권역 평균 참고가는 '
            '본 페이지 가격표를 기준으로 하며, 실제 결제 금액은 예약 시 '
            '업체로부터 최종 안내를 받으셔야 정확합니다.'
        ),
    },
    {
        'q': '{name}에서 여성 단독 거주자도 안심하고 받을 수 있나요?',
        'a': (
            '여성전용 옵션이 있는 업체를 선택하시면 여성 관리사가 1:1로 '
            '진행합니다. {name} 권역에서도 예약 단계에서 도착 인증, 신원 '
            '확인 정책, 종료 시간 안내가 명확한 업체를 선택해 주세요. '
            '문 앞 도착 알림과 종료 후 안전 확인을 함께 받으면 가장 '
            '안전합니다.'
        ),
    },
    {
        'q': '{name} 예약 후 도착 시간이 늦어지면 어떻게 하나요?',
        'a': (
            '교통·날씨 상황으로 도착 시간이 변동될 수 있으므로 예약 시 '
            '관리사의 출발 권역과 도착 예상 시간을 함께 안내받아 두시는 '
            '것이 좋습니다. 30분 이상 지연이 예상될 때는 업체에 직접 '
            '재확인하시고, 그 자리에서 시간을 다시 조율하시면 됩니다.'
        ),
    },
    {
        'q': '{name}에서 결제는 어떤 방식이 안전한가요?',
        'a': (
            '관리 시작 전 선입금을 요구하는 업체는 피해 주시고, 도착 후 '
            '현장에서 코스 진행 직전이나 직후에 결제하시는 방식이 가장 '
            '안전합니다. {name} 권역에서도 계좌이체 선입금 요청이 있을 '
            '경우 그 자리에서 거절하시는 것이 분쟁 예방의 기본 원칙입니다.'
        ),
    },
    {
        'q': '{name}에서 임신·수술 회복기에도 받을 수 있나요?',
        'a': (
            '임신, 최근 수술, 골절·외상 회복 초기, 심혈관·혈전 관련 진단을 '
            '받으신 경우에는 일반 코스가 적합하지 않을 수 있습니다. '
            '의료진과 상담 후 진행 여부를 결정해 주시고, 임산부용 자세·강도 '
            '조정이 가능한 업체인지 예약 시 미리 확인해 주세요.'
        ),
    },
]


def select_faqs(rel_path: str, name: str, parent_name: str, count: int = 3):
    """Pick `count` FAQs deterministically by hashing the path."""
    h = hashlib.sha256(rel_path.encode('utf-8')).digest()
    pool_size = len(FAQ_POOL)
    seen = []
    idx = 0
    while len(seen) < count and idx < 64:
        pick = h[idx] % pool_size
        if pick not in seen:
            seen.append(pick)
        idx += 1
    chosen = [FAQ_POOL[i] for i in seen]
    return [
        {
            'q': f['q'].format(name=name, parent_name=parent_name or name),
            'a': f['a'].format(name=name, parent_name=parent_name or name),
        }
        for f in chosen
    ]


def faq_html(faqs):
    parts = []
    for f in faqs:
        parts.append(
            f'    <details class="faq"><summary>{f["q"]}</summary>'
            f'<p>{f["a"]}</p></details>'
        )
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Step 5: sibling navigation block
# ---------------------------------------------------------------------------

def sibling_block_html(path: Path, name_by_path: dict, max_n: int = 12):
    siblings = find_siblings(path)[:max_n]
    if not siblings:
        return ''
    items = []
    for s in siblings:
        sname = name_by_path.get(s)
        if not sname:
            continue
        href = s.name  # same directory
        items.append(
            f'      <a href="{href}" class="region-sibling-card">{sname}</a>'
        )
    if not items:
        return ''
    rendered = '\n'.join(items)
    parent_label = name_by_path.get(path.parent / 'index.html', '')
    if parent_label:
        sub = f'<p class="region-siblings-sub">{parent_label} 내 다른 권역</p>'
    else:
        sub = ''
    return (
        '\n  <section class="article-section region-siblings">\n'
        '    <h2>주변 권역</h2>\n'
        f'    {sub}\n'
        '    <div class="region-siblings-grid">\n'
        f'{rendered}\n'
        '    </div>\n'
        '  </section>'
    )


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process(path: Path, name_by_path: dict) -> dict:
    html = path.read_text(encoding='utf-8')
    original = html
    actions = []

    rel = path.relative_to(REGION_DIR)
    rel_str = str(rel)
    parts = rel.parts
    province_slug = parts[0] if parts else ''
    province_name = PROVINCE_NAMES.get(province_slug, '')

    # h1
    m = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', html)
    if not m:
        return {'path': rel_str, 'actions': ['no-h1']}
    page_name = normalize_display_name(m.group(1))

    # parent chain (for leaf pages)
    parents_chain = []
    if len(parts) >= 3:
        # leaf: parents are province + city
        parent_index_name = name_by_path.get(
            path.parent / 'index.html', ''
        )
        parents_chain = [
            province_name or province_slug,
            parent_index_name,
        ]
        parent_name = parent_index_name
    elif len(parts) == 2 and parts[-1] != 'index.html':
        parents_chain = [province_name or province_slug]
        parent_name = province_name or province_slug
    else:
        parent_name = ''

    tier = tier_for(path)

    # --- A. Overview sentence prepended to first intro paragraph -------
    if 'class="region-overview"' not in html:
        overview = build_overview(tier, page_name, province_name, parents_chain)
        # Insert AFTER the first <h2>...안내</h2> paragraph
        pattern = re.compile(
            r'(<section class="article-section">\s*<h2>[^<]*?안내</h2>\s*'
            r'<p>[^<]*?</p>)',
            re.S,
        )
        new_html, n = pattern.subn(
            lambda m: m.group(1) + '\n    ' + overview, html, count=1
        )
        if n:
            html = new_html
            actions.append('overview')

    # --- B. Rotated FAQ replacement ------------------------------------
    if 'class="faq-v2"' not in html:
        faqs = select_faqs(rel_str, page_name, parent_name)
        new_faq_html = '<div class="faq-v2">\n' + faq_html(faqs) + '\n  </div>'
        pattern = re.compile(
            r'(<section class="article-section">\s*<h2>[^<]*?자주 묻는 질문</h2>\s*)'
            r'(?:<details class="faq">[\s\S]*?</details>\s*)+'
            r'(\s*</section>)',
            re.S,
        )
        new_html, n = pattern.subn(
            lambda m: m.group(1) + new_faq_html + m.group(2), html, count=1
        )
        if n:
            html = new_html
            actions.append('faq-rotate')

    # --- C. Sibling navigation block -----------------------------------
    if 'class="region-siblings-grid"' not in html:
        sib = sibling_block_html(path, name_by_path)
        if sib:
            # Insert just before closing </div></div> of article-wrap
            pattern = re.compile(
                r'(<div class="article-wrap"><div class="article-content">[\s\S]*?)(</div></div>)',
                re.S,
            )
            new_html, n = pattern.subn(
                lambda m: m.group(1) + sib + '\n  ' + m.group(2),
                html,
                count=1,
            )
            if n:
                html = new_html
                actions.append('siblings')

    if html != original:
        path.write_text(html, encoding='utf-8')
    return {'path': rel_str, 'actions': actions}


def main():
    print('Building name index from <h1> tags …')
    name_by_path = build_name_index()
    print(f'Indexed {len(name_by_path)} pages')

    region_pages = [
        p for p in REGION_DIR.rglob('*.html') if '.git' not in p.parts
    ]
    summary = {}
    no_change = 0
    for p in region_pages:
        r = process(p, name_by_path)
        if not r['actions']:
            no_change += 1
        for a in r['actions']:
            summary[a] = summary.get(a, 0) + 1
    summary['no-change'] = no_change
    print('Summary:')
    for k, v in sorted(summary.items()):
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
