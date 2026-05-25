"""words.csv pinyin이 sub 문장 병음에 반영되는지."""

from studio.conversation.data_loading import (
    _attach_sub_variants_to_base_rows,
    _build_masked_pinyin_for_sentence,
)


def test_word_pinyin_overrides_g2pm_in_sub_sentence():
    raw = "{老板},{请}{给}{我}{冰水}"
    display = "老板,请给我一瓶可乐"
    words_by_id = {20150: "可乐"}
    pinyins_by_id = {20150: "kělè"}
    marks, _, _ = _build_masked_pinyin_for_sentence(
        display,
        raw,
        words_by_id=words_by_id,
        maskings_by_id={},
        pinyins_by_id=pinyins_by_id,
        replacement_pinyin_pairs=[("可乐", "kělè")],
    )
    assert "yuè" not in marks
    assert "lè" in marks


def test_attach_sub_variant_uses_word_pinyin():
    base_rows = [{"id": 16, "raw_sentence": "{老板},{请}{给}{我}{冰水}"}]
    words_by_id = {
        20018: "老板",
        1000: "一",
        2025: "瓶",
        20150: "可乐",
    }
    pinyins_by_id = {20150: "kělè"}
    sub_rows_by_base_id = {
        16: [
            {
                "target_slot_orders": [0, 3.1, 3.2, 4],
                "alt_word_ids": [20018, 1000, 2025, 20150],
                "alt_translation": "사장님, 콜라 한 병 주세요",
                "alt_sound_path": "",
            }
        ],
    }
    _attach_sub_variants_to_base_rows(
        base_rows,
        words_by_id=words_by_id,
        maskings_by_id={},
        pinyins_by_id=pinyins_by_id,
        sub_rows_by_base_id=sub_rows_by_base_id,
    )
    variant = (base_rows[0].get("sub_variants") or [])[0]
    marks = str(variant.get("pinyin_marks") or "")
    assert variant["replaced_sentence"] == "老板,请给我一瓶可乐"
    assert "yuè" not in marks
    assert "lè" in marks
