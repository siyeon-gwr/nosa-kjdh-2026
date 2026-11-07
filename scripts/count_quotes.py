"""
scripts/nosa/count_quotes.py — R2의 nosa_units.json 인용 메타 집계 (읽기 전용)

r2util.load_json()으로만 읽는다. 저장·업로드·삭제 호출 없음.

실행 (Render Shell):
  python scripts/nosa/count_quotes.py
  python scripts/nosa/count_quotes.py --top 30      # quoted_speaker 분포 표시 개수

환경변수: R2_ACCOUNT_ID · R2_BUCKET · R2_ACCESS_KEY_ID · R2_SECRET_ACCESS_KEY
의존: scripts/nosa/r2util.py
"""
import os, sys, argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

import r2util

R2_NAME  = "nosa_units.json"
FAIL_MSG = "자동분할 실패"     # 2_segment.py:173의 하드코딩 문자열
ZHUJA    = "朱子曰"
SAY      = "曰"


def pct(n, total):
    return f"{n / total * 100:.1f}%" if total else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20, help="quoted_speaker 분포 표시 개수")
    args = ap.parse_args()

    units = r2util.load_json(R2_NAME)
    if units is None:
        print(f"R2에 {R2_NAME} 없음 (또는 자격증명·접근 실패). 먼저 2_segment.py 실행.")
        sys.exit(1)

    total = len(units)

    warned   = [u for u in units if u.get("warning")]
    seg_fail = [u for u in warned if FAIL_MSG in u["warning"]]
    quote_w  = [u for u in warned if FAIL_MSG not in u["warning"]]

    speakers = Counter(u.get("quoted_speaker") or "null" for u in units)

    zhuja_unattributed = [
        u for u in units
        if ZHUJA in (u.get("text") or "") and not u.get("quoted_speaker")
    ]
    nested = [u for u in units if (u.get("text") or "").count(SAY) >= 2]

    print(f"대상: r2://{os.getenv('R2_BUCKET', '?')}/nosa/{R2_NAME}")
    print("=" * 56)
    print(f"전체 단위 수                     {total:>8}")
    print("-" * 56)
    print(f"warning 보유                     {len(warned):>8}  ({pct(len(warned), total)})")
    print(f"  ├ '{FAIL_MSG}' 포함        {len(seg_fail):>8}  ({pct(len(seg_fail), total)})")
    print(f"  └ 그 외 (인용 오독 경고)       {len(quote_w):>8}  ({pct(len(quote_w), total)})")
    print("-" * 56)
    print(f"quoted_speaker 분포 (상위 {args.top})")
    for name, cnt in speakers.most_common(args.top):
        print(f"  {name:<24} {cnt:>8}  ({pct(cnt, total)})")
    if len(speakers) > args.top:
        print(f"  ... 그 외 {len(speakers) - args.top}종")
    print("-" * 56)
    print(f"text에 '{ZHUJA}' 있으나 quoted_speaker null   {len(zhuja_unattributed):>6}")
    print(f"text에 '{SAY}' 2회 이상 (중첩 인용 후보)        {len(nested):>6}")
    print("=" * 56)

    if zhuja_unattributed:
        print(f"\n[미귀속 '{ZHUJA}' 샘플 5건]")
        for u in zhuja_unattributed[:5]:
            print(f"  {u.get('id', '?')}  {(u.get('text') or '')[:60]}")


if __name__ == "__main__":
    main()
