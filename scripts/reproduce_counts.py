"""
본문 수치를 로컬 제출본(data/nosa_units.json)에서 재현한다. 읽기 전용, 네트워크 불필요.

사용법:
    python scripts/reproduce_counts.py data/nosa_units.json
"""
import json, re, sys
from collections import Counter

MARKERS = ["兄每言", "來喩", "盛敎", "曰", "云", "謂", "老兄", "示喩", "來書"]  # sample_unattributed.py와 동일
FUNCS = ["問題提起", "定義", "轉換", "論證", "歸結", "引用", "反駁", "結語", "問安", "敍事", "囑託"]
MODERN = re.compile("[，「」“”？！：；、『』]")


def main(path):
    U = json.load(open(path, encoding="utf-8"))
    q = lambda u: (u.get("quoted_speaker") or "").strip()
    marked = [u for u in U if any(m in u["text"] for m in MARKERS)]
    att = [u for u in marked if q(u)]
    print(f"전체 단위                      {len(U)}")
    print(f"표지 단위 / 귀속 / 미귀속      {len(marked)} / {len(att)} / {len(marked) - len(att)}")
    for m in MARKERS:
        occ = [u for u in U if m in u["text"]]
        print(f"  {m:<4} 귀속 {sum(1 for u in occ if q(u))} / 출현 {len(occ)}")
    print(f"중첩 후보(曰 2회 이상)         {sum(1 for u in U if u['text'].count('曰') >= 2)}")
    print(f"인용 화자 보유 / 고유값        {sum(1 for u in U if q(u))} / {len(set(q(u) for u in U if q(u)))}")
    print(f"주 화자 분포                   {dict(Counter(u.get('speaker') for u in U))}")
    out = Counter(u.get("function") for u in U if u.get("function") and u["function"] not in FUNCS)
    print(f"11종 밖 function               {sum(out.values())}")
    print(f"引用이면서 화자 없음           {sum(1 for u in U if u.get('function') == '引用' and not q(u))}")
    keys = {}
    for u in U:
        keys.setdefault(u["key"], []).append(u)
    t = Counter("modern" if MODERN.search("".join(x["text"] for x in v)) else "stop" for v in keys.values())
    print(f"표점 체계(편)                  현대식 {t['modern']} / 구독 {t['stop']}")
    mm = {k: v for k, v in keys.items() if "問目" in v[0]["title"]}
    print(f"問目 편 / 단위                 {len(mm)} / {sum(len(v) for v in mm.values())}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/nosa_units.json")
