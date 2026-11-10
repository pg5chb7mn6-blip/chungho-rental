#!/usr/bin/env python3
"""두 원고의 문장 겹침을 재서 네이버 유사문서 위험을 미리 잡는다.

  python3 tools/similarity_check.py ops/posts/naver/A.md ops/posts/B.md

같은 주제를 네이버 블로그와 자사 사이트에 각각 올릴 때, 문장을 복사하면 네이버가
유사문서로 판정해 둘 다 노출이 죽는다. 어절 3-gram 겹침 비율이 25%를 넘으면 다시 써야 한다.
"""
import re
import sys

THRESHOLD = 25.0


def normalize(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"^---.*?---", "", text, flags=re.S)      # 머리말 제거
    text = re.sub(r"\[이미지[^\]]*\]", " ", text)             # 이미지 지시 제거
    text = re.sub(r"\[\[CTA\]\]|^#+ |^[-*|>] |^\d+\. ", " ", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)     # 링크 텍스트만 남김
    text = re.sub(r"[^\w가-힣 ]", " ", text)
    return [w for w in text.split() if w]


def ngrams(words, n=3):
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a_words, b_words = normalize(sys.argv[1]), normalize(sys.argv[2])
    a, b = ngrams(a_words), ngrams(b_words)
    if not a or not b:
        print("[오류] 비교할 본문이 너무 짧습니다.")
        return 2
    shared = a & b
    ratio = len(shared) / min(len(a), len(b)) * 100

    print(f"A: {sys.argv[1]}  ({len(a_words)}어절)")
    print(f"B: {sys.argv[2]}  ({len(b_words)}어절)")
    print(f"겹침 비율: {ratio:.1f}%  (기준 {THRESHOLD}% 이하)")
    if shared:
        print("\n겹치는 표현 (최대 15개):")
        for s in sorted(shared)[:15]:
            print(f"  {s}")
    if ratio > THRESHOLD:
        print(f"\n[보류] 겹침이 {THRESHOLD}%를 넘습니다. 두 원고 중 하나를 다시 쓰세요.")
        print("  같은 사실을 다른 예시·다른 순서·다른 문장으로 풀어야 합니다.")
        return 1
    print("\n[통과] 두 원고를 각각 발행해도 유사문서 위험이 낮습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
