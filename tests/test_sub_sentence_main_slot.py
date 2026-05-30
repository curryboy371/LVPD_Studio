"""sub_sentences main_slot → main word 이미지 메타."""

from unittest.mock import MagicMock, patch

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
    mock_word = MagicMock()
    mock_word.word = "一"
    mock_word.pinyin = "yī"
    mock_word.meaning = "일|하나"
    mock_word.img_path = ""
    with patch("data.table_manager.get_word", return_value=mock_word):
        _attach_sub_variants_to_base_rows(
            base_rows,
            words_by_id=words_by_id,
            maskings_by_id={},
            sub_rows_by_base_id=sub_rows_by_base_id,
        )
    variants = base_rows[0].get("sub_variants") or []
    assert len(variants) == 1
    assert variants[0]["main_word_id"] == 1000
    assert variants[0]["main_word_hanzi"] == "一"
    assert variants[0]["main_word_pinyin"] == "yī"
    assert variants[0]["main_word_meaning"] == "일"


def test_attach_sub_variant_main_word_pinyin_auto_when_csv_empty():
    base_rows = [{"id": 1, "raw_sentence": "{苹果}"}]
    words_by_id = {20501: "苹果"}
    sub_rows_by_base_id = {
        1: [
            {
                "target_slot_orders": [0],
                "alt_word_ids": [20501],
                "main_slot": "0",
                "alt_translation": "test",
                "alt_sound_path": "",
            }
        ],
    }
    mock_word = MagicMock()
    mock_word.word = "苹果"
    mock_word.pinyin = ""
    mock_word.masking = ""
    mock_word.meaning = "사과"
    mock_word.img_path = ""
    with patch("data.table_manager.get_word", return_value=mock_word):
        with patch(
            "studio.conversation.data_loading.get_pinyin_processor"
        ) as mock_pp_fn:
            mock_pp = MagicMock()
            mock_pp.available = True
            mock_pp.full_convert.return_value = "píng guǒ"
            mock_pp_fn.return_value = mock_pp
            _attach_sub_variants_to_base_rows(
                base_rows,
                words_by_id=words_by_id,
                maskings_by_id={},
                sub_rows_by_base_id=sub_rows_by_base_id,
            )
    variants = base_rows[0].get("sub_variants") or []
    assert variants[0]["main_word_pinyin"] == "píng guǒ"
    mock_pp.full_convert.assert_called_once_with("苹果")
