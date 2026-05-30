"""sub_sentences main_slot → main word 이미지 메타."""

from studio.conversation.data_loading import _attach_sub_variants_to_base_rows
from studio.conversation.slot_replacement import resolve_main_word_id


def test_resolve_main_word_id_by_slot():
    wid = resolve_main_word_id(
        main_slot="0.1",
        slot_orders=[0, 0.1, 0.2],
        alt_word_ids=[20501, 1000, 2021],
        fallback_word_id=20501,
    )
    assert wid == 1000


def test_resolve_main_word_id_fallback():
    wid = resolve_main_word_id(
        main_slot="",
        slot_orders=[0],
        alt_word_ids=[20504],
        fallback_word_id=20504,
    )
    assert wid == 20504


def test_attach_sub_variant_main_word_meta():
    base_rows = [{"id": 1, "raw_sentence": "{苹果}{多少}{钱}？"}]
    words_by_id = {20501: "苹果", 20504: "芒果", 1000: "一"}
    sub_rows_by_base_id = {
        1: [
            {
                "target_slot_orders": [0, 0.1],
                "alt_word_ids": [20504, 1000],
                "main_slot": "0.1",
                "alt_translation": "망고 한 근?",
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
    assert variants[0]["main_word_id"] == 1000
