#!/usr/bin/env python3
"""사이트 주소(origin)를 통째로 바꾼다. 네이버 서치어드바이저 등록을 위한 주소 이전용.

  python3 tools/set_origin.py https://niceeng-rental.co.kr
  python3 tools/set_origin.py https://niceeng-rental.co.kr --dry-run

왜 필요한가
  네이버 서치어드바이저는 사이트를 **호스트 단위로만** 등록받는다.
  https://pg5chb7mn6-blip.github.io/chungho-rental/ 처럼 하위 경로에 있는 사이트는
  등록 자체가 되지 않는다("URL을 호스트 단위로 입력해주세요").
  그래서 사이트가 호스트 루트에 오도록 주소를 옮겨야 한다.

하는 일
  1. 모든 html/xml/txt/md/json 안의 기존 origin 문자열을 새 origin 으로 치환
  2. robots.txt 의 Disallow 경로와 Sitemap 줄을 새 경로 기준으로 재작성
  3. ops/site.config.json 의 origin 갱신
  4. 커스텀 도메인이면 CNAME 파일 생성, github.io 로 돌아가면 삭제

주의
  주소를 옮기면 검색엔진 색인이 초기화된다. **글이 쌓이기 전에 지금 하는 편이 낫다.**
  옮긴 뒤에는 서치어드바이저·서치콘솔에 새 주소로 다시 등록해야 한다.
"""
import json
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "ops", "site.config.json")
EXTS = (".html", ".xml", ".txt", ".md", ".json")
SKIP_DIRS = {".git", "node_modules"}


def target_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(EXTS):
                yield os.path.join(dirpath, fn)


def rewrite_robots(new_origin, dry):
    path = os.path.join(ROOT, "robots.txt")
    if not os.path.exists(path):
        return
    prefix = urlparse(new_origin).path.rstrip("/")     # 커스텀 도메인이면 ""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^Disallow: .*admin\.html$",
                  f"Disallow: {prefix}/admin.html", text, flags=re.M)
    text = re.sub(r"^Sitemap: .*$",
                  f"Sitemap: {new_origin}/sitemap.xml", text, flags=re.M)
    if not dry:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"  robots.txt  Disallow {prefix}/admin.html · Sitemap {new_origin}/sitemap.xml")


def handle_cname(new_origin, dry):
    """커스텀 도메인이면 CNAME 파일이 있어야 GitHub Pages 가 그 도메인으로 서비스한다."""
    host = urlparse(new_origin).netloc
    path = os.path.join(ROOT, "CNAME")
    if host.endswith(".github.io"):
        if os.path.exists(path):
            if not dry:
                os.remove(path)
            print("  CNAME 삭제 (github.io 로 돌아감)")
        return
    if not dry:
        with open(path, "w", encoding="utf-8") as f:
            f.write(host + "\n")
    print(f"  CNAME 생성 → {host}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 1:
        print(__doc__)
        return 2

    new_origin = args[0].rstrip("/")
    parsed = urlparse(new_origin)
    if parsed.scheme != "https" or not parsed.netloc:
        print("[오류] https://도메인 형태로 입력하세요. 예: https://niceeng-rental.co.kr")
        return 2

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    old_origin = cfg["origin"].rstrip("/")

    if old_origin == new_origin:
        print(f"이미 {new_origin} 입니다. 바뀔 것이 없습니다.")
        return 0

    print(f"{old_origin}\n  →  {new_origin}\n")
    if parsed.path.rstrip("/"):
        print("  ⚠ 새 주소에도 하위 경로가 남아 있습니다. 네이버는 호스트 단위로만 등록받으므로")
        print("    이 상태로는 서치어드바이저 등록이 여전히 되지 않습니다.\n")

    changed = total = 0
    for path in target_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if old_origin not in text:
            continue
        hits = text.count(old_origin)
        total += hits
        changed += 1
        if not dry:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace(old_origin, new_origin))

    print(f"  파일 {changed}개 · 링크 {total}개 치환")
    rewrite_robots(new_origin, dry)
    handle_cname(new_origin, dry)

    if not dry:
        cfg["origin"] = new_origin
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("  ops/site.config.json 갱신")

    if dry:
        print("\n[--dry-run] 실제로는 아무것도 바꾸지 않았습니다.")
        return 0

    host = parsed.netloc
    print(f"""
다음에 할 일

  1. python3 tools/build_blog.py     (사이트맵·RSS를 새 주소로 다시 생성)
  2. python3 tools/apply_config.py
  3. git add -A && git commit -m "사이트 주소 이전: {host}" && git push
""")
    if not host.endswith(".github.io"):
        print(f"""  4. 도메인 DNS 설정
       A 레코드   @    185.199.108.153 / 185.199.109.153 / 185.199.110.153 / 185.199.111.153
       CNAME      www  pg5chb7mn6-blip.github.io.
  5. GitHub 저장소 → Settings → Pages → Custom domain 에 {host} 입력 → Enforce HTTPS 체크
  6. https://{host}/ 가 열리는지 확인 (DNS 전파에 최대 24시간)
  7. 네이버 서치어드바이저에 https://{host}/ 등록 → 소유확인 → 사이트맵·RSS 제출
  8. 구글 서치콘솔에도 새 주소로 속성 추가 (기존 속성은 그대로 두고 병행 관찰)""")
    else:
        print(f"""  4. GitHub 저장소 이름을 정확히 `{host}` 로 변경
       (Settings → Repository name) — 이 이름이어야 호스트 루트로 서비스됩니다
  5. https://{host}/ 가 열리는지 확인
  6. 네이버 서치어드바이저에 https://{host}/ 등록 → 소유확인 → 사이트맵·RSS 제출""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
