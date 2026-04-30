# 슬롯(활용 문장) 가이드

슬롯은 **sub_sentences** 테이블로 관리합니다.  
base 문장 한 개에 대해, 특정 단어 위치(`target_slot_order`)를 다른 단어(`alt_word_id`)로 바꾼 “활용 문장”을 여러 개 둘 수 있습니다.
이제 한 행에서 **여러 치환**을 동시에 지정할 수 있습니다.

---

## 1. 3테이블 구조

- **base_sentences**: 원문·번역·미디어
- **words**: 단어 사전(`id, word, pos, meaning, img_path`)
- **sub_sentences**: `base_id + target_slot_order + alt_word_id + alt_translation + alt_sound_path`

---

## 2. 예시

base_sentences id=1:
- `raw_sentence`: `{苹果}{多少}{钱}？`
- 단어 순서는 `raw_sentence`의 `{}` 슬롯 순서를 그대로 사용
- `translation`: `사과 얼마예요?`

words:
- `501=苹果`, `504=芒果`, `505=西瓜`

sub_sentences:

| id | base_id | target_slot_order | alt_word_id | alt_translation | alt_sound_path |
|----|---------|-------------------|-------------|-----------------|----------------|
| 1  | 1       | 0                 | 504         | 망고는 얼마예요? | resource/sound/fruit_store/1_sub_1.mp3 |
| 2  | 1       | 0                 | 505         | 수박은 얼마예요? | resource/sound/fruit_store/1_sub_2.mp3 |

→ 재생: base 1개(苹果多少钱？) + 활용 2개(芒果多少钱？, 西瓜多少钱？) — 각각 alt_translation 표시.

---

## 3. 다중 치환 / 문장 앞뒤 삽입

`target_slot_order`, `alt_word_id`의 다중 값 구분자는 파이프(`|`)를 사용합니다.

- 기본 슬롯 치환(0부터 시작):
  - `target_slot_order=0|1`
  - `alt_word_id=501|502`
  - 의미: 0번 슬롯에는 501, 1번 슬롯에는 502를 적용

- 문장 앞 삽입:
  - `target_slot_order=-1`
  - 의미: 대체 단어를 문장 맨앞에 붙임

- 문장 끝 삽입:
  - `target_slot_order=맨끝` (또는 `end`, `last`)
  - 의미: 대체 단어를 문장 맨끝에 붙임

### 다중 매핑 규칙

- 두 컬럼 길이가 같으면 1:1로 순서 매핑
- 한쪽만 1개이고 다른 쪽이 여러 개면 1개를 반복 적용
- 둘 다 여러 개인데 길이가 다르면 짧은 쪽 길이에 맞춰 앞에서부터 매핑

예시:

| id | base_id | target_slot_order | alt_word_id | alt_translation |
|----|---------|-------------------|-------------|-----------------|
| 10 | 1       | 0\|1              | 501\|502    | 예시 A |
| 11 | 1       | -1                | 503         | 예시 B |
| 12 | 1       | 0\|맨끝           | 504\|505    | 예시 C |

---

## 4. 작업 순서

1. **base_sentences**에 `raw_sentence`, `translation` 입력
2. **words**에 대체 후보 단어를 등록
3. **sub_sentences**에 같은 `base_id`로 `target_slot_order`, `alt_word_id`, `alt_translation`, `alt_sound_path` 추가
4. 앱은 `raw_sentence` 슬롯 + `sub_sentences`를 사용해 활용 문장을 만든다
