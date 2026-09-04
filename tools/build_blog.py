#!/usr/bin/env python3
"""ops/posts/*.md 원고를 네이버·구글이 읽는 정적 HTML 블로그로 변환한다.

  python3 tools/build_blog.py

하는 일
  1. ops/posts/*.md  ->  blog/<slug>/index.html   (Article + FAQPage + BreadcrumbList 구조화 데이터 포함)
  2. blog/index.html (카테고리별 목록 허브) 생성
  3. sitemap.xml / rss.xml 에 블로그 URL 반영 (기존 고정 URL은 유지)

왜 필요한가
  네이버 검색로봇(Yeti)은 자바스크립트를 실행하지 않는다. 그리고 네이버 블로그에만 글을 쓰면
  구글·다음·빙에는 사실상 아무 자산도 쌓이지 않는다. 같은 주제를 자사 사이트에도 '다르게 쓴'
  정적 HTML로 남겨야 두 검색엔진 모두에서 유입이 생긴다.
"""
import html as ihtml
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "ops", "posts")
BLOG_DIR = os.path.join(ROOT, "blog")
CONFIG = os.path.join(ROOT, "ops", "site.config.json")
KST = timezone(timedelta(hours=9))

CATEGORIES = {
    "비용": "렌탈료·비용 비교",
    "제품": "제품 선택 가이드",
    "계약": "계약·위약금·해지",
    "관리": "필터·설치·관리",
    "사무실": "사무실·매장·창업",
    "지역": "지역별 설치 안내",
}


# ────────────────────────────── 원고 읽기 ──────────────────────────────

def parse_front_matter(raw, path):
    if not raw.startswith("---"):
        raise SystemExit(f"[오류] {path}: 파일 첫 줄이 '---' 로 시작하는 머리말이어야 합니다.")
    _, fm, body = raw.split("---", 2)
    meta = {}
    key = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - "):          # 리스트 항목
            meta.setdefault(key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        meta[key] = val if val else []
    return meta, body.strip()


def load_posts():
    posts = []
    if not os.path.isdir(POSTS_DIR):
        return posts
    for fn in sorted(os.listdir(POSTS_DIR)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        path = os.path.join(POSTS_DIR, fn)
        with open(path, encoding="utf-8") as f:
            meta, body = parse_front_matter(f.read(), path)
        if str(meta.get("draft", "")).lower() in ("true", "yes", "y"):
            continue
        for required in ("title", "description", "slug", "date", "category"):
            if not meta.get(required):
                raise SystemExit(f"[오류] {fn}: 머리말에 '{required}' 가 없습니다.")
        if meta["category"] not in CATEGORIES:
            raise SystemExit(
                f"[오류] {fn}: category '{meta['category']}' 는 정의되어 있지 않습니다. "
                f"가능한 값: {', '.join(CATEGORIES)}")
        meta["_file"] = fn
        meta["body"] = body
        meta.setdefault("updated", meta["date"])
        posts.append(meta)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


# ────────────────────────────── 마크다운(부분집합) ──────────────────────────────

def inline(text):
    text = ihtml.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{ihtml.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def render_body(body, cta_html):
    """지원 문법: ## / ### 제목, 문단, - 목록, 1. 목록, | 표 |, > 안내박스,
    [[CTA]] 상담 유도 블록, '## 자주 묻는 질문' 아래의 Q./A. 쌍."""
    out, faqs = [], []
    lines = body.splitlines()
    i, n = 0, len(lines)
    in_faq = False

    def flush(buf):
        if buf:
            out.append("<p>" + inline(" ".join(buf)) + "</p>")
        return []

    buf = []
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            buf = flush(buf)
            i += 1
            continue

        if stripped == "[[CTA]]":
            buf = flush(buf)
            out.append(cta_html)
            i += 1
            continue

        if stripped.startswith("### "):
            buf = flush(buf)
            out.append("<h3>" + inline(stripped[4:]) + "</h3>")
            i += 1
            continue

        if stripped.startswith("## "):
            buf = flush(buf)
            title = stripped[3:].strip()
            if in_faq:                      # 앞 절이 FAQ였다면 아코디언 컨테이너를 닫는다
                out.append("</div>")
            in_faq = "자주 묻는 질문" in title
            out.append("<h2>" + inline(title) + "</h2>")
            if in_faq:
                out.append("<div class=\"faq\">")
            i += 1
            continue

        if in_faq and stripped.startswith("Q."):
            q = stripped[2:].strip()
            a_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("Q.") and not lines[i].strip().startswith("## "):
                if lines[i].strip().startswith("A."):
                    a_lines.append(lines[i].strip()[2:].strip())
                elif lines[i].strip():
                    a_lines.append(lines[i].strip())
                i += 1
            a = " ".join(a_lines).strip()
            faqs.append((q, a))
            out.append(f"<details><summary>{inline(q)}</summary><p>{inline(a)}</p></details>")
            continue

        if stripped.startswith("> "):
            buf = flush(buf)
            note = []
            while i < n and lines[i].strip().startswith("> "):
                note.append(lines[i].strip()[2:])
                i += 1
            out.append('<div class="note"><p>' + inline(" ".join(note)) + "</p></div>")
            continue

        if stripped.startswith("|"):
            buf = flush(buf)
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                head, *rest = rows
                thead = "".join(f"<th>{inline(c)}</th>" for c in head)
                tbody = "".join(
                    "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rest)
                out.append(f'<div class="tw"><table><thead><tr>{thead}</tr></thead>'
                           f"<tbody>{tbody}</tbody></table></div>")
            continue

        if re.match(r"^[-*] ", stripped) or re.match(r"^\d+\. ", stripped):
            buf = flush(buf)
            ordered = bool(re.match(r"^\d+\. ", stripped))
            items = []
            while i < n:
                s = lines[i].strip()
                if re.match(r"^[-*] ", s):
                    items.append(s[2:])
                elif re.match(r"^\d+\. ", s):
                    items.append(re.sub(r"^\d+\.\s*", "", s))
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        buf.append(stripped)
        i += 1

    flush(buf)
    if in_faq:
        out.append("</div>")
    return "\n".join(out), faqs


# ────────────────────────────── 템플릿 ──────────────────────────────

CSS = """
:root{--ink:#152030;--ink2:#39485C;--sub:#69798C;--blue:#1E63D0;--blue-d:#164FA8;
--blue-lt:#EAF1FD;--blue-tint:#F4F8FE;--ivory:#FDFCFB;--card:#FFF;--line:#E4EBF3;--line2:#EFF3F8;
--amber:#96540A;--amber-bg:#FDEFD8;--max:760px}
*{box-sizing:border-box;margin:0;padding:0}
html{background:#FDFCFB;scroll-behavior:smooth}
body{font-family:'Pretendard Variable',Pretendard,-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
color:var(--ink);font-size:16px;line-height:1.72;word-break:keep-all;-webkit-font-smoothing:antialiased;
background-image:linear-gradient(168deg,#FDFCFB 0%,#F4F8FC 44%,#E7F0F9 100%);background-attachment:fixed}
a{color:inherit;text-decoration:none}
.wrap{max-width:var(--max);margin:0 auto;padding:0 22px}
.topbar{position:sticky;top:0;z-index:70;background:rgba(253,252,251,.85);
backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);
border-bottom:1px solid rgba(228,235,243,.8)}
.topbar .wrap{max-width:1180px;display:flex;align-items:center;gap:12px;height:58px}
.logo{display:flex;align-items:center;gap:9px}
.logo .mark{width:24px;height:24px;border-radius:8px;position:relative;
background:linear-gradient(150deg,var(--blue),#4A90E8)}
.logo .mark::after{content:"";position:absolute;left:5px;right:5px;bottom:5px;height:7px;
border-radius:4px;background:rgba(255,255,255,.9)}
.logo b{font-size:16px;font-weight:800;letter-spacing:-.04em}
.logo span{font-size:11.5px;color:var(--sub)}
.tcta{margin-left:auto;font-size:13.5px;font-weight:700;color:#fff;background:var(--blue);
padding:9px 15px;border-radius:10px}
article{padding:30px 0 56px}
.crumb{font-size:13px;color:var(--sub);margin-bottom:14px}
.crumb a{color:var(--blue);font-weight:600}
.cat{display:inline-block;font-size:12px;font-weight:700;color:var(--blue);background:var(--blue-lt);
padding:5px 12px;border-radius:999px;margin-bottom:12px}
h1{font-size:29px;font-weight:800;letter-spacing:-.035em;line-height:1.34;margin-bottom:12px}
.dateline{font-size:13px;color:var(--sub);border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}
.lead{font-size:17px;color:var(--ink2);background:var(--blue-tint);border:1px solid var(--line);
border-radius:14px;padding:18px 20px;margin-bottom:28px}
article h2{font-size:21px;font-weight:800;letter-spacing:-.03em;margin:34px 0 12px;padding-top:8px}
article h3{font-size:17.5px;font-weight:700;margin:22px 0 8px;color:var(--ink2)}
article p{margin-bottom:14px;color:var(--ink2)}
article ul,article ol{margin:0 0 16px 20px}
article li{margin-bottom:7px;color:var(--ink2)}
article strong{color:var(--ink);font-weight:700}
article a[href]{color:var(--blue);font-weight:600;text-decoration:underline;text-underline-offset:3px}
.note{background:var(--amber-bg);border-radius:12px;padding:15px 18px;margin:18px 0}
.note p{margin:0;color:var(--amber);font-size:14.5px;font-weight:600}
.tw{overflow-x:auto;margin:18px 0;border:1px solid var(--line);border-radius:12px;background:#fff}
table{width:100%;border-collapse:collapse;font-size:14.5px;min-width:420px}
th,td{padding:11px 13px;text-align:left;border-bottom:1px solid var(--line2)}
th{background:var(--blue-tint);font-weight:700;font-size:13.5px;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.faq details{border:1px solid var(--line);border-radius:12px;background:#fff;padding:14px 16px;margin-bottom:9px}
.faq summary{font-weight:700;cursor:pointer;font-size:15px}
.faq details p{margin:10px 0 0;font-size:14.5px}
.cta{background:linear-gradient(150deg,#12386F,#1E63D0);border-radius:18px;padding:26px 24px;margin:32px 0;color:#fff}
.cta h2{margin:0 0 8px;font-size:19px;color:#fff}
.cta p{color:rgba(255,255,255,.9);font-size:14.5px;margin-bottom:16px}
.cta .row{display:flex;gap:9px;flex-wrap:wrap}
.cta a{display:inline-block;padding:12px 20px;border-radius:11px;font-weight:700;font-size:14.5px}
.cta a.p{background:#fff;color:var(--blue-d)}
.cta a.k{background:#FEE500;color:#191600}
.rel{border-top:1px solid var(--line);margin-top:36px;padding-top:22px}
.rel h2{font-size:17px;margin:0 0 12px}
.rel ul{margin-left:18px}
.rel a{color:var(--blue);font-weight:600}
.pager{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}
.pager a{flex:1 1 220px;border:1px solid var(--line);background:#fff;border-radius:12px;padding:13px 15px}
.pager span{display:block;font-size:11.5px;color:var(--sub);font-weight:700;margin-bottom:3px}
.pager b{font-size:14.5px;font-weight:700;letter-spacing:-.02em}
.hero{padding:38px 0 18px}
.hero h1{font-size:31px}
.hero p{color:var(--ink2);font-size:16px;margin-top:10px}
.catnav{display:flex;gap:7px;flex-wrap:wrap;margin:22px 0 8px}
.catnav a{font-size:13.5px;font-weight:700;padding:8px 14px;border-radius:999px;
border:1px solid var(--line);background:#fff;color:var(--ink2)}
.list{display:grid;gap:11px;padding-bottom:50px}
.item{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.item .cat{margin-bottom:8px}
.item h2{font-size:17.5px;font-weight:700;letter-spacing:-.03em;margin:0 0 6px;line-height:1.44}
.item p{font-size:14.5px;color:var(--sub);margin:0}
.item time{display:block;font-size:12.5px;color:var(--sub);margin-top:9px}
.sect{font-size:15px;font-weight:800;color:var(--sub);margin:26px 0 10px;letter-spacing:-.02em}
footer{background:#101A28;color:#9FB0C4;padding:34px 0;font-size:12.5px;line-height:1.75}
footer .wrap{max-width:1180px}
.fnav{display:flex;flex-wrap:wrap;gap:8px 16px;margin-bottom:18px}
.fnav a{color:#C6D3E2;font-weight:600;font-size:13px}
footer b{display:block;color:#fff;font-size:14px;margin-bottom:7px}
.biz,.disc{color:#8296AC}
.disc{margin-top:14px;font-size:11.5px;line-height:1.7}
@media(max-width:620px){h1,.hero h1{font-size:24px}article h2{font-size:19px}body{font-size:15.5px}}
"""

FOOTER_TMPL = """<footer><div class="wrap">
  <div class="fnav">{fnav}</div>
  <b>청호나이스 공식 판매점</b>
  <div class="biz">
    상호 나이스엔지니어링 &middot; 대표자 {{{{대표자명}}}} &middot; 사업자등록번호 {{{{사업자등록번호}}}}<br>
    통신판매업신고번호 {{{{통신판매업신고번호}}}} &middot; 주소 {{{{사업장 주소}}}}<br>
    전화 {{{{대표전화}}}} &middot; 이메일 {{{{사내 이메일}}}} &middot;
    <a href="{kakao}" target="_blank" rel="noopener nofollow">카카오톡 오픈채팅 상담</a><br>
    개인정보 보호책임자 {{{{대표자명}}}} ({{{{사내 이메일}}}})
  </div>
  <div class="disc">본 사이트는 청호나이스 공식 판매점(대리점)이 운영하는 상담·견적 안내 사이트이며, 청호나이스 본사가 직접 운영하는 공식몰은 아닙니다. 게재된 월 렌탈료는 부가세 포함 금액이며 제품·조건·프로모션 시기에 따라 달라질 수 있습니다. 렌탈 계약에는 의무사용기간이 있으며, 의무사용기간 내 중도해지 시 계약서에 정한 기준에 따라 위약금이 발생할 수 있습니다. 본 페이지는 계약서가 아니며 최종 금액과 조건은 상담 시 확정됩니다.<br>
    Copyright &copy; 나이스엔지니어링. All rights reserved.</div>
</div></footer>"""

FNAV = [
    ("", "렌탈료 견적 계산"), ("blog/", "블로그"), ("jeongsugi-rental/", "정수기 렌탈"),
    ("eoreum-jeongsugi/", "얼음정수기"), ("gonggi-cheongjeonggi/", "공기청정기"),
    ("bidet/", "비데"), ("yeonsugi/", "연수기"), ("jeseupgi/", "제습기"),
    ("office/", "사무실·매장"), ("guide-rental-vs-purchase/", "렌탈 vs 구매"),
    ("guide-wiyakgeum/", "의무기간·위약금"), ("guide-ijeon-seolchi/", "이전설치"),
    ("guide-filter/", "필터 교체 주기"), ("guide-onerum/", "원룸·1인가구"),
    ("company/", "사업자 정보"), ("privacy/", "개인정보처리방침"),
]


def head(origin, title, desc, url, keywords, extra_meta="", ld=""):
    kw = f'<meta name="keywords" content="{ihtml.escape(keywords, quote=True)}">' if keywords else ""
    t = ihtml.escape(title, quote=True)
    d = ihtml.escape(desc, quote=True)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{t}</title>
<meta name="description" content="{d}">
{kw}
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="author" content="청호나이스 렌탈">
<meta property="og:type" content="article">
<meta property="og:site_name" content="청호나이스 렌탈 견적">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{origin}/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{origin}/og.png">
<meta name="naver-site-verification" content="{{{{네이버_서치어드바이저_인증코드}}}}">
<meta name="google-site-verification" content="{{{{구글_서치콘솔_인증코드}}}}">
<meta name="theme-color" content="#FDFCFB">
<link rel="alternate" type="application/rss+xml" title="청호나이스 렌탈 안내" href="{origin}/rss.xml">
{extra_meta}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
{ld}
</head>
<body>
<div class="topbar"><div class="wrap">
  <a class="logo" href="{origin}/"><span class="mark"></span>
    <b>청호나이스 렌탈</b><span>청호나이스 공식 판매점</span></a>
  <a class="tcta" href="{origin}/#quote">1분 견적 확인</a>
</div></div>
"""


def cta_block(origin, kakao, preset=""):
    href = f"{origin}/{preset}#quote" if preset else f"{origin}/#quote"
    return f"""<div class="cta">
  <h2>내 조건으로 월 렌탈료 바로 확인</h2>
  <p>제품군·의무사용기간·관리방식만 고르면 부가세 포함 월 렌탈료와 총액이 바로 계산됩니다. 계산 결과를 그대로 담아 상담 신청까지 이어집니다.</p>
  <div class="row">
    <a class="p" href="{href}">견적 계산기 열기</a>
    <a class="k" href="{kakao}" target="_blank" rel="noopener nofollow">카카오톡으로 문의</a>
  </div>
</div>"""


def footer(origin, kakao):
    fnav = "".join(f'<a href="{origin}/{p}">{n}</a>' for p, n in FNAV)
    return FOOTER_TMPL.format(fnav=fnav, kakao=kakao)


# ────────────────────────────── 페이지 생성 ──────────────────────────────

def build_post(post, origin, kakao, prev_post, next_post, all_posts):
    url = f"{origin}/blog/{post['slug']}/"
    body_html, faqs = render_body(post["body"], cta_block(origin, kakao, post.get("preset", "")))
    if "[[CTA]]" not in post["body"]:
        body_html += "\n" + cta_block(origin, kakao, post.get("preset", ""))

    keywords = post.get("keywords") or []
    kw_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

    graph = [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": f"{origin}/"},
            {"@type": "ListItem", "position": 2, "name": "블로그", "item": f"{origin}/blog/"},
            {"@type": "ListItem", "position": 3, "name": post["title"]},
        ]},
        {"@type": "BlogPosting", "@id": url + "#article", "headline": post["title"],
         "description": post["description"], "url": url, "inLanguage": "ko-KR",
         "datePublished": post["date"], "dateModified": post["updated"],
         "mainEntityOfPage": url, "image": f"{origin}/og.png",
         "articleSection": CATEGORIES[post["category"]],
         "keywords": kw_str,
         "author": {"@type": "Organization", "name": "청호나이스 공식 판매점"},
         "publisher": {"@type": "Organization", "name": "청호나이스 공식 판매점",
                       "url": f"{origin}/"}},
    ]
    if faqs:
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]})
    ld = '<script type="application/ld+json">' + json.dumps(
        {"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False) + "</script>"

    rel_links = post.get("related") or []
    if isinstance(rel_links, str):
        rel_links = [rel_links]
    rel_html = ""
    if rel_links:
        items = []
        for r in rel_links:
            path, _, label = r.partition("|")
            items.append(f'<li><a href="{origin}/{path.strip()}">{ihtml.escape(label.strip() or path.strip())}</a></li>')
        rel_html = f'<div class="rel"><h2>함께 보면 좋은 안내</h2><ul>{"".join(items)}</ul></div>'

    pager = []
    if next_post:
        pager.append(f'<a href="{origin}/blog/{next_post["slug"]}/"><span>다음 글</span>'
                     f'<b>{ihtml.escape(next_post["title"])}</b></a>')
    if prev_post:
        pager.append(f'<a href="{origin}/blog/{prev_post["slug"]}/"><span>이전 글</span>'
                     f'<b>{ihtml.escape(prev_post["title"])}</b></a>')
    pager_html = f'<div class="pager">{"".join(pager)}</div>' if pager else ""

    updated_note = ""
    if post["updated"] != post["date"]:
        updated_note = f" · {post['updated']} 업데이트"

    html = head(origin, post["title"], post["description"], url, kw_str, ld=ld)
    html += f"""<article><div class="wrap">
<nav class="crumb"><a href="{origin}/">홈</a> › <a href="{origin}/blog/">블로그</a> › <span>{ihtml.escape(CATEGORIES[post['category']])}</span></nav>
<span class="cat">{ihtml.escape(CATEGORIES[post['category']])}</span>
<h1>{ihtml.escape(post['title'])}</h1>
<div class="dateline"><time datetime="{post['date']}">{post['date']}</time>{updated_note} · 청호나이스 공식 판매점</div>
{'<p class="lead">' + inline(post['lead']) + '</p>' if post.get('lead') else ''}
{body_html}
{rel_html}
{pager_html}
</div></article>
"""
    html += footer(origin, kakao) + "\n</body></html>\n"

    out_dir = os.path.join(BLOG_DIR, post["slug"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return url


def build_index(posts, origin, kakao):
    url = f"{origin}/blog/"
    desc = ("청호나이스 정수기·얼음정수기·공기청정기 렌탈료, 의무사용기간과 위약금, 필터 관리, "
            "사무실 설치까지 계약 전에 확인해야 할 내용을 실제 상담 사례 기준으로 정리한 안내 글 모음입니다.")
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Blog", "@id": url + "#blog", "url": url,
             "name": "청호나이스 렌탈 안내 블로그", "description": desc, "inLanguage": "ko-KR",
             "publisher": {"@type": "Organization", "name": "청호나이스 공식 판매점", "url": f"{origin}/"}},
            {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": p["title"],
                 "url": f"{origin}/blog/{p['slug']}/"} for i, p in enumerate(posts[:50])]},
        ]}, ensure_ascii=False) + "</script>"

    html = head(origin, "청호나이스 렌탈 안내 블로그 | 렌탈료·계약·관리 실전 가이드",
                desc, url, "청호나이스 렌탈 블로그, 정수기 렌탈 정보, 렌탈료 비교, 정수기 위약금", ld=ld)
    html = html.replace('<meta property="og:type" content="article">',
                        '<meta property="og:type" content="website">')
    html += f"""<div class="wrap hero">
<h1>렌탈 계약 전에 알아두면 좋은 것들</h1>
<p>월 렌탈료가 왜 사람마다 다른지, 의무사용기간 안에 이사를 가면 어떻게 되는지, 사무실은 무엇이 다른지. 상담하면서 실제로 가장 많이 받은 질문부터 하나씩 정리하고 있습니다.</p>
<div class="catnav">{''.join(f'<a href="#c-{k}">{v}</a>' for k, v in CATEGORIES.items() if any(p['category'] == k for p in posts))}</div>
</div>
<div class="wrap">
"""
    if not posts:
        html += '<p style="padding:30px 0;color:#69798C">첫 글을 준비하고 있습니다.</p>'
    else:
        html += '<div class="sect">최근 글</div><div class="list">'
        for p in posts[:8]:
            html += (f'<a class="item" href="{origin}/blog/{p["slug"]}/">'
                     f'<span class="cat">{ihtml.escape(CATEGORIES[p["category"]])}</span>'
                     f'<h2>{ihtml.escape(p["title"])}</h2>'
                     f'<p>{ihtml.escape(p["description"][:110])}</p>'
                     f'<time datetime="{p["date"]}">{p["date"]}</time></a>')
        html += "</div>"
        for key, label in CATEGORIES.items():
            group = [p for p in posts if p["category"] == key]
            if not group:
                continue
            html += f'<div class="sect" id="c-{key}">{ihtml.escape(label)}</div><div class="list">'
            for p in group:
                html += (f'<a class="item" href="{origin}/blog/{p["slug"]}/">'
                         f'<h2>{ihtml.escape(p["title"])}</h2>'
                         f'<p>{ihtml.escape(p["description"][:110])}</p>'
                         f'<time datetime="{p["date"]}">{p["date"]}</time></a>')
            html += "</div>"
    html += cta_block(origin, kakao) + "</div>\n" + footer(origin, kakao) + "\n</body></html>\n"

    os.makedirs(BLOG_DIR, exist_ok=True)
    with open(os.path.join(BLOG_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return url


# ────────────────────────────── 사이트맵 / RSS ──────────────────────────────

STATIC_URLS = [
    ("", "1.0", "weekly"), ("blog/", "0.9", "daily"),
    ("jeongsugi-rental/", "0.9", "weekly"), ("eoreum-jeongsugi/", "0.9", "weekly"),
    ("gonggi-cheongjeonggi/", "0.9", "weekly"), ("bidet/", "0.9", "weekly"),
    ("yeonsugi/", "0.9", "weekly"), ("jeseupgi/", "0.9", "weekly"),
    ("office/", "0.9", "weekly"), ("guide-rental-vs-purchase/", "0.8", "monthly"),
    ("guide-wiyakgeum/", "0.8", "monthly"), ("guide-ijeon-seolchi/", "0.8", "monthly"),
    ("guide-filter/", "0.8", "monthly"), ("guide-onerum/", "0.8", "monthly"),
    ("company/", "0.4", "yearly"), ("privacy/", "0.3", "yearly"),
]


def build_sitemap(posts, origin):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    newest = posts[0]["updated"] if posts else today
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, pri, freq in STATIC_URLS:
        mod = newest if path in ("", "blog/") else today
        lines.append(f"<url><loc>{origin}/{path}</loc><lastmod>{mod}</lastmod>"
                     f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    for p in posts:
        lines.append(f"<url><loc>{origin}/blog/{p['slug']}/</loc><lastmod>{p['updated']}</lastmod>"
                     f"<changefreq>monthly</changefreq><priority>0.7</priority></url>")
    lines.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def rfc822(datestr):
    d = datetime.strptime(datestr, "%Y-%m-%d").replace(tzinfo=KST)
    return d.strftime("%a, %d %b %Y 09:00:00 +0900")


def build_rss(posts, origin):
    """네이버 서치어드바이저 RSS 제출용. 새 글이 나올 때마다 네이버가 먼저 수집하게 만드는 통로."""
    now = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")
    items = []
    for p in posts[:30]:
        link = f"{origin}/blog/{p['slug']}/"
        items.append(
            "<item>"
            f"<title>{ihtml.escape(p['title'])}</title>"
            f"<link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
            f"<pubDate>{rfc822(p['date'])}</pubDate>"
            f"<category>{ihtml.escape(CATEGORIES[p['category']])}</category>"
            f"<description>{ihtml.escape(p['description'])}</description>"
            "</item>")
    for path, label, desc in [
        ("jeongsugi-rental/", "청호나이스 정수기 렌탈 안내",
         "청호나이스 정수기 렌탈료와 관리 방식, 의무사용기간을 정리한 안내 페이지입니다."),
        ("eoreum-jeongsugi/", "청호나이스 얼음정수기 안내",
         "얼음정수기 렌탈료와 제빙 방식, 설치 조건을 정리한 안내 페이지입니다."),
        ("office/", "사무실·매장 정수기 렌탈 안내",
         "사무실과 매장의 인원·업종별 정수기 선택 기준을 정리한 안내 페이지입니다."),
        ("guide-wiyakgeum/", "의무사용기간과 위약금 안내",
         "렌탈 의무사용기간과 중도해지 시 위약금 구조를 정리한 안내 페이지입니다."),
    ]:
        items.append("<item>"
                     f"<title>{label}</title><link>{origin}/{path}</link>"
                     f"<guid isPermaLink=\"true\">{origin}/{path}</guid>"
                     f"<description>{desc}</description></item>")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>청호나이스 렌탈 안내</title>
<link>{origin}/</link>
<atom:link href="{origin}/rss.xml" rel="self" type="application/rss+xml"/>
<description>청호나이스 정수기·얼음정수기·공기청정기·비데 렌탈료와 계약 조건을 정리한 안내 모음입니다.</description>
<language>ko</language>
<lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""
    with open(os.path.join(ROOT, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(xml)



def update_home_latest(posts, origin):
    """메인 페이지 #lineup 안의 '블로그 최신 글' 목록을 최신 5편으로 갱신한다.

    메인에서 새 글로 곧장 링크가 걸려야 검색로봇이 새 글을 빨리 발견한다."""
    path = os.path.join(ROOT, "index.html")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    begin, end = "<!-- blog:latest:begin -->", "<!-- blog:latest:end -->"
    if begin not in text or end not in text:
        return
    items = "".join(
        f'<li><a href="{origin}/blog/{p["slug"]}/"><b>{ihtml.escape(p["title"])}</b>'
        f'<span>{ihtml.escape(CATEGORIES[p["category"]])} · {p["date"]}</span></a></li>'
        for p in posts[:5])
    block = f'{begin}\n  <ul class="lnk">{items}</ul>\n  {end}'
    new = re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _: block, text, flags=re.S)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    origin = cfg["origin"].rstrip("/")
    kakao = cfg.get("kakao_channel") or f"{origin}/#contact"

    posts = load_posts()
    for i, p in enumerate(posts):
        prev_post = posts[i + 1] if i + 1 < len(posts) else None   # 더 오래된 글
        next_post = posts[i - 1] if i > 0 else None                # 더 최신 글
        build_post(p, origin, kakao, prev_post, next_post, posts)
    build_index(posts, origin, kakao)
    build_sitemap(posts, origin)
    build_rss(posts, origin)
    update_home_latest(posts, origin)

    print(f"블로그 글 {len(posts)}편 생성 → blog/")
    for p in posts:
        print(f"  {p['date']}  [{p['category']}] {p['slug']}  {p['title']}")
    print("sitemap.xml / rss.xml 갱신 완료")
    print("\n다음: python3 tools/apply_config.py  (새로 만든 페이지의 플레이스홀더도 함께 치환됩니다)")


if __name__ == "__main__":
    sys.exit(main())
