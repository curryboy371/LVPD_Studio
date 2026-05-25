from pathlib import Path

from core.paths import get_repo_root, resolve_conversation_sub_cn_sound_path


def test_resolve_stem_under_sentense_dir():
    resolved = resolve_conversation_sub_cn_sound_path("你好,请给我一个叉子")
    assert resolved is not None
    assert resolved.is_file()
    assert resolved.parent == get_repo_root() / "resource" / "sound" / "sentense"
    assert resolved.name == "你好,请给我一个叉子.mp3"


def test_resolve_full_repo_relative_path():
    resolved = resolve_conversation_sub_cn_sound_path(
        "resource/sound/sentense/不要香菜.mp3"
    )
    assert resolved is not None
    assert resolved.name == "不要香菜.mp3"


def test_resolve_filename_with_ext_in_sentense_dir():
    resolved = resolve_conversation_sub_cn_sound_path("不要醋.mp3")
    assert resolved is not None
    assert resolved.name == "不要醋.mp3"
