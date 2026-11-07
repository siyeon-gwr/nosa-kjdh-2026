"""
표지를 갖췄으나 인용 화자가 비어 있는 단위에서 표본을 뽑아 분류용 CSV를 만든다.

사용법:
    python sample_unattributed.py nosa_units.json
출력:
    unattributed_sample.csv  (label 열에 A/B/C를 직접 기입)
      A = 인용 아님 (정상 비귀속)
      B = 인용인데 누락 (speaker_should_be에 화자 기입)
      C = 분절 오류 (인용 구간이 단위 경계에서 잘림)
"""
import csv
import json
import random
import sys

MARKERS = ["兄每言", "來喩", "盛敎", "曰", "云", "謂", "老兄", "示喩", "來書"]
# 답장 전용 표지를 우선 표집한다
STRATA = [("來書", 10), ("示喩", 10), ("老兄", 5), ("曰|云|謂", 5)]
TEXT_KEYS = ["text", "original", "원문", "content", "body"]
SPEAKER_KEYS = ["citation_speaker", "quoted_speaker", "speaker", "인용화자", "cited_speaker"]
SEED = 42


def pick(d, keys):
    for k in keys:
        if k in d:
            return k
    return None


def main(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    units = data["units"] if isinstance(data, dict) and "units" in data else data

    tk, sk = pick(units[0], TEXT_KEYS), pick(units[0], SPEAKER_KEYS)
    if not tk or not sk:
        sys.exit(f"필드명을 찾지 못함. 실제 키: {list(units[0].keys())}")
    print(f"원문 필드={tk}, 화자 필드={sk}, 전체 단위={len(units)}")

    marked, unattr = [], []
    for i, u in enumerate(units):
        text = u.get(tk) or ""
        found = [m for m in MARKERS if m in text]
        if not found:
            continue
        marked.append(i)
        if not (u.get(sk) or "").strip():
            unattr.append((i, found))

    # 논문 수치(수정본): 1,518 / 185 / 1,333
    print(f"표지 단위={len(marked)}, 귀속={len(marked) - len(unattr)}, 미귀속={len(unattr)}")

    random.seed(SEED)
    chosen, used = [], set()
    for pattern, n in STRATA:
        keys = pattern.split("|")
        pool = [x for x in unattr if x[0] not in used and any(k in x[1] for k in keys)]
        take = random.sample(pool, min(n, len(pool)))
        for x in take:
            used.add(x[0])
            chosen.append((pattern, x))
        print(f"  {pattern}: 후보 {len(pool)} 중 {len(take)}")

    with open("unattributed_sample.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stratum", "index", "volume", "title", "markers", "text",
                    "label(A/B/C)", "speaker_should_be", "note"])
        for pattern, (i, found) in chosen:
            u = units[i]
            w.writerow([pattern, i, u.get("volume", ""), u.get("title", ""),
                        " ".join(found), u.get(tk, ""), "", "", ""])
    print(f"unattributed_sample.csv 저장: {len(chosen)}건")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "nosa_units.json")
