"""단어 외우기 TTS — TtsGenerateDialog 로 통합됨 (하위 호환 re-export)."""
from __future__ import annotations

from extra.table_editor.services.tts_voice_options import WordMemorizeTtsOptions
from extra.table_editor.ui.tts_generate_dialog import TtsGenerateDialog

__all__ = ["WordMemorizeTtsDialog", "WordMemorizeTtsOptions"]


class WordMemorizeTtsDialog:
    @classmethod
    def ask(
        cls,
        parent,
        *,
        initial_layout: str = "",
    ) -> WordMemorizeTtsOptions | None:
        result = TtsGenerateDialog.ask(
            parent,
            initial=initial_layout,
            initial_kind="word_memorize",
        )
        if result is None or result.kind != "word_memorize":
            return None
        return WordMemorizeTtsOptions.from_generate_result(result)
