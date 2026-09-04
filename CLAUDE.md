# 청호렌탈 — 프로젝트 안내

청호나이스 공식 판매점(나이스엔지니어링)의 렌탈 견적·상담 사이트이자, 검색 유입을 만들기 위한 블로그 운영 저장소입니다.
GitHub Pages로 서비스됩니다: `https://pg5chb7mn6-blip.github.io/chungho-rental/`

## 이 저장소에서 일할 때 먼저 읽을 것

- `ops/README.md` — 운영 체계 전체
- `ops/진단-유입부진-원인.md` — 왜 유입이 없는지 (2026-09-04 기준 진단)
- `ops/체크리스트-초기세팅.md` — 검색엔진 등록 등 선행 조건

## 매일 발행

`/daily-blog` 스킬을 사용합니다. `keyword-scout` → `blog-writer` → `lead-closer` → `seo-auditor` 순서로 진행합니다.

## 구조

```
index.html              견적 계산기 (data.js 기반, 자바스크립트로 렌더링)
data.js                 제품·요금 데이터 (매월 프로모션 반영 필요)
<제품군>/index.html      정적 랜딩 12종 (네이버 로봇은 JS를 실행하지 않아 별도 필요)
blog/                   ⚠ 생성물. 직접 고치지 말 것 — ops/posts/*.md 를 고치고 빌드
sitemap.xml, rss.xml    ⚠ 생성물. tools/build_blog.py 가 갱신
ops/                    운영 문서·원고·설정
tools/                  빌드·검수 스크립트
```

## 규칙

- `blog/`, `sitemap.xml`, `rss.xml` 은 **생성물**입니다. 직접 수정하지 말고 `ops/posts/*.md` 를 고친 뒤 `python3 tools/build_blog.py` 를 실행합니다.
- 사업자 정보·인증코드는 `ops/site.config.json` 한 곳에서만 관리하고 `python3 tools/apply_config.py` 로 반영합니다. HTML의 `{{...}}` 를 손으로 고치지 마십시오.
- 페이지를 새로 만들면 `tools/build_blog.py` 의 `STATIC_URLS` 와 `FNAV` 에 추가합니다.
- 원고에 **확정 렌탈료·위약금 액수·필터 교체 주기를 단정해 쓰지 않습니다.** "제품과 조건에 따라 다릅니다"로 처리합니다.
- 본사 공식몰이 아니라 **공식 판매점(대리점)** 입니다. 오인될 표현을 쓰지 않습니다.

## 작업 브랜치

`claude/cheonho-rental-seo-blog-3faixj`
