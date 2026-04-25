# 슬롯(활용 문장) 가이드

슬롯은 **sub_sentences** 테이블로 관리합니다.  
base 문장 한 개에 대해, 특정 단어 위치(`target_slot_order`)를 다른 단어(`alt_word_id`)로 바꾼 “활용 문장”을 여러 개 둘 수 있습니다.

---

## 1. 3테이블 구조

- **base_sentences**: 원문·번역·미디어 + `base_words`(단어 순서)
- **words**: 단어 사전(`id, word, pos, meaning, img_path`)
- **sub_sentences**: `base_id + target_slot_order + alt_word_id + alt_translation + alt_sound_path`

---

## 2. 예시

base_sentences id=1:
- `raw_sentence`: `{苹果}{多少}{钱}？`
- `base_words`: `苹果|多少|钱`
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

## 3. 작업 순서

1. **base_sentences**에 `raw_sentence`, `base_words`, `translation` 입력
2. **words**에 대체 후보 단어를 등록
3. **sub_sentences**에 같은 `base_id`로 `target_slot_order`, `alt_word_id`, `alt_translation`, `alt_sound_path` 추가
4. 앱은 `base_words` + `sub_sentences`를 사용해 활용 문장을 만든다
