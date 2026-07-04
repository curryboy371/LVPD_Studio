---
name: word-memorize-batch
description: 단어 외우기(word_memorize) 콘텐츠용 단어를 표(탭 구분) 형태로 입력받아 words.xlsx에 추가하고, 이어서 resource/table/word_memorize_layouts/*.json 배치 파일까지 생성한다. 공통 한자 세트(레이저 타입, dian.json 계열), 같은 주제 세트(토픽 타입, animal.json 계열), 부품 한자 조합 세트(조합형, 조합_예시1.json 계열) 세 가지 모두 지원.
---

# 단어 외우기 배치(batch) 추가 스킬

사용자가 단어 목록(뜻·영어 뜻·한자·병음)을 표 형태로 주면, `words.xlsx`에 추가하고
바로 `word_memorize_layouts/*.json` 배치 파일까지 만들어준다. 두 단계 모두 이미 있는
프로젝트 도구를 그대로 재사용한다 (새 JSON을 손으로 작성하지 않는다).

## 0. 배치 타입 판단 (레이저 vs 토픽 vs 조합형)

`resource/table/word_memorize_layouts/`의 기존 파일은 세 계열로 나뉜다:

- **레이저 타입** — 공통 한자(부수/글자)를 공유하는 단어 묶음. 제목 없음,
  `selection_highlight`가 `laser_b/g/p/y`, 배경은 `mandala_*`/`mandara`.
  예: `dian.json`(店), `guan.json`(怀), `hao.json`(好), `lao.json`(老),
  `출.json`(出), `회.json`(回).
- **토픽 타입** — 같은 주제(동물/음식/음료/감정 등)로 묶은 단어 묶음. 제목·부제 있음,
  `selection_highlight`가 보통 `gradient`, 배경은 주제에 맞는 비디오, 구독/좋아요 CTA
  카드가 끝에 붙기도 함.
  예: `animal.json`, `drink.json`, `emotion.json`, `family.json`, `음식.json`.
- **조합형** — 부품 한자 2개(예: 书+店)가 합쳐져 결과 합성어(书店)가 되는 A–B1–B2–B3–A
  루프. `combo_layout: true`, 박스는 결과 합성어 3개뿐(부품은 words.xlsx의
  `component1_id`/`component2_id`로만 연결, 레이아웃 JSON엔 안 나옴).
  예: `조합_예시1.json`(书店/电灯/冰水). 만드는 절차는 아래 §4 참고 — 1·2단계와
  완전히 다른 전용 스크립트(`build_compose_layout.py`)를 쓴다.

사용자 요청에서 "공통 한자"·"~店/~回류" 같은 힌트가 있으면 레이저 타입, "주제로 묶어줘"·
"동물/음식 같은 거"면 토픽 타입, "부품이 합쳐져서~"·"조합"·"~+~=~" 같은 힌트면
조합형으로 판단한다. 애매하면 사용자에게 물어본다.

## 1. 단어 표 → `.words_add` 파일 작성

`tools/words_batch/template.words_add`의 형식을 따라 `tools/words_batch/<주제>.words_add`
파일을 만든다 (사용자가 준 표를 그대로 옮기면 됨):

```
@sheet 명사        ← words.xlsx 시트 (품사 카테고리: 명사/동사/형용사 등, template.words_add 참고)
@pos   명사        ← words.pos
@type  <종류>       ← 레이저 타입이면 공유 한자(예: dian, 출, 회) / 토픽 타입이면 주제명(예: 동물)

# meaning	en_meaning	word	pinyin
(흰)쌀밥	cooked rice	米饭	mǐfàn
...
```

열은 탭 구분, 순서 고정 (`meaning`, `en_meaning`, `word`, `pinyin`). 참고 파일:
`tools/words_batch/food_nouns.words_add`(토픽 예), `tools/words_batch/dian_nouns.words_add`(레이저 예).

## 2. words.xlsx 추가 + layout JSON 생성 (한 번에)

`tools/words_batch/build_layout.py`를 사용한다 — `add_words.py`로 단어를 추가한 뒤,
`--like`로 지정한 기존 배치 JSON을 스타일 템플릿으로 삼아 새 layout JSON을 만든다
(배경·하이라이트·타일·파티클·글꼴·CTA 카드 등을 그대로 복제하고 word box만 교체).

```bash
# 레이저 타입 예 — dian.json 스타일 그대로
python -m tools.words_batch.build_layout tools/words_batch/hui_compounds.words_add \
    --like resource/table/word_memorize_layouts/dian.json --name 회

# 토픽 타입 예 — animal.json 스타일 참고, 제목만 새로 지정, 10개만 사용(나머지는 CTA 2칸)
python -m tools.words_batch.build_layout tools/words_batch/food_nouns.words_add \
    --like resource/table/word_memorize_layouts/animal.json --name 음식 \
    --title "음식 이름을 외우자!" --limit 10
```

**항상 먼저 `--dry-run`으로 확인한 뒤 실제 실행한다** (words.xlsx 저장·layout JSON 저장 없이
콘솔에 결과 미리보기만 출력):

```bash
python -m tools.words_batch.build_layout tools/words_batch/<파일>.words_add \
    --like resource/table/word_memorize_layouts/<템플릿>.json --name <출력이름> --dry-run
```

### 주요 옵션

| 옵션 | 설명 |
|---|---|
| `--like PATH` (필수) | 스타일 템플릿 배치 JSON |
| `--name STEM` (필수) | 출력 파일명 (확장자 제외) → `resource/table/word_memorize_layouts/{STEM}.json` |
| `--limit N` | 배치에서 추가된 단어 중 앞 N개만 사용 (토픽 타입에서 CTA 카드 자리를 남기고 싶을 때) |
| `--title TEXT` | 제목 — 줄바꿈은 실제 개행 문자. 생략하면 템플릿 제목 유지 |
| `--subtitle TEXT` | 부제 — 줄바꿈은 실제 개행 문자. 각 줄은 템플릿의 `text_tile` 색을 순서대로 재사용 |
| `--no-cta` | 템플릿의 구독/좋아요 CTA 카드를 제외 |
| `--dry-run` | 미리보기만 (아무것도 저장 안 함) |
| `--force` / `--no-csv` / `--excel` | `add_words.py`와 동일 |

### word box 배치 규칙

- 새 단어 개수가 템플릿의 **일반 word box 개수(CTA 제외)와 같으면** → 템플릿의 x/y/w/h를
  그대로 복제한다 (가장 충실한 "참고"). 예: `dian.json`은 9개, `animal.json`은 CTA 2개를
  뺀 10개가 word box.
- 개수가 다르면 → 템플릿 box 크기를 참고해 자동으로 정사각형에 가까운 격자
  (`extra/table_editor/services/word_memorize_grid.py`의 `apply_grid_layout`)로 재배치한다.
- CTA 카드(구독/좋아요 등)는 `--no-cta`가 없는 한 항상 마지막에 그대로 유지된다.

## 3. 완료 후

- `python -m py_compile` 등 문법 검사는 스크립트 자체를 수정했을 때만 필요 (평소 사용 시 불필요).
- 저장 후 `resource/table/words.csv`도 함께 갱신된다 (`--no-csv` 없을 때).
- 생성된 layout JSON은 필요하면 테이블 편집기(`extra/table_editor`)의 word_memorize 배치
  화면에서 열어 미세 조정할 수 있다.

## 4. 조합형 — 부품 한자 세트 만들기

조합형은 1·2단계(레이저/토픽)와 완전히 다르게 진행한다. **결과 합성어와 부품
한자가 전부 words.xlsx에 이미 있어야** 하고, `build_compose_layout.py`는
"연결"과 layout 생성만 한다 (word_id 배치 X — 조합형은 박스 좌표를 안 쓴다).

### 4-1. 없는 단어 먼저 추가

결과 합성어(书店)와 부품 한자(书, 店)가 words.xlsx에 있는지 확인한다. 부품이
이미 다른 단어의 구성 요소로 존재하면(예: 电은 电脑에도 쓰임) 그대로 재사용 —
새로 안 만들어도 됨. 없는 것만 평소처럼 `.words_add` + `add_words.py`로 추가:

```
@sheet 명사
@pos   명사
@type  <아무 값>

# meaning	en_meaning	word	pinyin
서점	bookstore	书店	shūdiàn
책	book	书	shū
가게	shop	店	diàn
```
```bash
python -m tools.words_batch.add_words tools/words_batch/서점_단어.words_add
```

### 4-2. `.words_compose` 파일로 연결 + layout 생성

3열(탭 구분): `result  component1  component2` — 전부 한자 텍스트로 참조
(word_id 아님, 스크립트가 words.xlsx에서 찾아 연결한다):

```
# result	component1	component2
书店	书	店
电灯	电	灯
冰水	冰	水
```

```bash
# 먼저 --dry-run으로 확인 (저장 없이 콘솔에 layout JSON 미리보기)
python -m tools.words_batch.build_compose_layout tools/words_batch/서점세트.words_compose \
    --like resource/table/word_memorize_layouts/조합_예시1.json --name 조합_서점세트 --dry-run

# 문제없으면 실제 실행
python -m tools.words_batch.build_compose_layout tools/words_batch/서점세트.words_compose \
    --like resource/table/word_memorize_layouts/조합_예시1.json --name 조합_서점세트
```

한 세트는 정확히 3개 항목(B1/B2/B3). `--like`는 배경·색 등 스타일 템플릿용 —
지금은 `조합_예시1.json` 하나뿐이라 사실상 고정값. 결과 합성어·부품 중
words.xlsx에 없는 게 있으면 어떤 단어가 없는지 에러로 알려주니 4-1로 돌아가 추가한다.

### 4-3. 완료 후

- `component1_id`/`component2_id`는 결과 합성어 row에만 채워진다(부품 row 자체는 안 건드림).
- `resource/table/words.csv`도 함께 갱신됨(`--no-csv` 없을 때).
- 사운드·이모지 등 남은 리소스는 `조합형_need.md` 참고.

## layout JSON만 필요하고 words.xlsx 추가는 이미 끝난 경우

이미 추가된 단어의 id만으로 layout을 새로 짜고 싶으면 `tools/words_batch/build_layout.py`
대신 직접 `extra/table_editor/services/word_memorize_layout.py`의 `WordMemorizeLayout`,
`load_layout`/`save_layout`과 `word_memorize_grid.apply_grid_layout`을 사용한 짧은 스크립트를
그때그때 작성한다 (이 스킬의 2단계 코드가 그 사용 예시).
