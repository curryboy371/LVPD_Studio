"""sub_sentences alt_word_id=0 슬롯 제거."""

from studio.conversation.data_loading import (
    ALT_WORD_ID_REMOVE_SLOT,
    _attach_sub_variants_to_base_rows,
    _is_alt_word_remove,
    _replace_multiple_slots_in_raw_sentence,
)


def test_remove_single_integer_slot():
    raw = "{苹果}{多少}{钱}？"
    out = _replace_multiple_slots_in_raw_sentence(
        raw,
        replacements=[(1, None)],
    )
    assert out == "苹果钱？"


def test_remove_and_replace_mixed():
    raw = "{我}{想}{剪}{张员瑛}{那样}{的}{发型}"
    out = _replace_multiple_slots_in_raw_sentence(
        raw,
        replacements=[(3, None), (4, "那样")],
    )
    assert "张员瑛" not in out
    assert "那样" in out
    assert "发型" in out


def test_attach_sub_variant_with_remove_id():
    base_rows = [
        {
            "id": 99,
            "raw_sentence": "{苹果}{多少}{钱}？",
        }
    ]
    words_by_id = {20501: "苹果", 20502: "多少"}
    sub_rows_by_base_id = {
        99: [
            {
                "target_slot_orders": [1],
                "alt_word_ids": [ALT_WORD_ID_REMOVE_SLOT],
                "alt_translation": "사과 얼마?",
                "alt_sound_path": "",
            }
        ],
    }
    _attach_sub_variants_to_base_rows(
        base_rows,
        words_by_id=words_by_id,
        maskings_by_id={},
        sub_rows_by_base_id=sub_rows_by_base_id,
    )
    variants = base_rows[0].get("sub_variants") or []
    assert len(variants) == 1
    assert variants[0]["replaced_sentence"] == "苹果钱？"
    assert _is_alt_word_remove(variants[0]["alt_word_ids"][0])
