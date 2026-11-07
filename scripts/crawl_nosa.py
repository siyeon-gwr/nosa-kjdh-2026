"""
노사집(蘆沙集) 한국고전종합DB 크롤러 v2
번역(BT) + 교감표점(MP, 우선) / 영인표점(MO, 대체) 동시 수집

확인된 사실
  1) 본문:  GET /dir/node?dataId={짧은DCI}
     짧은DCI = ITKC_{BT|MO|MP}_0628A_{권}_{문체}_{글}
     긴 DCI(..._2016_001_XML)를 넣으면 HTTP 500
  2) 세 계열이 동일 키를 공유 → 정렬 작업 불필요
        BT  ITKC_BT_0628A_0010_010_0010   번역문 (+각주)
        MO  ITKC_MO_0628A_0010_010_0010   영인표점.  구두점 「。」만
        MP  ITKC_MP_0628A_0010_010_0010   교감표점.  「，」「。」 구별 ← 발화분할에 유리
     MP는 전 갈래에 있지 않다. 書(권4~15)에는 있고 雜著(권16)에는 없다 → MO로 대체
  3) 순차이동: GET /dir/nextPrevViewAjax?dataId={짧은DCI} → {"자료ID":"다음ID"}
  4) 노사집 = 0628A.  書 = 권4~15 (0040~0150), 문체코드 010
  5) BT 본문 뒤에 각주가 [주-D001] 형태로 붙는다 → 분리 저장
  6) 제목의 答/與 구별
        答○○  = 상대 편지에 대한 답장 → 상대 발화가 인용으로 남음
        與○○  = 먼저 보낸 편지        → 응답 관계 없음
     발화 단위 판정 기준이 갈리는 지점

사용
  python3 crawl_nosa.py         # 書 전체 (약 696편, ~30분)
  python3 crawl_nosa.py 10      # 앞 10편 시험
"""
import re, json, time, html, sys, urllib.request, urllib.error

BASE = "https://db.itkc.or.kr"
HDRS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Referer": BASE + "/dir/item?itemId=BT",
}
DELAY = 0.7
START = "ITKC_BT_0628A_0040_010_0010"   # 권4 書 첫 편
LAST_VOL = "0150"                        # 권15까지 書


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 500:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def parse_node(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    lines = [re.sub(r"[ \t]+", " ", l).strip()
             for l in html.unescape(re.sub(r"<[^>]+>", "\n", h)).split("\n")]
    lines = [l for l in lines if l]
    try:
        di = next(i for i, l in enumerate(lines) if l.startswith("[DCI]"))
    except StopIteration:
        return None

    head = " ".join(lines[:di])
    m = re.search(r"최종정보\s+(.+?)\s*/\s*(\S+?)\s+(.+)$", head)
    volume, genre, title = (m.group(1), m.group(2), m.group(3)) if m else ("", "", "")
    title = re.sub(r"\s*〔\s*", "〔", re.sub(r"\s*〕", "〕", title)).strip()

    body = []
    for l in lines[di + 1:]:
        if l.startswith("ⓒ") or l.startswith("©"):
            break
        if l in ("DCI복사", "URL복사", "▲TOP", "새창열기", "동시 스크롤"):
            continue
        body.append(l)
    return {"dci": lines[di].replace("[DCI]", "").split()[0],
            "volume": volume.strip(), "genre": genre.strip(),
            "title": title, "body": "\n".join(body)}


def split_footnotes(t):
    """번역문 본문과 각주를 분리."""
    i = t.find("[주-")
    if i < 0:
        return re.sub(r"[ \t]{2,}", " ", t).strip(), []
    body = t[:i].strip()
    notes = re.findall(r"\[주-([A-Z]?\d+)\]\s*(.+?)(?=\[주-|$)", t[i:], flags=re.S)
    return body, [{"id": a, "text": re.sub(r"\s+", " ", b).strip()} for a, b in notes]


def clean_han(t):
    t = re.sub(r"[a-z]\d{3}_\d{3}[a-d]", "", t)   # a310_359b 면수 마커
    return re.sub(r"\s+", "", t).strip()


def fetch(data_id):
    h = get(f"{BASE}/dir/node?dataId={data_id}")
    if not h or "시스템 오류" in h:
        return None
    return parse_node(h)


def next_id(data_id):
    j = get(f"{BASE}/dir/nextPrevViewAjax?dataId={data_id}")
    m = re.search(r'"자료ID"\s*:\s*"([^"]+)"', j) if j else None
    return m.group(1) if m else None


def classify(title):
    if "答" in title or title.startswith("답"):
        return "答"
    if "與" in title or title.startswith("보내") or "보내다" in title:
        return "與"
    return "기타"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 9
    cur, out, n = START, [], 0
    while cur and n < limit:
        if cur.split("_")[3] > LAST_VOL:
            break
        bt = fetch(cur)
        if not bt:
            break
        key = "_".join(cur.split("_")[2:])

        mp = fetch("ITKC_MP_" + key)
        mo = fetch("ITKC_MO_" + key)
        src = mp or mo
        han_src = "MP" if mp else ("MO" if mo else "")

        body, notes = split_footnotes(bt["body"])
        kind = classify(bt["title"])

        rec = {
            "key": key,
            "volume": bt["volume"], "genre": bt["genre"], "title": bt["title"],
            "letter_kind": kind,
            "korean": body,
            "footnotes": notes,
            "hanmun": clean_han(src["body"]) if src else "",
            "hanmun_source": han_src,
            "bt_dci": bt["dci"],
            "mp_dci": mp["dci"] if mp else "",
            "mo_dci": mo["dci"] if mo else "",
        }
        out.append(rec)
        n += 1
        print(f"[{n:3d}] {key} {kind} {bt['title'][:22]:<22} "
              f"ko{len(body):5d} hm{len(rec['hanmun']):5d}({han_src}) 註{len(notes):2d}")

        nxt = next_id(cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
        time.sleep(DELAY)

    json.dump(out, open("nosa_seo.json", "w"), ensure_ascii=False, indent=1)
    kinds = {}
    for r in out:
        kinds[r["letter_kind"]] = kinds.get(r["letter_kind"], 0) + 1
    print(f"\n저장: nosa_seo.json  {len(out)}편   갈래별 {kinds}")


if __name__ == "__main__":
    main()
