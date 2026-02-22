"""
병음 변환 모듈. g2pM 기반 표기/발음 병음 및 성조 기호 변환.
테이블 생성 시 중국어 문장 → 병음(성조 기호) 변환에 사용.
"""
import re
from typing import Optional

try:
    from g2pM import G2pM
except ImportError:
    G2pM = None  # type: ignore[misc, assignment]


class PinyinProcessor:
    """중국어 문장을 표기/발음 병음 및 성조 기호 문자열로 변환하는 프로세서."""

    def __init__(self) -> None:
        self.g2p = G2pM() if G2pM else None
        self.tone_map = {
            "a": ["a", "ā", "á", "ǎ", "à"],
            "e": ["e", "ē", "é", "ě", "è"],
            "i": ["i", "ī", "í", "ǐ", "ì"],
            "o": ["o", "ō", "ó", "ǒ", "ò"],
            "u": ["u", "ū", "ú", "ǔ", "ù"],
            "v": ["ü", "ǖ", "ǘ", "ǚ", "ǜ"],
            "ü": ["ü", "ǖ", "ǘ", "ǚ", "ǜ"],
        }
        self.neutral_chars = {"呀", "哇", "吧", "呢", "嘛", "啦", "的", "了", "着", "过"}

    @property
    def available(self) -> bool:
        """g2pM 로드 여부."""
        return self.g2p is not None

    def _split_tone(self, p: str) -> tuple[str, Optional[float]]:
        """병음에서 기본 발음과 성조 숫자 분리 (예: 'hao3' -> 'hao', 3)."""
        if re.match(r"[a-z]+[0-5]", p):
            return p[:-1], float(p[-1])
        return p, None

    def tone3_to_mark(self, p: str) -> str:
        """숫자 병음을 성조 기호 병음으로 변환 (3.5는 3성 기호로 표기)."""
        base, tone = self._split_tone(p)
        if tone is None or tone in [0, 5]:
            return base.replace("v", "ü")

        display_tone = 3 if tone == 3.5 else int(tone)
        res = base.replace("v", "ü")
        for vowel in ["a", "e", "o"]:
            if vowel in res:
                return res.replace(vowel, self.tone_map[vowel][display_tone])
        if "iu" in res:
            return res.replace("u", self.tone_map["u"][display_tone])
        if "ui" in res:
            return res.replace("i", self.tone_map["i"][display_tone])
        for v in ["i", "u", "ü"]:
            if v in res:
                return res.replace(v, self.tone_map[v][display_tone])
        return res

    def get_lexical_pinyin(self, text: str) -> list[str]:
        """표기상 병음 (사전적 원래 발음, 숫자 포함)."""
        if not self.g2p:
            return []
        return [p for p in self.g2p(text) if p.strip()]

    def get_phonetic_pinyin(self, text: str) -> list[str]:
        """발음상 병음 (변조 및 반3성 3.5 적용)."""
        if not self.g2p:
            return []
        raw_pys = self.g2p(text)
        seq: list[dict] = []
        char_idx = 0
        for p in raw_pys:
            if not p.strip():
                continue
            char = text[char_idx]
            base, tone = self._split_tone(p)
            if tone is None:
                tone = 0
            seq.append({"char": char, "base": base, "tone": tone})
            char_idx += 1

        for item in seq:
            if item["char"] in self.neutral_chars:
                item["tone"] = 5

        for i in range(len(seq) - 1):
            if seq[i]["char"] == "不":
                seq[i]["tone"] = 2 if seq[i + 1]["tone"] == 4 else 4

        for i in range(len(seq) - 1):
            if seq[i]["char"] == "一":
                if seq[i + 1]["tone"] == 4:
                    seq[i]["tone"] = 2
                elif seq[i + 1]["tone"] in [1, 2, 3, 3.5]:
                    seq[i]["tone"] = 4

        for i in range(len(seq) - 2, -1, -1):
            if seq[i]["tone"] == 3:
                next_t = seq[i + 1]["tone"]
                if next_t == 3 or next_t == 2:
                    seq[i]["tone"] = 2
                elif next_t in [1, 2, 4, 5]:
                    seq[i]["tone"] = 3.5

        final_seq: list[str] = []
        for i, item in enumerate(seq):
            if item["char"] == "儿" and i > 0 and item["tone"] == 5:
                last = final_seq[-1]
                final_seq[-1] = last[:-1] + "r" + last[-1]
            else:
                t = item["tone"]
                if t is None:
                    t = 0
                tone_val = str(t) if t == 3.5 else str(int(t))
                final_seq.append(f"{item['base']}{tone_val}")

        return final_seq

    def full_convert(self, text: str) -> str:
        """한 글자씩 분석하여 성조 기호가 포함된 최종 문자열 반환."""
        if not self.g2p or not text.strip():
            return ""
        phonetic_list = self.get_phonetic_pinyin(text)
        return " ".join([self.tone3_to_mark(p) for p in phonetic_list])


# 싱글톤처럼 쓸 수 있는 기본 인스턴스 (지연 초기화 시 사용)
_default_processor: Optional[PinyinProcessor] = None


def get_pinyin_processor() -> PinyinProcessor:
    """PinyinProcessor 싱글톤 인스턴스를 반환한다."""
    global _default_processor
    if _default_processor is None:
        _default_processor = PinyinProcessor()
    return _default_processor


__all__ = ["PinyinProcessor", "get_pinyin_processor"]


if __name__ == "__main__":
    processor = get_pinyin_processor()
    if not processor.available:
        print("g2pM 미설치. pip install g2pM 후 실행하세요.")
    else:
        test_cases = [
            "我不去",
            "一斤",
            "你可以",
            "有点儿",
            "我很渴",
        ]
        print(f"{'원문':<10} | {'발음 숫자 표기':<20} | {'최종 성조 기호'}")
        print("-" * 60)
        for s in test_cases:
            phonetic = processor.get_phonetic_pinyin(s)
            marks = processor.full_convert(s)
            print(f"{s:<10} | {str(phonetic):<20} | {marks}")
