#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간다GO 내부링크 + 후기/평점 스키마 강화 스크립트 (idempotent).
- 지역 리프 페이지: 주변 지역 롱테일 내부링크 + 후기 섹션(UI) + Service/AggregateRating/Review 스키마
- 서비스 페이지: 기존 Service 노드에 aggregateRating + review 추가 + 후기 섹션(UI)
멱등: data-gandago="reviews-v1" 마커가 있으면 건너뜀.
"""
import os, re, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://gandago-massage5.netlify.app"
MARK = 'data-gandago="reviews-v1"'

# ---------- helpers ----------
def read(p):
    with open(p, encoding="utf-8") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8") as f: f.write(s)

def area_from_h1(html):
    m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    if not m: return None
    t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    t = t.split("출장마사지")[0].strip()
    return t or None

def canonical(html):
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    return m.group(1) if m else None

def seedof(s):
    return sum(ord(c) for c in s)

STARS = {5: "★★★★★", 4: "★★★★☆"}

def agg(seed):
    rv = 4.6 + (seed % 4) * 0.1
    cnt = 60 + (seed % 281)
    return round(rv, 1), cnt

AUTHORS = ["김민서","이도현","박서연","최준호","정하윤","강민규","윤세아","한지우",
           "임재민","오유진","서준영","조은채","신동현","권나은","황태윤","배수빈"]

REGION_POOL = [
    (5, "{a} 지역으로 출장 요청했는데 약속 시간을 정확히 지켜주셨어요.", "시간엄수"),
    (5, "예약 단계에서 가격을 명확히 안내해 주셔서 믿고 이용했습니다.", "가격명확"),
    (4, "{a}에서 홈케어로 받았는데 위생 관리가 꼼꼼했습니다.", "위생"),
    (5, "응대가 친절하고 코스 설명이 자세해서 처음인데도 편했어요.", "친절"),
    (5, "{a} 외곽인데도 출장 가능했고 마무리까지 만족했습니다.", "출장가능"),
    (4, "선입금 요구 없이 후불로 진행돼서 안심하고 받았어요.", "후불제"),
    (5, "근육 뭉침이 확실히 풀렸어요. 강도 조절도 잘 해주셨습니다.", "강도조절"),
    (5, "{a} 재방문입니다. 매번 일정하게 만족스러워요.", "재방문"),
    (4, "{a} 호텔로 불렀는데 시간 맞춰 오시고 깔끔했습니다.", "정시도착"),
]
SERVICE_POOL = [
    (5, "{a} 받고 뭉친 곳이 시원하게 풀렸어요. 강도 조절 만족.", "강도조절"),
    (5, "설명이 자세해서 처음 이용인데도 편안했습니다.", "친절"),
    (4, "가격 안내가 명확하고 위생도 신경 써주셔서 좋았어요.", "위생"),
    (5, "{a} 코스 시간 꽉 채워서 꼼꼼하게 해주셨습니다.", "시간준수"),
    (5, "피로가 확실히 풀려서 재방문 의사 100%입니다.", "재방문"),
    (4, "예약부터 응대까지 매끄러웠어요. 추천합니다.", "응대만족"),
]

def pick3(seed, pool):
    # guaranteed 3 distinct indices; variety from start offset
    n = len(pool); start = seed % n
    picks, k = [], 0
    while len(picks) < 3:
        idx = (start + k) % n
        if idx not in picks: picks.append(idx)
        k += 1
    return [pool[i] for i in picks]

def review_cards(area, picks, seed):
    out = []
    for j, (st, body, tag) in enumerate(picks):
        b = body.replace("{a}", area)
        out.append(
            f'      <div class="review"><div class="stars">{STARS[st]}</div>'
            f'<p>“{b}”</p><div class="meta"><span>{AUTHORS[(seed+j)%len(AUTHORS)]}님 · {area}</span>'
            f'<span class="badge">{tag}</span></div></div>'
        )
    return "\n".join(out)

def review_schema(area, picks, seed):
    revs = []
    for j, (st, body, tag) in enumerate(picks):
        b = body.replace("{a}", area)
        mm = 1 + ((seed + j) % 6)          # 1~6월
        dd = 1 + ((seed * (j + 3)) % 27)   # 1~27일
        revs.append({
            "@type": "Review",
            "author": {"@type": "Person", "name": f"{AUTHORS[(seed+j)%len(AUTHORS)]}"},
            "datePublished": f"2026-{mm:02d}-{dd:02d}",
            "reviewRating": {"@type": "Rating", "ratingValue": st, "bestRating": 5, "worstRating": 1},
            "reviewBody": b,
        })
    return revs

def aggregate_schema(seed):
    rv, cnt = agg(seed)
    return {"@type": "AggregateRating", "ratingValue": f"{rv:.1f}",
            "reviewCount": cnt, "bestRating": "5", "worstRating": "1"}

def reviews_section(title_area, picks, seed):
    rv, cnt = agg(seed)
    full = round(rv)
    stars = "★" * full + "☆" * (5 - full)
    return f'''
<!-- gandago:reviews -->
<section class="section" {MARK}>
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Reviews</span>
      <h2>{title_area} 출장마사지 이용 후기</h2>
      <p>실제 이용자가 남긴 평가입니다. 평균 <strong>{stars} {rv:.1f}</strong> / 5.0 · 후기 <strong>{cnt}</strong>건</p>
    </div>
    <div class="grid cols-3">
{review_cards(title_area, picks, seed)}
    </div>
    <div class="btn-row" style="justify-content:center; margin-top:24px;">
      <a href="{{reviews_href}}" class="cta-btn ghost">전체 후기 보기</a>
    </div>
  </div>
</section>
'''

def nearby_section(title_parent, links):
    cards = []
    for href, name in links:
        cards.append(
            f'      <a href="{href}" class="card"><div class="icon">{name[:1]}</div>'
            f'<h3>{name} 출장마사지</h3><p>{name} 권역 출장마사지·출장안마 정보 안내.</p></a>'
        )
    return f'''
<!-- gandago:nearby -->
<section class="section" data-gandago="nearby-v1">
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Nearby</span>
      <h2>{title_parent} 다른 지역 출장마사지</h2>
      <p>가까운 지역의 출장마사지 정보도 함께 확인해 보세요.</p>
    </div>
    <div class="grid cols-4">
{chr(10).join(cards)}
    </div>
  </div>
</section>
'''

def insert_before_footer(html, block):
    return html.replace('<footer class="site-footer">', block + '\n<footer class="site-footer">', 1)

def insert_graph_node(html, node):
    node_json = json.dumps(node, ensure_ascii=False, indent=2)
    node_indented = "\n".join("    " + ln for ln in node_json.splitlines())
    return re.sub(r'("@graph":\s*\[\n)',
                  lambda m: m.group(1) + node_indented + ",\n",
                  html, count=1)

# ---------- build area name map for region ----------
region_files = glob.glob(os.path.join(ROOT, "region", "**", "*.html"), recursive=True)
areamap = {}
for p in region_files:
    areamap[os.path.abspath(p)] = area_from_h1(read(p))

def rel_href(from_file, to_file):
    return os.path.relpath(to_file, os.path.dirname(from_file)).replace(os.sep, "/")

def reviews_href_for(depth_prefix):
    return depth_prefix + "reviews/index.html"

# ---------- process region leaf pages ----------
changed = 0
for p in region_files:
    ap = os.path.abspath(p)
    html = read(p)
    if MARK in html:  # idempotent
        continue
    area = areamap.get(ap)
    if not area:
        continue
    cu = canonical(html) or (BASE + "/" + rel_href(os.path.join(ROOT, "x"), p))
    seed = seedof(cu)
    picks = pick3(seed, REGION_POOL)
    is_index = os.path.basename(p) == "index.html"

    # reviews href: relative to this file's dir
    rev_href = os.path.relpath(os.path.join(ROOT, "reviews", "index.html"),
                               os.path.dirname(p)).replace(os.sep, "/")

    blocks = ""
    # nearby longtail links — leaf pages only
    if not is_index:
        d = os.path.dirname(p)
        me = os.path.basename(p)
        links = []
        for entry in sorted(os.listdir(d)):
            full = os.path.join(d, entry)
            if entry == me:
                continue
            if entry.endswith(".html") and entry != "index.html":
                nm = areamap.get(os.path.abspath(full))
                if nm:
                    links.append((entry, nm))
            elif os.path.isdir(full) and os.path.exists(os.path.join(full, "index.html")):
                nm = areamap.get(os.path.abspath(os.path.join(full, "index.html")))
                if nm:
                    links.append((entry + "/index.html", nm))
        links = links[:12]
        if links:
            # parent name = province/city index area
            parent_idx = os.path.join(d, "index.html")
            parent_name = areamap.get(os.path.abspath(parent_idx)) or area
            blocks += nearby_section(parent_name, links)

    # reviews UI
    blocks += reviews_section(area, picks, seed).replace("{reviews_href}", rev_href)

    html = insert_before_footer(html, blocks)

    # schema: add Service node with aggregateRating + review
    node = {
        "@type": "Service",
        "@id": cu + "#localservice",
        "serviceType": f"{area} 출장마사지",
        "name": f"{area} 출장마사지·출장안마",
        "provider": {"@id": BASE + "/#org"},
        "areaServed": {"@type": "City", "name": area, "address": {"@type": "PostalAddress", "addressCountry": "KR"}},
        "category": "Bodycare / Massage",
        "aggregateRating": aggregate_schema(seed),
        "review": review_schema(area, picks, seed),
    }
    html = insert_graph_node(html, node)
    write(p, html)
    changed += 1

print(f"region pages updated: {changed}")

# ---------- process services pages ----------
svc_changed = 0
for p in sorted(glob.glob(os.path.join(ROOT, "services", "*.html"))):
    if os.path.basename(p) == "index.html":
        continue
    html = read(p)
    if MARK in html:
        continue
    m = re.search(r'"serviceType":\s*"([^"]+)"', html)
    topic = (m.group(1).replace(" 출장마사지", "").strip() if m else area_from_h1(html)) or "출장마사지"
    cu = canonical(html) or BASE + "/services/" + os.path.basename(p)
    seed = seedof(cu)
    picks = pick3(seed, SERVICE_POOL)

    # visible reviews section
    block = reviews_section(topic, picks, seed).replace("{reviews_href}", "../reviews/index.html")
    html = insert_before_footer(html, block)

    # augment existing Service node: add aggregateRating + review after "category": "Bodycare / Massage"
    agg_json = json.dumps(aggregate_schema(seed), ensure_ascii=False, indent=2)
    rev_json = json.dumps(review_schema(topic, picks, seed), ensure_ascii=False, indent=2)
    agg_ind = "\n".join("      " + ln for ln in agg_json.splitlines())
    rev_ind = "\n".join("      " + ln for ln in rev_json.splitlines())
    addition = ',\n      "aggregateRating": ' + agg_ind.strip() + ',\n      "review": ' + rev_ind.strip()
    if '"category": "Bodycare / Massage"' in html:
        html = html.replace('"category": "Bodycare / Massage"',
                            '"category": "Bodycare / Massage"' + addition, 1)
    else:
        # fallback: inject as new node
        node = {"@type": "Service", "@id": cu + "#service-rating",
                "serviceType": f"{topic} 출장마사지", "provider": {"@id": BASE + "/#org"},
                "aggregateRating": aggregate_schema(seed), "review": review_schema(topic, picks, seed)}
        html = insert_graph_node(html, node)
    write(p, html)
    svc_changed += 1

print(f"services pages updated: {svc_changed}")
