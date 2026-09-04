#!/usr/bin/env python3
"""ops/site.config.json 값으로 사이트 전체의 {{플레이스홀더}}를 치환하고 추적 스크립트를 심는다.

  python3 tools/apply_config.py          # 실제 치환
  python3 tools/apply_config.py --check  # 파일은 건드리지 않고 남은 항목만 보고

여러 번 실행해도 안전하다(멱등). 값이 비어 있는 항목은 건드리지 않고 마지막에 목록으로 보고한다.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "ops", "site.config.json")

PLACEHOLDER_KEYS = [
    "대표자명", "사업자등록번호", "통신판매업신고번호", "사업장 주소",
    "대표전화", "사내 이메일",
    "네이버_서치어드바이저_인증코드", "구글_서치콘솔_인증코드",
]

BEGIN = "<!-- analytics:begin -->"
END = "<!-- analytics:end -->"


def html_files():
    skip = {".git", "node_modules", "ops", "tools", ".claude"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)


def analytics_block(cfg):
    ga = (cfg.get("ga4_measurement_id") or "").strip()
    na = (cfg.get("naver_analytics_id") or "").strip()
    if not ga and not na:
        return ""
    parts = [BEGIN]
    if ga:
        parts.append(
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>\n'
            f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
            f'gtag("js",new Date());gtag("config","{ga}");</script>'
        )
    if na:
        parts.append(
            '<script type="text/javascript" src="//wcs.naver.net/wcslog.js"></script>\n'
            '<script type="text/javascript">if(!wcs_add)var wcs_add={};'
            f'wcs_add["wa"]="{na}";if(window.wcs){{wcs.inflow();wcs_do();}}</script>'
        )
    parts.append(END)
    return "\n".join(parts) + "\n"


def apply_analytics(text, block):
    """<head> 끝 직전에 삽입. 이미 있으면 교체."""
    if BEGIN in text:
        return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", block, text, flags=re.S)
    if not block:
        return text
    return text.replace("</head>", block + "</head>", 1)


def main():
    check_only = "--check" in sys.argv
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    values = {k: (cfg.get(k) or "").strip() for k in PLACEHOLDER_KEYS}
    filled = {k: v for k, v in values.items() if v}
    empty = [k for k, v in values.items() if not v]
    block = analytics_block(cfg)
    phone = values.get("대표전화", "")

    changed = 0
    for path in html_files():
        with open(path, encoding="utf-8") as f:
            original = f.read()
        text = original
        for key, val in filled.items():
            text = text.replace("{{" + key + "}}", val)
        text = apply_analytics(text, block)
        if phone and path.endswith("index.html") and os.path.dirname(path) == ROOT:
            text = re.sub(r'const PHONE\s*=\s*"[^"]*"', f'const PHONE = "{phone}"', text)
        if text != original:
            changed += 1
            if not check_only:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)

    # 남은 플레이스홀더 집계
    remaining = {}
    for path in html_files():
        with open(path, encoding="utf-8") as f:
            for m in re.findall(r"\{\{([^}]+)\}\}", f.read()):
                remaining.setdefault(m, set()).add(os.path.relpath(path, ROOT))

    verb = "치환 예정" if check_only else "치환 완료"
    print(f"[{verb}] 파일 {changed}개")
    if filled:
        print("  채운 항목: " + ", ".join(filled))
    if block:
        print("  추적 스크립트 삽입: " + ", ".join(
            x for x in [
                "GA4" if (cfg.get("ga4_measurement_id") or "").strip() else "",
                "네이버 애널리틱스" if (cfg.get("naver_analytics_id") or "").strip() else "",
            ] if x))
    if remaining:
        print("\n[아직 비어 있는 항목] — 검색엔진 소유확인과 사업자 정보 표시 의무에 직결됩니다")
        for key in sorted(remaining):
            print(f"  {{{{{key}}}}}  ({len(remaining[key])}개 파일)")
        print("\n  ops/site.config.json 에 값을 채우고 다시 실행하세요.")
        if "통신판매업신고번호" in remaining:
            print("  ※ 통신판매업 미신고 상태라면 값을 넣지 말고, 각 파일 푸터에서 해당 줄을 삭제하세요(허위 표시 금지).")
    else:
        print("\n남은 플레이스홀더 없음. 서치어드바이저/서치콘솔 소유확인을 진행하세요.")
    if empty:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
