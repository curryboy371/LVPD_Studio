# 슬롯(활용 문장) 가이드

슬롯은 **sub_sentences** 테이블로 관리합니다.  
base 문장 한 개에 대해, 특정 단어 위치(target_slot_order)를 다른 단어(alt_word_id)로 바꾼 “활용 문장”을 여러 개 둘 수 있습니다.

---

## 1. 테이블 구조

- **base_sentences**: 원문·번역·미디어 (한 행당 문장 1개)
- **sentence_word_map**: 그 문장의 단어 순서 (slot_order 0, 1, 2, …)
- **sub_sentences**: base_id + target_slot_order + alt_word_id + alt_translation (+ alt_sound_path)

---

## 2. 예시

base_sentences id=101: `苹果多少钱？` / `사과 얼마예요?`  
words: 501=苹果, 502=多少, 503=钱, 504=芒果, 505=수박  
sentence_word_map: (101, 501, 0), (101, 502, 1), (101, 503, 2)

sub_sentences:

| id | base_id | target_slot_order | alt_word_id | alt_translation |
|----|---------|-------------------|-------------|-----------------|
| 1  | 101     | 0                 | 504         | 망고는 얼마예요? |
| 2  | 101     | 0                 | 505         | 수박은 얼마예요? |

→ 재생: base 1개(苹果多少钱？) + 활용 2개(芒果多少钱？, 西瓜多少钱？) — 각각 alt_translation 표시.

---

## 3. 작업 순서

1. **base_sentences / words / sentence_word_map**: 원문·단어·순서 정의
2. **sub_sentences**: 같은 base_id에 대해 target_slot_order, alt_word_id, alt_translation 추가
3. 앱은 `get_sub_sentences_for_base(base_id)` 로 활용 목록을 가져와 Step 2 등에서 표시
