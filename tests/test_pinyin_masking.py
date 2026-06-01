"""words.csv 붙여 쓴 성조 병음 분리·표시."""

from utils.pinyin_masking import word_pinyin_to_marks, word_pinyin_to_marks_spaced


def test_concatenated_tone_marks_no_spurious_spaces():
    assert word_pinyin_to_marks("星期一", "xīngqīyī") == "xīngqīyī"
    assert word_pinyin_to_marks("今天", "jīntiān") == "jīntiān"
    assert word_pinyin_to_marks("明天", "míngtiān") == "míngtiān"
    assert word_pinyin_to_marks("可乐", "kělè") == "kělè"


def test_spaced_tone_marks_keep_syllable_gaps():
    assert word_pinyin_to_marks("星期一", "xīng qī yī") == "xīng qī yī"


def test_spaced_display_splits_by_hanzi():
    assert word_pinyin_to_marks_spaced("星期一", "xīngqīyī") == "xīng qī yī"
    assert word_pinyin_to_marks_spaced("今天", "jīntiān") == "jīn tiān"
    assert word_pinyin_to_marks_spaced("月", "yuè") == "yuè"
