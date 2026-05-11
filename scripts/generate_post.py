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


PROMPT_TEMPLATE = """당신은 "간다GO" 매거진의 한국인 작성자입니다. 출장마사지·바디케어 관련 정보·건강·라이프스타일 글을 사람이 직접 쓴 것처럼 자연스러운 한국어로 작성합니다.

[주제]
{title}

[검색 의도]
이 글을 검색해서 들어오는 사람은 다음을 알고 싶어 합니다. 그 의도를 충족시키는 방향으로 쓰세요.
"{intent}"

[분량]
한글 기준 본문 합계 2,500자 ± 100자. 너무 짧거나 길지 않게.

[구조]
- 본문은 H2 다섯 개로 구성합니다.
- 각 H2 제목 앞에 번호: "1. ", "2. ", "3. ", "4. ", "5. "
- 각 H2 아래는 오직 평문 문단(들)만. 목록(불릿/번호 리스트), 표, 굵은체, 이탤릭, 인용부호 강조, 코드블록 등 어떤 서식도 절대 사용 금지.
- 각 H2 본문은 약 500자.

[문체 — 이 글이 AI가 쓴 것처럼 읽히면 실패입니다]
1. 자연스러운 한국어 구어체로. 너무 매끄럽거나 정형적이지 않게.
2. 다음 AI 정형 표현을 피하세요: "또한", "결론적으로", "정리하자면", "마지막으로", "다음과 같이", "특히", "~할 수 있습니다"의 반복.
3. 가끔 사람 같은 표현을 섞으세요: "솔직히", "사실", "근데 이게", "어쩌면", "~하는 편이긴 한데", "그러니까".
4. 종결어미를 단조롭게 두지 마세요. "~죠", "~거든요", "~잖아요"를 한두 번 자연스럽게 섞어도 좋습니다.
5. 문장 길이를 다양하게 — 짧은 5어절 문장과 25어절 긴 문장을 한 문단 안에 섞으세요.
6. 가끔 미완결처럼 살짝 흐리거나, 결론을 단정하지 않고 여운을 두어도 좋습니다.
7. 한 단락 안에서 시점·뉘앙스가 살짝 변해도 됩니다. 너무 일관된 결론 지향 문체는 AI처럼 보입니다.
8. 사실 전달보다, 사람이 자기 경험을 나누듯 말하는 흐름이 핵심.

[E-E-A-T 신호 — 본문 안에 자연스럽게 녹이기]
- Experience: 구체적 시나리오 한 번 이상 (예: "야근 끝나고 새벽 한 시에..." 같은 상황 묘사).
- Expertise: 구체적 숫자 한두 번 (시간, 가격대, 주기 같은 것).
- Authority: 의료·안전 관련 한 줄 짚기 (예: 최근 수술·임신 시에는 사전 안내).
- Trust: 합법적 정상 영업·선입금 거절 같은 안전 원칙을 자연스럽게 한 번.
이 모든 신호는 따로 섹션을 두지 말고, 본문 흐름 안에 녹여 주세요.

[금지어]
"1등", "최고", "100%", "보장", "완벽", "베스트", "1위", "추천 1순위", "치료된다", "낫는다", "효과가 확실" 같은 단정·과장·의학적 단정 표현은 절대 사용 금지.

[지역 맥락]
가능하면 본문에 다음 지역명을 1~2회 자연스럽게 녹이세요 (억지로 끼우지 말고, 시나리오·예시 안에 자연스럽게): {region_hint}
지역 힌트가 비어있다면 굳이 지역을 끌어들이지 않아도 됩니다.

[출력 형식]
오직 JSON만 출력하세요. JSON 앞뒤로 어떤 설명·인사·코드블록 표시도 붙이지 마세요. 정확히 아래 키들로 구성하세요.

{{
  "title": "60자 이내 매력적 제목 (클릭 유도되되 과장 없이)",
  "description": "140자 이내 메타 디스크립션",
  "h2_1": "1. 첫 H2 제목 (10~25자)",
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


def call_claude(topic: dict, retry_hint: str = "") -> dict:
    client = Anthropic()
    prompt = PROMPT_TEMPLATE.format(
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

    related_cards = "\n".join(
        f'      <a href="{esc(r["href"])}" class="card">\n'
        f'        <h3>{esc(r["text"])}</h3>\n'
        f'      </a>'
        for r in topic["related_links"]
    )

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article["title"],
        "description": article["description"],
        "datePublished": iso,
        "dateModified": iso,
        "author": {"@type": "Organization", "name": "간다GO"},
        "publisher": {
            "@type": "Organization",
            "name": "간다GO",
            "logo": {"@type": "ImageObject", "url": f"{DOMAIN}/favicon.svg"},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": post_url},
    }

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
<body>

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

<section class="section alt">
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Related</span>
      <h2>함께 보면 좋은 글</h2>
      <p>이 글과 함께 보면 도움 될 페이지를 골라뒀습니다.</p>
    </div>
    <div class="grid cols-3">
{related_cards}
    </div>
  </div>
</section>

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
{json.dumps(jsonld, ensure_ascii=False, indent=2)}
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
    cards = "\n".join(
        f'      <a href="posts/{p["slug"]}.html" class="card">\n'
        f'        <span class="card-date">{esc(p["date"])}</span>\n'
        f'        <h3>{esc(p["title"])}</h3>\n'
        f'        <p>{esc(p["description"][:80])}</p>\n'
        f'      </a>'
        for p in posts[:12]
    )
    block = f'''{INDEX_MARK_START}
<section class="section" id="latest">
  <div class="container">
    <div class="section-head">
      <span class="eyebrow">Latest</span>
      <h2>최근 매거진 글</h2>
      <p>새로 올라온 글을 가장 먼저 만나보세요.</p>
    </div>
    <div class="grid cols-3">
{cards}
    </div>
  </div>
</section>
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


# ----- 사이트맵 갱신 -----

def update_sitemap(post_url: str) -> None:
    if not SITEMAP.exists():
        return
    text = SITEMAP.read_text(encoding="utf-8")
    if post_url in text:
        return  # 이미 있음
    today = datetime.now(KST).strftime("%Y-%m-%d")
    entry = (
        f"  <url>\n"
        f"    <loc>{post_url}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>monthly</changefreq>\n"
        f"    <priority>0.7</priority>\n"
        f"  </url>\n"
    )
    text = text.replace("</urlset>", entry + "</urlset>")
    SITEMAP.write_text(text, encoding="utf-8")


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

    topic["used"] = True
    topic["published_at"] = datetime.now(KST).strftime("%Y-%m-%d")
    save_queue(queue)
    print(f"[ok] 토픽 큐 갱신 (used: true)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
