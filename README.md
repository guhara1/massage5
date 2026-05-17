# 간다GO

전국 출장마사지 정보 플랫폼.

## 구조

```
.
├─ index.html              # 메인 페이지
├─ css/style.css           # 공통 스타일
├─ js/main.js              # 모바일 메뉴 / 활성 메뉴 표시
├─ region/                 # 지역별 찾기
│  ├─ index.html
│  ├─ seoul.html
│  ├─ gyeonggi.html
│  ├─ incheon.html
│  └─ other.html
├─ services/               # 서비스 종류별
│  ├─ index.html
│  ├─ thai.html
│  ├─ aroma.html
│  ├─ swedish.html
│  ├─ lomi.html
│  ├─ homecare.html
│  ├─ women.html
│  └─ couple.html
├─ reviews/index.html      # 이용 후기
├─ support/index.html      # 고객지원 · 안전 · FAQ · 제휴
└─ magazine/index.html     # 매거진
```

## 미리보기

순수 정적 HTML/CSS/JS이므로 별도 빌드 없이 바로 열 수 있습니다.

```bash
# 간단한 로컬 서버
python3 -m http.server 8080
# 또는
npx serve .
```

브라우저에서 `http://localhost:8080` 열기.

## GitHub Pages 배포

저장소의 Settings → Pages → Source = `Deploy from a branch`, Branch = `main` (또는
원하는 브랜치) → `/ (root)` 선택 후 저장하면 됩니다.

## OG 이미지

- 기본 OG 이미지는 `/assets/og-default.svg` (1200×630)에 들어 있습니다.
- 일부 SNS·크롤러는 SVG OG 이미지를 인식하지 못하므로, 동일 경로에 PNG/JPG
  버전을 추가 배포하면 호환성이 가장 좋습니다 (예: `og-default.png`).
- PNG 추가 후에는 페이지의 `<meta property="og:image">`와 JSON-LD의 `image`
  필드를 `og-default.png`로 일괄 교체할 수 있습니다 (참고: `scripts/update_og_image.py`).
