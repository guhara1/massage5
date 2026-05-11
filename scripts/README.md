# 매거진 자동 발행 시스템

월·수·금 오전 9시(KST)에 매거진 글 1편을 자동 발행합니다.

## 한 번만 설정하면 됩니다

### 1. Anthropic API 키 발급

1. https://console.anthropic.com 접속
2. 계정 생성·로그인 후 **Settings → API Keys**
3. **Create Key** 클릭 → 키 복사 (한 번만 보입니다)
4. 결제 수단 등록 (사용량 기반, 글 1편당 약 $0.30~0.50)

### 2. GitHub Secret 등록

1. https://github.com/guhara1/massage5/settings/secrets/actions
2. **New repository secret** 클릭
3. Name: `ANTHROPIC_API_KEY`
4. Value: 위에서 복사한 키
5. **Add secret**

### 3. Actions 활성화 확인

1. https://github.com/guhara1/massage5/actions
2. "I understand my workflows, go ahead and enable them" 클릭 (처음 한 번만)
3. 좌측에 **Auto Magazine Post** 워크플로우 보이면 정상

## 동작 방식

```
월·수·금 오전 9시(KST)
       ↓
topic_queue.json 에서 사용 안 한 토픽 1개 선택
       ↓
Claude Opus 4.7 로 글 생성 (E-E-A-T + 사람 글 톤)
       ↓
품질 가드 통과 (분량/구조/금지어/서식)
       ↓
/magazine/posts/{slug}.html 저장
       ↓
/magazine/index.html 최신 글 섹션 자동 갱신
       ↓
/sitemap.xml 갱신
       ↓
git commit + push → Cloudflare Pages 자동 배포
```

## 수동 발행 (테스트용)

GitHub Actions 페이지에서:
1. **Auto Magazine Post** 워크플로우 클릭
2. 우측 **Run workflow** → **Run workflow**
3. 1~2분 후 새 글이 발행됨

## 토픽 관리

`scripts/topic_queue.json` 에 30개 토픽이 미리 들어 있습니다.

- 토픽 1개 = 글 1편
- 30개 × 주 3회 = **약 10주분**
- 다 쓰면 알림이 뜨고, 새 토픽을 추가하면 됩니다

토픽 1개 양식:
```json
{
  "slug": "url-에-쓰일-슬러그",
  "title": "글 제목 (AI가 자체적으로 다듬을 수 있음)",
  "category": "outcall|type|pain|office|travel|sleep|interview",
  "region_hint": "본문에 자연스럽게 녹일 지역 힌트",
  "search_intent": "이 글을 검색하는 사람의 진짜 의도",
  "related_links": [
    {"text": "함께 보면 좋은 글 제목", "href": "../../region/seoul/index.html"}
  ],
  "used": false
}
```

## 품질 가드

- 분량: 본문 2,200~2,800자 (목표 2,500자)
- 구조: H2 다섯 개, 각 제목 앞에 "1. ", "2. " ... 번호
- 본문: 평문만 (목록·표·굵은체 금지)
- 금지어: "1등", "최고", "100%", "완벽", "치료된다" 등 차단
- 검증 실패 시 1회 재시도, 그래도 실패하면 워크플로우 실패

## 비용 안내

- 1편당 약 $0.30~0.50 (Claude Opus 4.7)
- 주 3회 × 4주 = **월 약 $4~6**

## 문제 발생 시

- Actions 페이지에서 빨간 X 표시가 뜨면 로그 확인
- API 키 만료·잔액 부족·토픽 소진이 흔한 원인
