from utils.media_stem import media_path_stem


def test_media_path_stem_strips_punctuation_and_spaces():
    assert media_path_stem("你好,请给我一个叉子") == "你好请给我一个叉子"
    assert media_path_stem("苹果多少钱？") == "苹果多少钱"
    assert media_path_stem("  不要 醋 , ?  ") == "不要醋"
