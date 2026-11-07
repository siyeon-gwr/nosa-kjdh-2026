"""
scripts/nosa/eval_loo.py — leave-one-out 분절 평가 (읽기 + OpenAI 호출만)

문제: 골드 2편(理通說·答權信元)이 2_segment.py의 few-shot 예시와 채점 기준을
겸하고 있어 평가가 순환한다. 예시로 본 편을 다시 맞히는 건 성능이 아니다.

방법: 한 편을 예시에서 빼고(hold-out) 그 편을 분절해 골드와 대조한다.
남은 한 편만 예시로 쓴다.

2_segment.py는 수정하지 않는다. 모듈명이 숫자로 시작해 import 문으로는 못 불러오므로
importlib으로 파일을 직접 적재하고, GOLD_FILES만 런타임에 갈아끼워
build_fewshot(:60-73, 예시 출력 조립 :66-71)과 SYSTEM(:76-88)·make_user_prompt·
segment_one을 그대로 재사용한다.

쓰기 없음: R2 저장·Pinecone 업서트 호출 안 한다. 결과는 _loo_{hold}.md 로만 쓴다.
(2_segment.py가 import 시점에 r2util을 들이지만 save_json은 호출하지 않는다.)

실행 (Render Shell):
  python scripts/nosa/eval_loo.py                      # 기본 --hold kwonsinwon
  python scripts/nosa/eval_loo.py --hold itongseol
  python scripts/nosa/eval_loo.py --hold kwonsinwon --prefix-n 20

환경변수: OPENAI_API_KEY
의존: scripts/nosa/2_segment.py (읽기 재사용), scripts/nosa/nosa_corpus.json, 골드 2편
"""
import os, sys, re, json, argparse, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

CORPUS = os.path.join(HERE, "nosa_corpus.json")

HOLD = {
    "itongseol":  {"gold": "itongseol_units.json",         "label": "理通說"},
    "kwonsinwon": {"gold": "answer_kwonsinwon_units.json", "label": "答權信元"},
}


# ================================================================
#  2_segment.py 적재 (수정 없음)
# ================================================================

def load_segment_module():
    # 2_segment.py는 모듈 최상단에서 r2util(→boto3)을 들인다. 이 평가는 R2를 쓰지 않으므로
    # boto3가 없는 환경에서는 스텁을 끼워 적재만 되게 한다. 호출은 어차피 없다.
    try:
        import boto3  # noqa: F401
    except ImportError:
        import types
        stub = types.ModuleType("r2util")
        def _blocked(*a, **k):
            raise RuntimeError("eval_loo는 R2를 쓰지 않는다 (boto3 미설치 스텁)")
        stub.save_json = stub.load_json = stub.exists = _blocked
        sys.modules.setdefault("r2util", stub)

    path = os.path.join(HERE, "2_segment.py")
    spec = importlib.util.spec_from_file_location("nosa_2_segment", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ================================================================
#  코퍼스에서 hold 편 찾기
# ================================================================

def find_corpus_rec(corpus, gold):
    """골드 source의 key → dci에서 유도한 key → dci 직접 → 제목+갈래 순으로 조회.
    코퍼스 title은 '권신원에게 답하다〔答權信元〕' 형태이고 같은 제목이 5편 있어
    제목 매칭은 최후 수단이다."""
    src = gold.get("source", {})
    by_key = {r.get("key"): r for r in corpus}

    cands = []
    if src.get("key"):
        cands.append(src["key"])
    for f in ("dci", "mp_dci", "mo_dci", "bt_dci"):
        v = src.get(f)
        if v:
            m = re.search(r"(0628A(?:_\d+){3})", v)
            if m:
                cands.append(m.group(1))
    for k in cands:
        if k in by_key:
            return by_key[k], f"key={k}"

    for f in ("dci", "mp_dci", "mo_dci", "bt_dci"):
        v = src.get(f)
        if not v:
            continue
        for r in corpus:
            if v in (r.get("mo_dci"), r.get("mp_dci"), r.get("bt_dci")):
                return r, f"{f}={v}"

    t = src.get("title", "")
    hit = [r for r in corpus
           if t and t in (r.get("title") or "") and r.get("genre") == src.get("genre")]
    if len(hit) == 1:
        return hit[0], f"title~{t}"

    raise SystemExit(f"코퍼스에서 hold 편을 특정하지 못했다. 후보 key={cands}, 제목일치 {len(hit)}건")


# ================================================================
#  경계 매칭 · 채점
# ================================================================

def head(text, n):
    """공백·개행 제거 후 앞 n자. 경계 비교용 지문."""
    return re.sub(r"\s", "", text or "")[:n]


def is_abridged(units):
    """골드 hanmun에 생략부호가 있으면 축약본. 答權信元 골드가 이에 해당한다.
    축약본은 단위의 끝이 원문의 끝이 아니므로 끝 경계를 채점할 수 없다."""
    return any("…" in (u.get("hanmun") or "") for u in units)


def align(gold_units, pred_units, n):
    """골드 순서대로 같은 지문을 가진 미사용 예측 단위를 하나씩 물린다."""
    used, pairs, gold_miss = set(), [], []
    for gi, g in enumerate(gold_units):
        gh = head(g.get("hanmun", ""), n)
        for pi, p in enumerate(pred_units):
            if pi in used:
                continue
            if head(p.get("hanmun", ""), n) == gh:
                used.add(pi)
                pairs.append((gi, pi))
                break
        else:
            gold_miss.append(gi)
    pred_extra = [pi for pi in range(len(pred_units)) if pi not in used]
    return pairs, gold_miss, pred_extra


def qs_class(gold_qs, pred_qs):
    g, p = gold_qs or None, pred_qs or None
    if g is None and p is None:
        return "정확(비인용)"
    if g is not None and g == p:
        return "정확(인용)"
    if g is not None and p is None:
        return "미배정"
    if g is None and p is not None:
        return "오배정(과잉)"
    return "오배정(오인)"


# ================================================================
#  보고서
# ================================================================

def write_report(path, ctx, gold_units, pred_units, pairs, gold_miss, pred_extra, stats, qs_rows, fn_rows):
    L = []
    A = L.append
    A(f"# LOO 평가 — hold: {ctx['label']} ({ctx['hold']})")
    A("")

    if ctx["shot_abridged"]:
        A(f"> **경고 — 예시가 축약본이다.** 이번 실행의 유일한 few-shot 예시인 "
          f"{ctx['shot_label']}({ctx['shot_file']})은 hanmun에 생략부호(…)가 들어간 축약본이다. "
          f"2_segment.py의 SYSTEM 지시는 \"hanmun을 모두 이으면 반드시 입력 원문과 일치해야 한다\"고 "
          f"요구하는데, 예시 자체가 그 조건을 어긴 견본이다. 모델은 원문 누락을 허용된 것으로 학습할 수 있다.")
        A(">")
        A("> **두 방향(--hold itongseol / --hold kwonsinwon) 수치를 같은 잣대로 비교하지 마라.** "
          "예시의 성질이 달라 조건이 대등하지 않다.")
        A("")

    A("## 채점 기준")
    A("")
    A(f"- **시작 경계 기준.** 골드 hanmun의 공백 제거 후 앞 {ctx['prefix_n']}자가 같으면 같은 단위로 본다.")
    A("- **끝 경계는 채점하지 않는다.** "
      + (f"{ctx['label']} 골드가 축약본(…)이라 단위의 끝이 원문의 끝이 아니다. 길이·종료 지점 대조는 무의미하다."
         if ctx["gold_abridged"] else
         "이 골드는 축약본이 아니지만, 두 방향의 기준을 맞추기 위해 시작 경계만 채점한다."))
    A("- quoted_speaker·function은 시작 경계가 물린 쌍에 한해 채점한다.")
    A("")

    A("## 실행 조건")
    A("")
    A("| 항목 | 값 |")
    A("|---|---|")
    A(f"| 예시에서 제외한 편 | {ctx['label']} ({ctx['gold_file']}) |")
    A(f"| 예시로 쓴 편 | {ctx['shot_label']} ({ctx['shot_file']}) |")
    A(f"| 코퍼스 조회 | {ctx['lookup']} |")
    A(f"| 코퍼스 제목 | {ctx['rec_title']} |")
    A(f"| 갈래 · 권 | {ctx['genre']} · {ctx['volume']} |")
    A(f"| 원문 길이 | {ctx['hanmun_len']}자 |")
    A(f"| max_tokens | {ctx['max_tokens']} |")
    A(f"| 경계 지문 | 공백 제거 후 앞 {ctx['prefix_n']}자 (시작 경계만, 끝 경계 미채점) |")
    A(f"| 예시 축약 여부 | {'축약본 (…)' if ctx['shot_abridged'] else '전문'} |")
    A(f"| 골드 축약 여부 | {'축약본 (…)' if ctx['gold_abridged'] else '전문'} |")
    A("")
    A("## 요약")
    A("")
    A("| 지표 | 값 |")
    A("|---|---|")
    A(f"| 골드 단위 수 | {len(gold_units)} |")
    A(f"| 예측 단위 수 | {len(pred_units)} |")
    A(f"| 경계 일치 (시작 경계) | {len(pairs)} / {len(gold_units)} |")
    A(f"| 미매칭 골드 | {len(gold_miss)} |")
    A(f"| 잉여 예측 | {len(pred_extra)} |")
    A(f"| quoted_speaker 정확 | {stats['qs_ok']} / {len(pairs)} (인용 {stats['qs_ok_q']} · 비인용 {stats['qs_ok_n']}) |")
    A(f"| quoted_speaker 오배정 | {stats['qs_bad']} (과잉 {stats['qs_over']} · 오인 {stats['qs_wrong']}) |")
    A(f"| quoted_speaker 미배정 | {stats['qs_missing']} |")
    A(f"| function 일치 | {stats['fn_ok']} / {len(pairs)} |")
    A("")

    A("## quoted_speaker 불일치")
    A("")
    if qs_rows:
        A("| 골드 uid | 판정 | 골드 | 예측 | 원문 앞 30자 |")
        A("|---|---|---|---|---|")
        for r in qs_rows:
            A(f"| {r['uid']} | {r['cls']} | {r['gold'] or 'null'} | {r['pred'] or 'null'} | {r['head']} |")
    else:
        A("없음.")
    A("")

    A("## function 불일치")
    A("")
    if fn_rows:
        A("| 골드 uid | 골드 | 예측 | 원문 앞 30자 |")
        A("|---|---|---|---|")
        for r in fn_rows:
            A(f"| {r['uid']} | {r['gold'] or '-'} | {r['pred'] or '-'} | {r['head']} |")
    else:
        A("없음.")
    A("")

    A("## 미매칭 골드 단위 (예측에 대응 없음)")
    A("")
    if gold_miss:
        for gi in gold_miss:
            g = gold_units[gi]
            A(f"- `{g.get('uid', gi + 1)}` · {g.get('function', '-')} · qs={g.get('quoted_speaker') or 'null'}")
            A(f"  - 골드: {head(g.get('hanmun', ''), 60)}")
    else:
        A("없음.")
    A("")

    A("## 잉여 예측 단위 (골드에 대응 없음)")
    A("")
    if pred_extra:
        for pi in pred_extra:
            p = pred_units[pi]
            A(f"- seq={p.get('seq', pi + 1)} · {p.get('function', '-')} · qs={p.get('quoted_speaker') or 'null'}")
            A(f"  - 예측: {head(p.get('hanmun', ''), 60)}")
    else:
        A("없음.")
    A("")

    A("## 경계 대조 전량 (골드 순서)")
    A("")
    A("| # | 골드 uid | 골드 앞 30자 | 예측 앞 30자 | 매칭 |")
    A("|---|---|---|---|---|")
    pmap = dict(pairs)
    for gi, g in enumerate(gold_units):
        pi = pmap.get(gi)
        ph = head(pred_units[pi].get("hanmun", ""), 30) if pi is not None else "—"
        A(f"| {gi + 1} | {g.get('uid', '-')} | {head(g.get('hanmun', ''), 30)} | {ph} | {'O' if pi is not None else 'X'} |")
    A("")

    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


# ================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", choices=sorted(HOLD), default="kwonsinwon")
    ap.add_argument("--prefix-n", type=int, default=15, help="경계 지문 길이 (기본 15자)")
    ap.add_argument("--out", default=None, help="보고서 경로 (기본 저장소 루트 _loo_{hold}.md)")
    args = ap.parse_args()

    hold, keep = args.hold, [k for k in HOLD if k != args.hold][0]
    gold_path = os.path.join(HERE, HOLD[hold]["gold"])
    shot_path = os.path.join(HERE, HOLD[keep]["gold"])

    gold = json.load(open(gold_path, encoding="utf-8"))
    gold_units = gold["units"]
    shot_units = json.load(open(shot_path, encoding="utf-8"))["units"]
    gold_abridged, shot_abridged = is_abridged(gold_units), is_abridged(shot_units)
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    rec, lookup = find_corpus_rec(corpus, gold)

    seg = load_segment_module()

    # few-shot에서 hold 편을 뺀다. 남은 한 편만 예시.
    seg.GOLD_FILES = [shot_path]
    shots = seg.build_fewshot()

    addressee = seg.extract_addressee(rec["title"])
    hanmun = rec["hanmun"]
    mt = 8000 if len(hanmun) > 2500 else 4000   # 2_segment.py:167과 동일 기준

    print(f"hold: {HOLD[hold]['label']} ({hold}) — 예시 제외")
    print(f"예시: {HOLD[keep]['label']} ({keep}) 1편, 단위 {len(shot_units)}개"
          + (" [축약본]" if shot_abridged else ""))
    if shot_abridged:
        print(f"  경고: 예시 {HOLD[keep]['label']}이 축약본(…)이다. SYSTEM의 '원문 일치' 지시와 어긋난 견본이다.")
        print(f"        다른 방향(--hold {keep}) 수치와 같은 잣대로 비교하지 마라.")
    print(f"채점: 시작 경계 기준 앞 {args.prefix_n}자, 끝 경계 미채점"
          + (f" ({HOLD[hold]['label']} 골드가 축약본)" if gold_abridged else ""))
    print(f"코퍼스: {lookup} | {rec['title']} | {rec['genre']} | {rec['volume']} | {len(hanmun)}자")
    print(f"골드 단위 수: {len(gold_units)} | max_tokens={mt}")
    print("분절 요청 중...", flush=True)

    from services.embedding import get_openai_client
    client = get_openai_client()
    pred_units = seg.segment_one(client, shots, seg.SCHOLAR["name"], addressee,
                                 rec["genre"], hanmun, mt)
    print(f"예측 단위 수: {len(pred_units)}")

    pairs, gold_miss, pred_extra = align(gold_units, pred_units, args.prefix_n)

    stats = {"qs_ok": 0, "qs_ok_q": 0, "qs_ok_n": 0, "qs_bad": 0,
             "qs_over": 0, "qs_wrong": 0, "qs_missing": 0, "fn_ok": 0}
    qs_rows, fn_rows = [], []
    for gi, pi in pairs:
        g, p = gold_units[gi], pred_units[pi]
        cls = qs_class(g.get("quoted_speaker"), p.get("quoted_speaker"))
        if cls.startswith("정확"):
            stats["qs_ok"] += 1
            stats["qs_ok_q" if cls == "정확(인용)" else "qs_ok_n"] += 1
        elif cls == "미배정":
            stats["qs_missing"] += 1
        else:
            stats["qs_bad"] += 1
            stats["qs_over" if cls == "오배정(과잉)" else "qs_wrong"] += 1
        if not cls.startswith("정확"):
            qs_rows.append({"uid": g.get("uid", gi + 1), "cls": cls,
                            "gold": g.get("quoted_speaker"), "pred": p.get("quoted_speaker"),
                            "head": head(g.get("hanmun", ""), 30)})

        gf, pf = g.get("function", ""), p.get("function", "")
        if gf and gf == pf:
            stats["fn_ok"] += 1
        elif gf != pf:
            fn_rows.append({"uid": g.get("uid", gi + 1), "gold": gf, "pred": pf,
                            "head": head(g.get("hanmun", ""), 30)})

    ctx = {
        "hold": hold, "label": HOLD[hold]["label"], "gold_file": HOLD[hold]["gold"],
        "shot_label": HOLD[keep]["label"], "shot_file": HOLD[keep]["gold"],
        "lookup": lookup, "rec_title": rec["title"], "genre": rec["genre"],
        "volume": rec["volume"], "hanmun_len": len(hanmun),
        "max_tokens": mt, "prefix_n": args.prefix_n,
        "gold_abridged": gold_abridged, "shot_abridged": shot_abridged,
    }
    out = args.out or os.path.join(ROOT, f"_loo_{hold}.md")
    write_report(out, ctx, gold_units, pred_units, pairs, gold_miss, pred_extra, stats, qs_rows, fn_rows)

    print("=" * 52)
    print(f"골드 {len(gold_units)} / 예측 {len(pred_units)}")
    print(f"경계 일치        {len(pairs)}/{len(gold_units)}  (미매칭 골드 {len(gold_miss)}, 잉여 예측 {len(pred_extra)})")
    print(f"quoted_speaker   정확 {stats['qs_ok']} (인용 {stats['qs_ok_q']}·비인용 {stats['qs_ok_n']}) / "
          f"오배정 {stats['qs_bad']} (과잉 {stats['qs_over']}·오인 {stats['qs_wrong']}) / 미배정 {stats['qs_missing']}")
    print(f"function 일치     {stats['fn_ok']}/{len(pairs)}")
    print("=" * 52)
    print(f"보고서: {out}")


if __name__ == "__main__":
    main()
