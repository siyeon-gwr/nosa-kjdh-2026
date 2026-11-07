# Nosa (蘆沙 奇正鎭) AI — KJDH-2026-010 재현 패키지

노사집(蘆沙集) 기반 발화단위 RAG의 **분절·생성·평가 재현물**. 운영 전체 코퍼스·벡터 DB·프로덕션 인프라는 포함하지 않는다.

## 1. 원문 출처와 수집

- **출처**: 한국고전번역원 **한국고전종합DB** (`https://db.itkc.or.kr`). 노사집 書目 ID `ITKC_*_0628A_*`.
- **수집 경로**: **웹 페이지 크롤링**(Open API·공공데이터포털 미사용). 요청 패턴(코드 인용):
  - 본문 노드: `GET https://db.itkc.or.kr/dir/node?dataId=ITKC_{BT|MP|MO}_0628A_{권}_{문체}_{글}` (`scripts/crawl_nosa.py:97`, `2_segment` 계열)
  - 순차 이동/목차: `GET https://db.itkc.or.kr/dir/nextPrevViewAjax?dataId=...` (`scan_toc.py`, `crawl_nosa.py:104`)
- **수집 시점**: 크롤러 커밋일 **2026-07-12** (`askmind-api` 3907b6f). 코드 내 별도 실행일시 기록은 없음.
- **hanmun 필드 = 표점본**: 교감표점(MP) 우선, 없으면 영인표점(MO)으로 저장(`crawl_nosa.py:128-131`, `clean_han`로 면수 마커·공백 제거). 번역문(BT)은 `korean`으로 따로 수집하였다.
- **이용 조건**: 원문·표점·번역의 권리는 한국고전번역원에 있으며 그 이용약관·출처표기 정책을 따른다. 본 패키지는 출처를 명시하고 재현 목적으로만 배포한다.

## 2. 번역문 미재배포 방침

한국고전번역원 **번역문(BT)은 재배포하지 않는다.**
- `data/nosa_units.json` 제출본은 **번역문 없음** 판본을 사용한다.
- `data/gold/*.json`의 `korean`(번역문) 필드는 본 패키지에서 **제거**하였다(hanmun 표점본 + 메타데이터만 유지). 각 파일 `_redistribution_note` 참조.

## 2-1. 생성 규칙 기준

심사용 `cite_rule.txt`는 **재현 파이프라인 발췌본**이며, **운영 생성 규칙의 원문은 `prompts/nosa_cite_guard_rules.txt`**(scholars_config.py의 `cite_guard_rules`, 2dfb874 이후)이다.

## 3. 기준 커밋

- 태그 **`kjdh-2026-010-revision-base`**
  - `askmind-api` → `5eccd44a27d2781781d6b5dbd7d3f7ef32a8c05d`
  - `classical-ai-research` → `22a1c5b95691a275abbbcb392ebbbc8c62e367fd`

## 4. 본문 수치와 재현

`data/nosa_units.json`(번역문 없는 제출본)으로 논문의 수치를 재현한다. 네트워크와 API 키가 필요 없다.

```bash
python3 scripts/reproduce_counts.py data/nosa_units.json
python3 scripts/sample_unattributed.py data/nosa_units.json   # 표지 집계 + 미귀속 표본 30건(unattributed_sample.csv)
```

재현 확인(2026-11-06):

| 항목 | 값 |
|---|---|
| 전체 단위 | 5,505 |
| 표지 단위 / 귀속 / 미귀속 | 1,518 / 185 / 1,333 |
| 曰 · 云 · 謂 (귀속/출현) | 135/630 · 45/438 · 54/677 |
| 중첩 후보(曰 2회 이상) | 202 |
| 인용 화자 보유 단위 / 고유값 | 236 / 104 |
| 11종 밖 function / 引用이면서 화자 없음 | 30 / 141 |
| 표점 체계(편): 현대식 / 구독 | 526 / 327 |
| 問目 편 / 단위 | 36 / 670 |

운영 색인에서는 표지 단위가 1,515로 집계되었다. 원문 없이 번역문만 들어 있던 문서 단위 3개에 원문을 복원한 판본이 이 제출본이며, 그 3개 단위가 차이를 만든다.

교차 보류 검증(OPENAI_API_KEY 필요, 모델 갱신에 따라 결과가 달라질 수 있음):

```bash
OPENAI_API_KEY=... python3 scripts/eval_loo.py --hold itongseol
OPENAI_API_KEY=... python3 scripts/eval_loo.py --hold kwonsinwon
```

2026년 7월 실행 로그는 `logs/`에 있다. 단위별 모델 출력은 보존되지 않았다.

## 5. 디렉터리 구조

```
data/
  nosa_units.json        # 색인 5,505단위 메타데이터와 원문 (번역문 없음)
  gold/                  # 수동 분할 정답 (번역문 제거판)
    itongseol_units.json
    answer_kwonsinwon_units.json
scripts/
  crawl_nosa.py 2_segment.py count_quotes.py eval_loo.py r2util.py
  sample_unattributed.py reproduce_counts.py
prompts/
  segmentation_SYSTEM.txt           # 분절 시스템 지시문
  nosa_cite_guard_rules.txt         # 운영 생성 규칙 원문 (2dfb874 이후)
  genre_policy.json                 # 문체별 분절 정책
  nosa_block.{before,after}.txt     # 생성 지시문(노사 config) 8/11 전·후 원문
  base_scholar_system_prompt.{before,after}.txt
  *.2dfb874.diff                    # 8/11 변경 diff
logs/
  loo_run_itongseol.txt  loo_run_kwonsinwon.txt
LICENSE-DATA  (CC BY 4.0)   LICENSE-CODE  (MIT)
```

`count_quotes.py`는 운영 환경(R2)에서 읽는 원본 스크립트이며, 로컬 재현에는 `reproduce_counts.py`를 쓴다. 운영 전체 코퍼스(번역문 포함)와 Pinecone 색인은 포함하지 않는다.

## 6. 인용

이시연 (2026). Nosa Ki Jeongjin AI: index data and scripts (KJDH-2026-010). GitHub: siyeon-gwr/nosa-kjdh-2026. Zenodo DOI는 첫 릴리스 후 추가한다.

## 7. 라이선스

- **데이터**(`data/`, `prompts/`의 분절 산출물): `LICENSE-DATA` — CC BY 4.0. 단, 한국고전번역원 원문·표점의 원권리는 ITKC에 있으며 그 정책을 함께 따른다. 번역문은 미포함.
- **코드**(`scripts/`): `LICENSE-CODE` — MIT.
