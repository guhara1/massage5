#!/usr/bin/env python3
"""
간다GO 매거진 자동 생성기.

- topic_queue.json 에서 사용하지 않은 다음 주제 1개 선택
- Anthropic API (Claude Opus 4.7) 로 사람 글 톤의 본문 생성
- 품질 가드 (분량/구조/금지어) 통과 후 HTML 저장
- /magazine/index.html 최신 글 섹션 갱신
- /sitemap.xml 갱신
- topic 을 used:true 처리
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib.request
import urllib.error
from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "https://gandago.me"
KST = timezone(timedelta(hours=9))

POSTS_DIR = ROOT / "magazine" / "posts"
QUEUE_PATH = ROOT / "scripts" / "topic_queue.json"
MAGAZINE_INDEX = ROOT / "magazine" / "index.html"
SITEMAP = ROOT / "sitemap.xml"

MODEL = "claude-opus-4-5"

BANNED_TERMS = [
    "1등", "최고", "100%", "완벽", "보장", "베스트", "1위",
    "추천 1순위", "치료된다", "낫는다", "효과가 확실"
]


def load_queue() -> dict:
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def save_queue(q: dict) -> None:
    QUEUE_PATH.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_topic(q: dict) -> dict | None:
    for t in q["topics"]:
        if not t.get("used"):
            return t
    return None


COMMON_BLOCK = """[분량]
한글 기준 본문 합계 2,500자 ± 100자.

[구조]
- 본문은 H2 다섯 개. 각 제목 앞에 "1. ", "2. ", "3. ", "4. ", "5. ".
- 각 H2 아래는 오직 평문 문단만. 목록(불릿/번호), 표, 굵은체, 이탤릭, 강조부호, 코드블록 모두 금지.
- 각 H2 본문은 약 500자.

[문체 — AI 티가 나면 실패]
1. 자연스러운 한국어 구어체. 너무 매끄럽거나 정형적이지 않게.
2. 다음 AI 정형 표현 피하기: "또한", "결론적으로", "정리하자면", "마지막으로", "다음과 같이", "특히", "~할 수 있습니다"의 반복.
3. 가끔 사람다운 표현 섞기: "솔직히", "사실", "근데 이게", "어쩌면", "그러니까".
4. 종결어미를 단조롭게 두지 말 것. "~죠", "~거든요", "~잖아요"를 한두 번 자연스럽게.
5. 문장 길이 다양화 — 짧은 문장과 긴 문장을 한 문단 안에 섞으세요.
6. 가끔 결론을 단정하지 않고 여운을 두어도 좋습니다.
7. 한 단락 안에서 시점·뉘앙스가 살짝 변해도 됩니다.

[E-E-A-T — 본문 안에 자연스럽게 녹이기]
- Experience: 구체적 시나리오 한 번 이상.
- Expertise: 구체적 숫자 한두 번 (시간·가격대·주기).
- Authority: 의료·안전 관련 한 줄 짚기.
- Trust: 합법적 정상 영업·선입금 거절 같은 안전 원칙을 자연스럽게 한 번.
따로 섹션 두지 말고 본문 흐름에 녹이세요.

[금지어]
"1등", "최고", "100%", "보장", "완벽", "베스트", "1위", "추천 1순위", "치료된다", "낫는다", "효과가 확실" 사용 금지.

[출력 형식]
오직 JSON만 출력. JSON 앞뒤 어떤 설명·인사·코드블록 마크다운 금지.

{{
  "title": "60자 이내 제목 (클릭 유도되되 과장 없이)",
  "description": "140자 이내 메타 디스크립션",
  "h2_1": "1. 첫 H2 제목 (10~28자)",
  "p_1": "약 500자 본문",
  "h2_2": "2. 두 번째 H2 제목",
  "p_2": "약 500자 본문",
  "h2_3": "3. 세 번째 H2 제목",
  "p_3": "약 500자 본문",
  "h2_4": "4. 네 번째 H2 제목",
  "p_4": "약 500자 본문",
  "h2_5": "5. 다섯 번째 H2 제목",
  "p_5": "약 500자 본문"
}}
"""

NARRATIVE_PROMPT = """당신은 "간다GO" 매거진의 한국인 작성자입니다. 특정 지역의 출장마사지 이용 경험을 사람의 일기·에세이처럼 자연스럽게 풀어내는 글을 씁니다. 광고 톤이 아니라, 그 동네에 살거나 일하는 사람이 자기 경험을 이야기하듯 솔직한 톤이 핵심입니다.

[주제]
{title}

[지역]
{district_name}

[배경 시나리오 — 이 시나리오를 본문 안에 자연스럽게 녹여 주세요]
{scenario}

[검색 의도]
"{intent}"

[지역 디테일 — 본문에 반드시 한두 번 녹일 것]
{region_hint}
그 동네에만 있는 작은 디테일(도로 사정, 주거 형태, 시간대 분위기, 인근 권역과의 비교 등)을 한두 줄이라도 넣어 주세요. 그래야 thin content가 안 됩니다.

[톤 — 특별 강조]
- 1인칭 시점이 자연스러우면 사용 (저는, 제 친구가). 다만 무리해서 1인칭으로 끌고 가지는 마세요.
- 광고·홍보 톤 절대 금지. "이용해 보세요" 같은 권유형보다는 "받아봤더니" 같은 회상·관찰형이 더 어울립니다.
- 단언보다 여운. "이게 답이다"보다 "이 정도가 적당하더라" 식.
- 종결어미 한 패턴으로 통일하지 말 것. 한 글 안에 "~더라고요", "~거든요", "~잖아요", "~죠"를 자연스럽게 섞으세요.

[제목 다양화 — 매우 중요]
주어진 [주제]를 그대로 베끼지 말고, 다음 중 자연스러운 한 가지 방식으로 변형해 주세요:
1) "{지역} 출장마사지, {감정 후크}"
2) "{시나리오} 끝나고 {지역}에서 받은 {시간}"
3) "{지역}에서 처음 마사지를 받았다, 솔직한 후기"
4) "{시간/요일} {지역}, {짧은 묘사}"
5) "{질문형}? {지역}에서 받아본 결과"
"OO동 출장마사지, ~" 패턴이 매번 똑같으면 AI 글로 인식됩니다. 절반 정도는 다른 구조로 시작해 주세요.

""" + COMMON_BLOCK


GUIDE_PROMPT = """당신은 "간다GO" 매거진의 한국인 작성자입니다. 출장마사지·바디케어 관련 정보·건강·라이프스타일 글을 사람이 직접 쓴 것처럼 자연스러운 한국어로 작성합니다.

[주제]
{title}

[검색 의도]
"{intent}"

[지역 맥락]
가능하면 본문에 다음 지역명을 1~2회 자연스럽게 녹이세요 (억지로 끼우지 말고): {region_hint}
지역 힌트가 비어있다면 굳이 지역을 끌어들이지 않아도 됩니다.

""" + COMMON_BLOCK


def call_claude(topic: dict, retry_hint: str = "") -> dict:
    client = Anthropic()
    post_type = topic.get("post_type", "guide")
    if post_type == "narrative":
        prompt = NARRATIVE_PROMPT.format(
            title=topic["title"],
            district_name=topic.get("district_name", ""),
            scenario=topic.get("scenario", ""),
            intent=topic["search_intent"],
            region_hint=topic.get("region_hint", "") or "(없음)",
        )
    else:
        prompt = GUIDE_PROMPT.format(
            title=topic["title"],
            intent=topic["search_intent"],
            region_hint=topic.get("region_hint", "") or "(없음)",
        )
    if retry_hint:
        prompt += f"\n\n[재시도 안내]\n이전 출력에서 다음 문제가 있었습니다. 수정해 주세요:\n{retry_hint}\n"

    msg = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "{"},
        ],
    )
    raw = "{" + "".join(b.text for b in msg.content if b.type == "text")
    # 견고한 JSON 추출
    raw = raw.strip()
    # 가끔 ``` 로 감싸는 경우 정리
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def validate(article: dict) -> str:
    """OK 이면 빈 문자열, 문제면 사유를 리턴."""
    required = ["title", "description", "h2_1", "p_1", "h2_2", "p_2",
                "h2_3", "p_3", "h2_4", "p_4", "h2_5", "p_5"]
    for k in required:
        if k not in article or not article[k].strip():
            return f"필수 키 '{k}' 누락 또는 빈 값"

    # H2 번호 검증
    for i in range(1, 6):
        h = article[f"h2_{i}"].strip()
        if not h.startswith(f"{i}. "):
            return f"h2_{i} 가 '{i}. '로 시작하지 않음: {h[:40]}"

    # 분량 검증
    body = "".join(article[f"p_{i}"] for i in range(1, 6))
    n = len(body)
    if n < 2200 or n > 2800:
        return f"본문 분량 부적합: {n}자 (목표 2400~2600)"

    # 서식 금지 검증 (본문 안에 마크다운/HTML 흔적이 있으면 안 됨)
    for i in range(1, 6):
        p = article[f"p_{i}"]
        if re.search(r"[*_`]{1,}|<[a-zA-Z]+|^[-•·]\s", p, re.MULTILINE):
            return f"p_{i} 안에 서식이 포함됨"

    # 금지어 검증
    full = " ".join([article["title"], article["description"], body])
    for t in BANNED_TERMS:
        if t in full:
            return f"금지어 사용: {t}"

    return ""


def generate(topic: dict) -> dict:
    last_err = ""
    for attempt in range(2):
        article = call_claude(topic, retry_hint=last_err)
        err = validate(article)
        if not err:
            return article
        last_err = err
        print(f"[validate] 시도 {attempt+1} 실패: {err}", file=sys.stderr)
    raise RuntimeError(f"품질 검증 실패: {last_err}")


def build_jsonld(title: str, description: str, post_url: str, iso_date: str,
                 body_chars: int, keywords: list) -> str:
    """Build comprehensive @graph JSON-LD for magazine post."""
    base = DOMAIN
    graph = [
        {
            "@type": "Article",
            "@id": f"{post_url}#article",
            "headline": title,
            "description": description,
            "datePublished": iso_date,
            "dateModified": iso_date,
            "author": {"@id": f"{base}/#org"},
            "publisher": {"@id": f"{base}/#org"},
            "mainEntityOfPage": {"@id": post_url},
            "inLanguage": "ko-KR",
            "wordCount": body_chars,
            "articleSection": "Magazine",
            "keywords": keywords,
            "image": f"{base}/favicon.svg",
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{post_url}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "홈", "item": f"{base}/"},
                {"@type": "ListItem", "position": 2, "name": "매거진", "item": f"{base}/magazine/"},
                {"@type": "ListItem", "position": 3, "name": title, "item": post_url},
            ],
        },
        {
            "@type": "Organization",
            "@id": f"{base}/#org",
            "name": "간다GO",
            "url": f"{base}/",
            "logo": {"@type": "ImageObject", "url": f"{base}/favicon.svg"},
            "sameAs": [
                "https://www.linkedin.com/in/%EB%B0%B1%ED%98%B8-%EA%B0%95-a84273261/",
                "https://medium.com/@88smartbro88",
                "https://x.com/gugeulmake84173",
            ],
        },
        {
            "@type": "WebSite",
            "@id": f"{base}/#website",
            "url": f"{base}/",
            "name": "간다GO",
            "inLanguage": "ko-KR",
            "publisher": {"@id": f"{base}/#org"},
        },
        {
            "@type": "WebPage",
            "@id": post_url,
            "url": post_url,
            "name": title,
            "isPartOf": {"@id": f"{base}/#website"},
            "breadcrumb": {"@id": f"{post_url}#breadcrumb"},
            "primaryImageOfPage": {"@type": "ImageObject", "url": f"{base}/favicon.svg"},
            "inLanguage": "ko-KR",
            "speakable": {
                "@type": "SpeakableSpecification",
                "cssSelector": [".article-content h2", ".article-content p"],
            },
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, indent=2)


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def render_html(topic: dict, article: dict, slug: str, post_url: str) -> str:
    now = datetime.now(KST)
    iso = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    date_korean = now.strftime("%Y년 %m월 %d일")

    sections_html = "\n".join(
        f'  <section class="article-section">\n'
        f'    <h2>{esc(article[f"h2_{i}"])}</h2>\n'
        f'    <p>{esc(article[f"p_{i}"]).replace(chr(10), "</p><p>")}</p>\n'
        f'  </section>'
        for i in range(1, 6)
    )

    related_items = "\n".join(
        f'      <li><a href="{esc(r["href"])}">{esc(r["text"])}</a></li>'
        for r in topic["related_links"]
    )
    related_label = topic.get("related_label", "지역별 이용 정보 기반")

    # Build keywords from topic context
    keywords = ["출장마사지", "간다GO 매거진"]
    if topic.get("district_name"):
        keywords.append(topic["district_name"])
    if topic.get("post_type") == "narrative":
        keywords.append("지역 후기")
    else:
        keywords.append("이용 가이드")

    body_chars = sum(len(article[f"p_{i}"]) for i in range(1, 6))
    jsonld_str = build_jsonld(
        title=article["title"],
        description=article["description"],
        post_url=post_url,
        iso_date=iso,
        body_chars=body_chars,
        keywords=keywords,
    )

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(article["title"])} | 간다GO 매거진</title>
<meta name="description" content="{esc(article["description"])}" />
<meta property="og:title" content="{esc(article["title"])}" />
<meta property="og:description" content="{esc(article["description"])}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="간다GO" />
<meta property="og:url" content="{post_url}" />
<meta name="theme-color" content="#0B5F58" />
<link rel="icon" type="image/svg+xml" href="../../favicon.svg" />
<link rel="apple-touch-icon" href="../../favicon.svg" />
<link rel="canonical" href="{post_url}" />
<link rel="stylesheet" href="../../css/style.css" />
</head>
<body class="magazine-post">

<div class="topbar"><div class="container">
  <a href="../../support/index.html#guide">처음 이용 안내</a>
  <a href="../../support/index.html#safety">안전 가이드</a>
  <a href="../../support/index.html#partner">제휴 문의</a>
</div></div>

<header class="site-header"><div class="container header-inner">
  <a href="../../index.html" class="brand"><span class="logo-mark">간</span><span class="brand-name">간다<span class="accent">GO</span></span></a>
  <nav class="nav">
    <div class="nav-item" data-section="home"><a class="nav-link" href="../../index.html">홈</a></div>
    <div class="nav-item" data-section="region"><a class="nav-link" href="../../region/index.html">지역별 찾기</a></div>
    <div class="nav-item" data-section="services"><a class="nav-link" href="../../services/index.html">서비스</a></div>
    <div class="nav-item" data-section="reviews"><a class="nav-link" href="../../reviews/index.html">이용 후기</a></div>
    <div class="nav-item" data-section="support"><a class="nav-link" href="../../support/index.html">고객지원·안전</a></div>
    <div class="nav-item active" data-section="magazine"><a class="nav-link" href="../index.html">매거진</a></div>
  </nav>
  <a href="../../support/index.html#guide" class="cta-btn">예약 안내</a>
  <button class="menu-toggle" aria-label="메뉴 열기"><span></span><span></span><span></span></button>
</div></header>

<section class="page-header"><div class="container">
  <div class="breadcrumb"><a href="../../index.html">홈</a><span class="sep">/</span><a href="../index.html">매거진</a><span class="sep">/</span><span>{esc(article["title"])}</span></div>
  <h1>{esc(article["title"])}</h1>
  <p class="post-meta">{date_korean} · 간다GO 매거진</p>
</div></section>

<div class="article-wrap"><div class="article-content">
{sections_html}
</div></div>

<div class="container">
  <aside class="related-dark">
    <div class="related-dark__head">
      <h2><span class="pin">📌</span> 함께 보면 좋은 글</h2>
      <span class="sub">({related_label})</span>
    </div>
    <ul class="related-dark__list">
{related_items}
    </ul>
  </aside>
</div>

<footer class="site-footer">
  <div class="footer-trust">
    <div class="container">
      <div class="trust-item">
        <span class="trust-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
        <p><strong>엄격한 신원 확인</strong>을 거친 전문 테라피스트들만 제휴합니다.</p>
      </div>
      <div class="trust-item">
        <span class="trust-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-12V5l-8-3-8 3v5c0 8 8 12 8 12z"/></svg></span>
        <p>간다GO는 <strong>건전한 마사지 문화</strong>를 지향하며, 불법·퇴폐 문의는 정중히 거절합니다.</p>
      </div>
    </div>
  </div>
  <div class="container footer-grid">
    <section class="footer-brand" aria-label="간다GO 소개">
      <a href="../../index.html" class="brand"><span class="logo-mark">간</span><span class="brand-name">간다<span class="accent">GO</span></span></a>
      <p>전국 출장마사지 정보 안내 플랫폼.<br>검증된 정보를 한곳에서.</p>
      <a href="tel:0508-202-4683" class="footer-tel">
        <span class="ft-num">0508-202-4683</span>
        <span class="ft-label">24시 예약·안내</span>
      </a>
    </section>
    <nav class="footer-nav" aria-label="지역 안내">
      <h4>지역 안내</h4>
      <ul>
        <li><a href="../../region/index.html">전체 지역</a></li>
        <li><a href="../../region/seoul/index.html">서울</a></li>
        <li><a href="../../region/gyeonggi/index.html">경기</a></li>
        <li><a href="../../region/incheon/index.html">인천</a></li>
        <li><a href="../../region/busan/index.html">부산</a></li>
      </ul>
    </nav>
    <nav class="footer-nav" aria-label="서비스">
      <h4>서비스</h4>
      <ul>
        <li><a href="../../services/swedish.html">스웨디시</a></li>
        <li><a href="../../services/aroma.html">아로마</a></li>
        <li><a href="../../services/thai.html">타이</a></li>
        <li><a href="../../services/homecare.html">홈케어</a></li>
        <li><a href="../../services/index.html">전체 서비스</a></li>
      </ul>
    </nav>
    <nav class="footer-nav" aria-label="고객지원">
      <h4>고객지원</h4>
      <ul>
        <li><a href="../../support/index.html#guide">이용 안내</a></li>
        <li><a href="../../support/index.html#safety">안전 가이드</a></li>
        <li><a href="../../reviews/index.html">이용 후기</a></li>
        <li><a href="../index.html">매거진</a></li>
        <li><a href="../../support/index.html#partner">제휴 문의</a></li>
      </ul>
    </nav>
  </div>
  <div class="footer-meta">
    <div class="container">
      <dl class="business-info">
        <div><dt>상호</dt><dd>YH 마케터</dd></div>
        <div><dt>대표</dt><dd>강백호</dd></div>
        <div><dt>사업자등록번호</dt><dd>815-26-00585</dd></div>
        <div><dt>주소</dt><dd>서울특별시 강남구 양재대로 478</dd></div>
      </dl>
    </div>
  </div>
  <div class="footer-bottom">
    <div class="container">
      <p>© 2026 간다GO. All rights reserved.</p>
    </div>
  </div>
</footer>
<script src="../../js/main.js"></script>

<script type="application/ld+json">
{jsonld_str}
</script>
</body></html>
'''


# ----- 매거진 인덱스 갱신 -----

INDEX_MARK_START = "<!-- AUTO_POSTS_START -->"
INDEX_MARK_END = "<!-- AUTO_POSTS_END -->"


def list_posts() -> list[dict]:
    posts = []
    if not POSTS_DIR.exists():
        return posts
    for p in sorted(POSTS_DIR.glob("*.html"), reverse=True):
        html = p.read_text(encoding="utf-8")
        title_m = re.search(r"<title>([^<|]+?)\s*\|", html)
        desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
        date_m = re.search(r'<p class="post-meta">([^<]+?)\s*·', html)
        if not title_m:
            continue
        posts.append({
            "slug": p.stem,
            "title": title_m.group(1).strip(),
            "description": desc_m.group(1).strip() if desc_m else "",
            "date": date_m.group(1).strip() if date_m else "",
        })
    return posts


def update_magazine_index() -> None:
    posts = list_posts()
    if not posts:
        return
    featured = posts[0]
    others = posts[1:13]  # up to 12 in grid

    feat_html = f'''<section class="section magazine-featured-section">
  <div class="container">
    <a href="posts/{featured["slug"]}.html" class="featured-post">
      <div class="featured-post__top">
        <span class="featured-eyebrow">📌 Featured</span>
        <span class="card-category">최신 글</span>
      </div>
      <h2>{esc(featured["title"])}</h2>
      <p class="lead">{esc(featured["description"])}</p>
      <div class="featured-meta">
        <span>{esc(featured["date"])}</span>
        <span class="meta-divider">·</span>
        <span class="featured-cta">글 읽으러 가기 →</span>
      </div>
    </a>
  </div>
</section>'''

    if others:
        grid_cards = "\n".join(
            f'      <a href="posts/{p["slug"]}.html" class="post-card">\n'
            f'        <span class="card-category">매거진</span>\n'
            f'        <h3>{esc(p["title"])}</h3>\n'
            f'        <p>{esc(p["description"][:120])}</p>\n'
            f'        <div class="post-card__meta">{esc(p["date"])}<span class="read-arrow">읽기 →</span></div>\n'
            f'      </a>'
            for p in others
        )
        grid_section = f'''
<section class="section">
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Latest</span>
      <h2>최근 매거진 글</h2>
    </div>
    <div class="post-grid">
{grid_cards}
    </div>
  </div>
</section>'''
    else:
        grid_section = ""

    # Coming Soon — show next 6 unused topics from queue
    coming_section = ""
    try:
        queue = load_queue()
        upcoming = [t for t in queue.get("topics", []) if not t.get("used")][:6]
    except Exception:
        upcoming = []
    if upcoming:
        def _cat(t):
            if t.get("post_type") == "narrative":
                return "지역 후기"
            slug = t.get("slug", "")
            if any(k in slug for k in ("swedish", "thai", "aroma", "lomi", "vs", "what-is", "hot-stone")):
                return "코스 안내"
            if any(k in slug for k in ("shoulder", "neck", "back", "calf", "workout", "pain")):
                return "통증·회복"
            if any(k in slug for k in ("overtime", "office", "sleep", "stress", "burnout", "autonomic")):
                return "라이프스타일"
            return "가이드"

        def _desc(t):
            sc = t.get("scenario") or t.get("search_intent") or ""
            if len(sc) > 100:
                sc = sc[:100] + "…"
            return sc

        coming_cards = "\n".join(
            f'      <div class="post-card post-card--coming">\n'
            f'        <span class="card-category">{esc(_cat(t))}</span>\n'
            f'        <h3>{esc(t["title"])}</h3>\n'
            f'        <p>{esc(_desc(t))}</p>\n'
            f'        <div class="post-card__meta">발행 예정</div>\n'
            f'      </div>'
            for t in upcoming
        )
        coming_section = f'''
<section class="section alt magazine-upcoming">
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Coming Soon</span>
      <h2>곧 업데이트될 글</h2>
      <p>매주 월·수·금 오전에 새 글이 올라옵니다.</p>
    </div>
    <div class="post-grid">
{coming_cards}
    </div>
  </div>
</section>'''

    block = f'''{INDEX_MARK_START}
{feat_html}{grid_section}{coming_section}
{INDEX_MARK_END}'''

    html = MAGAZINE_INDEX.read_text(encoding="utf-8")
    if INDEX_MARK_START in html and INDEX_MARK_END in html:
        html = re.sub(
            re.escape(INDEX_MARK_START) + r".*?" + re.escape(INDEX_MARK_END),
            block,
            html,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # 페이지 헤더 직후에 삽입
        html = re.sub(
            r"(</section>\s*\n*\s*<div class=\"container\">)",
            block + r"\n\1",
            html,
            count=1,
        )
    MAGAZINE_INDEX.write_text(html, encoding="utf-8")


# ----- 사이트맵 + RSS 갱신 -----

MAGAZINE_SITEMAP = ROOT / "sitemap-magazine.xml"
MAGAZINE_RSS = ROOT / "magazine" / "rss.xml"

INDEXNOW_KEY = "16e565e44992937c568b7cada0d76106"
INDEXNOW_KEY_LOCATION = f"{DOMAIN}/{INDEXNOW_KEY}.txt"
INDEXNOW_ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
    "https://yandex.com/indexnow",
]


def ping_indexnow(post_url: str) -> None:
    """IndexNow API 핑 - Bing·Yandex 즉시 색인 요청."""
    payload = json.dumps({
        "host": "gandago.me",
        "key": INDEXNOW_KEY,
        "keyLocation": INDEXNOW_KEY_LOCATION,
        "urlList": [post_url, f"{DOMAIN}/magazine/", f"{DOMAIN}/magazine/rss.xml"],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    for ep in INDEXNOW_ENDPOINTS:
        try:
            req = urllib.request.Request(ep, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"[indexnow] {ep} → {resp.status}")
        except urllib.error.HTTPError as e:
            # 200/202 success, 4xx body has detail
            if e.code in (200, 202):
                print(f"[indexnow] {ep} → {e.code}")
            else:
                print(f"[indexnow] {ep} → {e.code} (응답 본문: {e.read()[:120]!r})")
        except Exception as e:
            print(f"[indexnow] {ep} → 에러: {e}")


def ping_search_engines(post_url: str) -> None:
    """검색엔진별 사이트맵 갱신 ping (Google·Bing 레거시 + Naver IndexNow)."""
    # Google·Bing 사이트맵 ping (deprecated 됐지만 안 손해)
    sitemap_url = f"{DOMAIN}/sitemap.xml"
    for ping in [
        f"https://www.google.com/ping?sitemap={sitemap_url}",
        f"https://www.bing.com/ping?sitemap={sitemap_url}",
    ]:
        try:
            with urllib.request.urlopen(ping, timeout=10) as r:
                print(f"[sitemap-ping] {ping[:50]}... → {r.status}")
        except Exception as e:
            print(f"[sitemap-ping] {ping[:50]}... → 에러: {e}")


def update_sitemap(post_url: str) -> None:
    """매거진 sub-sitemap에 새 글 추가."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    target = MAGAZINE_SITEMAP if MAGAZINE_SITEMAP.exists() else SITEMAP
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    if post_url in text:
        return
    entry = (
        f"  <url>\n"
        f"    <loc>{post_url}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>monthly</changefreq>\n"
        f"    <priority>0.7</priority>\n"
        f"  </url>\n"
    )
    text = text.replace("</urlset>", entry + "</urlset>")
    target.write_text(text, encoding="utf-8")
    # Touch sitemap index lastmod
    if SITEMAP.exists():
        idx = SITEMAP.read_text(encoding="utf-8")
        idx = re.sub(
            r'(<loc>[^<]*sitemap-magazine\.xml</loc>\s*<lastmod>)[^<]+(</lastmod>)',
            rf'\g<1>{today}\g<2>',
            idx
        )
        SITEMAP.write_text(idx, encoding="utf-8")


def update_rss() -> None:
    """매거진 RSS 피드 갱신 (전체 글 재생성)."""
    posts = list_posts()  # 이미 정렬됨 (최신 첫번째)
    items_html = []
    for p in posts:
        url = f"{DOMAIN}/magazine/posts/{p['slug']}.html"
        pub_date = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")
        items_html.append(
            f'    <item>\n'
            f'      <title><![CDATA[{p["title"]}]]></title>\n'
            f'      <link>{url}</link>\n'
            f'      <guid isPermaLink="true">{url}</guid>\n'
            f'      <description><![CDATA[{p["description"]}]]></description>\n'
            f'      <pubDate>{pub_date}</pubDate>\n'
            f'    </item>'
        )
    last_build = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '  <channel>\n'
        '    <title>간다GO 매거진</title>\n'
        f'    <link>{DOMAIN}/magazine/</link>\n'
        f'    <atom:link href="{DOMAIN}/magazine/rss.xml" rel="self" type="application/rss+xml"/>\n'
        '    <description>전국 출장마사지 정보와 바디케어·건강·라이프스타일 콘텐츠.</description>\n'
        '    <language>ko-KR</language>\n'
        '    <copyright>© 간다GO. All rights reserved.</copyright>\n'
        f'    <lastBuildDate>{last_build}</lastBuildDate>\n'
        '    <generator>간다GO Magazine Auto-Publisher</generator>\n'
        + "\n".join(items_html) + "\n"
        '  </channel>\n'
        '</rss>\n'
    )
    MAGAZINE_RSS.parent.mkdir(parents=True, exist_ok=True)
    MAGAZINE_RSS.write_text(rss, encoding="utf-8")
    # 루트 미러 (gandago.me/rss.xml 도 작동하게)
    (ROOT / "rss.xml").write_text(rss, encoding="utf-8")


# ----- 메인 -----

def main() -> int:
    queue = load_queue()
    topic = pick_topic(queue)
    if topic is None:
        print("[info] 모든 토픽이 소진되었습니다. topic_queue.json 에 새 토픽을 추가하세요.")
        return 0

    print(f"[info] 토픽 선택: {topic['slug']} - {topic['title']}")
    article = generate(topic)
    print(f"[info] 본문 분량: {sum(len(article[f'p_{i}']) for i in range(1,6))} 자")

    slug = topic["slug"]
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    post_path = POSTS_DIR / f"{slug}.html"
    post_url = f"{DOMAIN}/magazine/posts/{slug}.html"

    html = render_html(topic, article, slug, post_url)
    post_path.write_text(html, encoding="utf-8")
    print(f"[ok] 글 저장: {post_path.relative_to(ROOT)}")

    update_magazine_index()
    print(f"[ok] 매거진 인덱스 갱신")

    update_sitemap(post_url)
    print(f"[ok] 사이트맵 갱신")

    update_rss()
    print(f"[ok] RSS 피드 갱신")

    # IndexNow ping (Bing·Yandex 즉시 색인)
    try:
        ping_indexnow(post_url)
        ping_search_engines(post_url)
    except Exception as e:
        print(f"[warn] 색인 ping 일부 실패: {e}")
    print(f"[ok] 색인 요청 ping 완료")

    topic["used"] = True
    topic["published_at"] = datetime.now(KST).strftime("%Y-%m-%d")
    save_queue(queue)
    print(f"[ok] 토픽 큐 갱신 (used: true)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
