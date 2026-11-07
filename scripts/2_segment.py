"""
scripts/nosa/2_segment.py — 범용 LLM 발화 단위 분할 (R2 영구저장)
GPT-4o로 문집 각 편을 발화 단위로 분할.

★ Render 디스크는 재배포 시 초기화된다. 따라서 결과를 R2에 저장한다.
   - 10편마다 R2 중간저장 → 세션 끊겨도, 재배포돼도 안 날아감
   - --resume 시 R2에서 복원 후 이어서
   - 최종 결과도 R2에 저장. 업로드 스크립트가 R2에서 읽음

실행 (Render Shell, 백그라운드 권장):
  nohup python scripts/nosa/2_segment.py > scripts/nosa/seg.log 2>&1 &
  tail -5 scripts/nosa/seg.log      # 진행 확인
  # 끊겨도:
  nohup python scripts/nosa/2_segment.py --resume > scripts/nosa/seg.log 2>&1 &

의존: services/embedding.py, scripts/nosa/r2util.py
"""
import json, os, re, sys, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import r2util

CORPUS = os.path.join(HERE, "nosa_corpus.json")
GOLD_FILES = [
    os.path.join(HERE, "itongseol_units.json"),
    os.path.join(HERE, "answer_kwonsinwon_units.json"),
]
OUT_LOCAL = os.path.join(HERE, "nosa_units.json")
OUT_NAME = "nosa_units.json"   # R2 키

DOC_GENRES = {"序", "疏", "辭狀", "策"}
SCHOLAR = {"name": "奇正鎭", "work": "蘆沙集"}
VOL_TABLE = ["一","二","三","四","五","六","七","八","九","十",
             "十一","十二","十三","十四","十五","十六","十七","十八","十九"]


def volume_hanja(volume_str):
    m = re.search(r"제(\d+)권", volume_str)
    if not m:
        return volume_str
    n = int(m.group(1))
    return f"卷之{VOL_TABLE[n-1]}" if 1 <= n <= 19 else volume_str


def extract_addressee(title):
    m = re.search(r"[答與上寄]([\u4e00-\u9fff]{2,4})", title)
    if m:
        return m.group(1)
    m2 = re.search(r"〔[答與上寄]([^〕]+)〕", title)
    if m2:
        nm = re.search(r"[\u4e00-\u9fff]{2,4}$", m2.group(1))
        return nm.group(0) if nm else ""
    return ""


def build_fewshot():
    shots = []
    for f in GOLD_FILES:
        g = json.load(open(f, encoding="utf-8"))
        units = g["units"]
        example_in = "".join(u["hanmun"] for u in units)
        example_out = json.dumps([
            {"seq": i + 1, "quoted_speaker": u.get("quoted_speaker"),
             "function": u.get("function", ""), "hanmun": u["hanmun"],
             "warning": u.get("warning", "")}
            for i, u in enumerate(units)
        ], ensure_ascii=False)
        shots.append((g["source"].get("title", ""), example_in, example_out))
    return shots


SYSTEM = """당신은 조선 성리학 문집을 발화 단위로 분할하는 전문가다.

발화 단위란 '의미가 완결된 가장 작은 묶음'이다.
- 완결: 하나의 논지가 시작해 끝나는 지점에서 경계가 갈린다.
- 최소성: 더 쪼개면 조각이 홀로 읽히지 않는 지점까지가 한 단위다.
- 화자 전환이나 인용 표지는 경계의 단서일 뿐, 기준은 의미의 완결이다.

인용 판정: 저자가 상대의 말을 끌어온 구간(來喩·示喩·來書·盛敎曰·兄每言 등의 뒤, 또는 상대 주장의 재진술)은
quoted_speaker에 상대를 표시하고, 그 구간을 저자의 주장으로 오독할 위험이 있으면 warning을 남긴다.

출력은 JSON 배열만. 설명·마크다운 금지. 각 원소:
{"seq":정수, "quoted_speaker":문자열 또는 null, "function":"問題提起|定義|轉換|論證|歸結|引用|反駁|結語|問安|敍事|囑託", "hanmun":"해당 구간 원문", "warning":"인용 오독 위험 시 경고, 없으면 빈 문자열"}
hanmun을 모두 이으면 반드시 입력 원문과 일치해야 한다. 글자를 빠뜨리거나 바꾸지 마라."""


def make_user_prompt(shots, scholar_name, addressee, genre, hanmun):
    parts = []
    for title, ex_in, ex_out in shots:
        parts.append(f"[예시 입력 — {title}]\n{ex_in}\n[예시 출력]\n{ex_out}")
    who = f"수신자: {addressee}" if addressee else "독자 대상"
    parts.append(f"[분할 대상]\n저자: {scholar_name} (화자 고정)\n문체: {genre}\n{who}\n원문:\n{hanmun}\n[출력]")
    return "\n\n".join(parts)


def segment_one(client, shots, scholar_name, addressee, genre, hanmun, max_tokens=4000):
    prompt = make_user_prompt(shots, scholar_name, addressee, genre, hanmun)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": prompt}],
        temperature=0, max_tokens=max_tokens,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.M).strip()
    return json.loads(raw)


def persist(units):
    """로컬 + R2 양쪽 저장."""
    json.dump(units, open(OUT_LOCAL, "w"), ensure_ascii=False, indent=1)
    try:
        r2util.save_json(OUT_NAME, units)
    except Exception as e:
        print(f"  [R2 저장 경고] {e}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    from services.embedding import get_openai_client
    client = get_openai_client()

    corpus = json.load(open(CORPUS, encoding="utf-8"))
    shots = build_fewshot()

    all_units, done = [], set()
    if args.resume:
        # R2 우선 복원, 없으면 로컬
        restored = r2util.load_json(OUT_NAME)
        if restored is None and os.path.exists(OUT_LOCAL):
            restored = json.load(open(OUT_LOCAL, encoding="utf-8"))
        if restored:
            all_units = restored
            done = {u["key"] for u in all_units}
            print(f"resume: R2/로컬에서 {len(done)}편 복원, skip", flush=True)

    processed = 0
    for rec in corpus:
        if args.limit and processed >= args.limit:
            break
        key = rec["key"]
        if key in done:
            continue
        genre = rec["genre"]
        base = {
            "source": SCHOLAR["work"], "volume": volume_hanja(rec["volume"]),
            "genre": genre, "title": rec["title"], "speaker": SCHOLAR["name"],
            "addressee": extract_addressee(rec["title"]),
            "letter_kind": rec.get("letter_kind", ""), "key": key,
        }

        if genre in DOC_GENRES:
            text = (rec.get("korean", "") + " ||| " + rec["hanmun"])[:8000]
            all_units.append({"id": f"nosa_{key}_doc", "text": text, **base, "quoted_speaker": None})
            processed += 1
            continue

        # 긴 원문은 처음부터 max_tokens 넉넉히
        mt = 8000 if len(rec["hanmun"]) > 2500 else 4000
        try:
            segs = segment_one(client, shots, SCHOLAR["name"], base["addressee"], genre, rec["hanmun"], mt)
        except Exception as e:
            print(f"  [ERR] {key} {rec['title'][:16]}: {e}", flush=True)
            all_units.append({"id": f"nosa_{key}_fallback", "text": rec["hanmun"][:8000],
                              **base, "quoted_speaker": None, "warning": "자동분할 실패, 편 전체 1단위"})
            processed += 1
            continue

        for i, s in enumerate(segs, 1):
            item = {"id": f"nosa_{key}_{i:02d}", "text": s["hanmun"][:8000], **base,
                    "quoted_speaker": s.get("quoted_speaker"), "function": s.get("function", "")}
            if s.get("warning"):
                item["warning"] = s["warning"]
            all_units.append(item)

        processed += 1
        if processed % 10 == 0:
            persist(all_units)
            print(f"  ...{processed}편 처리, 누적 {len(all_units)}단위 (R2 저장됨)", flush=True)
            time.sleep(0.3)

    persist(all_units)
    qn = sum(1 for u in all_units if u.get("warning"))
    fb = sum(1 for u in all_units if "fallback" in u["id"])
    print(f"\n완료: 로컬+R2 저장\n  처리 편수: {processed}\n  총 단위: {len(all_units)}\n  인용/경고: {qn}\n  fallback: {fb}", flush=True)


if __name__ == "__main__":
    main()
