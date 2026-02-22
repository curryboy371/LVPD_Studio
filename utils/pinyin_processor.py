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

# 발음 변화 타입 테이블: UI에서 성조 아이콘 위에 노란색으로 표시할 라벨
# bu/yi는 뒤 음절 성조에 따라 2성·4성으로 세분화
SANDHI_TYPE_LABELS: dict[str, str] = {
    # 不: 4성 앞 → 2성 / 그 외 → 4성
    "bu_to_2": "* 不 (4성 앞 → 2성)",
    "bu_to_4": "* 不 (그 외 → 4성)",
    # 一: 4성 앞 → 2성 / 1·2·3성 앞 → 4성
    "yi_to_2": "* 一 (4성 앞 → 2성)",
    "yi_to_4": "* 一 (1·2·3성 앞 → 4성)",
    "tone3_2": "* 3성+3성 -> 2성+3성",
    "tone3_half": "* 반3성",
    "reduplication": "* 중첩(경성)",
    "neutral_char": "* 경성(어기)",
}


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
        """병음에서 기본 발음과 성조 숫자 분리 (예: 'hao3' -> 'hao', 3). 반3성 'guo3.5' 지원."""
        p = p.strip()
        m = re.match(r"^([a-züv]+)([0-5])(\.5)?$", p)
        if m:
            base, digit, half = m.group(1), m.group(2), m.group(3)
            tone = float(digit + (half or ""))
            return base, tone
        return p, None

    def _is_pinyin_syllable(self, s: str) -> bool:
        """유효한 병음 음절(영문+선택적 숫자)인지 여부. ?0 등 비병음 제외."""
        return bool(s and re.match(r"^[a-züv]+[0-5]?$", s) and not s.startswith("?"))

    def tone3_to_mark(self, p: str) -> str:
        """숫자 병음을 성조 기호 병음으로 변환 (3.5는 3성 기호로 표기)."""
        base, tone = self._split_tone(p)
        # 비병음(물음표 등) 뒤의 숫자 제거: ?0 -> ?
        if not self._is_pinyin_syllable(p):
            base = re.sub(r"[0-5]$", "", base)
            return base
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

    def _merge_orphan_tone_digits(self, raw_list: list[str]) -> list[str]:
        """g2pM이 'guo'와 '3'을 따로 줄 때, 성조 숫자만 있는 항목을 이전 음절에 붙임."""
        if not raw_list:
            return []
        out: list[str] = []
        for p in raw_list:
            p = p.strip()
            if not p:
                continue
            if re.match(r"^[0-5]$", p) and out:
                out[-1] = out[-1] + p
            else:
                out.append(p)
        return out

    def get_lexical_pinyin(self, text: str) -> list[str]:
        """표기상 병음 (사전적 원래 발음, 숫자 포함)."""
        if not self.g2p:
            return []
        raw = [p for p in self.g2p(text) if p.strip()]
        return self._merge_orphan_tone_digits(raw)

    def _get_phonetic_pinyin_and_types(self, text: str) -> tuple[list[str], list[Optional[str]]]:
        """발음상 병음 리스트와 음절별 성조변화 타입 리스트를 함께 반환. (내부 공용)"""
        if not self.g2p:
            return [], []
        raw_pys = self._merge_orphan_tone_digits([p for p in self.g2p(text) if p.strip()])
        seq: list[dict] = []
        char_idx = 0
        for p in raw_pys:
            if not p.strip():
                continue
            char = text[char_idx]
            base, tone = self._split_tone(p)
            if tone is None:
                tone = 0
            seq.append({"char": char, "base": base, "tone": tone, "sandhi_type": None})
            char_idx += 1

        for item in seq:
            if item["char"] in self.neutral_chars:
                item["tone"] = 5
                item["sandhi_type"] = "neutral_char"

        for i in range(len(seq) - 1):
            if seq[i]["char"] == "不":
                if seq[i + 1]["tone"] == 4:
                    seq[i]["tone"] = 2
                    seq[i]["sandhi_type"] = "bu_to_2"
                else:
                    seq[i]["tone"] = 4
                    seq[i]["sandhi_type"] = "bu_to_4"

        for i in range(len(seq) - 1):
            if seq[i]["char"] == "一":
                if seq[i + 1]["tone"] == 4:
                    seq[i]["tone"] = 2
                    seq[i]["sandhi_type"] = "yi_to_2"
                elif seq[i + 1]["tone"] in [1, 2, 3, 3.5]:
                    seq[i]["tone"] = 4
                    seq[i]["sandhi_type"] = "yi_to_4"

        # 중첩동사/중첩형: 같은 글자 연속이면 뒤 음절 발음을 경성(5)으로
        for i in range(len(seq) - 1):
            if seq[i]["char"] == seq[i + 1]["char"]:
                seq[i + 1]["tone"] = 5
                seq[i + 1]["sandhi_type"] = "reduplication"

        # 3성 변조: 3+3 → 앞을 2성으로 / 3+(1,2,4,5) → 앞을 반3성(3.5)으로
        for i in range(len(seq) - 2, -1, -1):
            if seq[i]["tone"] == 3:
                next_t = seq[i + 1]["tone"]
                if next_t == 3:
                    seq[i]["tone"] = 2  # 3+3: 앞 음절만 2성으로
                    seq[i]["sandhi_type"] = "tone3_2"
                elif next_t in [1, 2, 4, 5]:
                    seq[i]["tone"] = 3.5  # 3+그 외: 반3성 (少+钱 → shao3.5)
                    seq[i]["sandhi_type"] = "tone3_half"

        final_seq: list[str] = []
        sandhi_types: list[Optional[str]] = []
        for i, item in enumerate(seq):
            base = item["base"]
            if item["char"] == "儿" and i > 0 and item["tone"] == 5:
                last = final_seq[-1]
                final_seq[-1] = last[:-1] + "r" + last[-1]
            elif not self._is_pinyin_syllable(base):
                final_seq.append(re.sub(r"[0-5]$", "", base))
                sandhi_types.append(item.get("sandhi_type"))
            else:
                t = item["tone"]
                if t is None:
                    t = 0
                tone_val = str(t) if t == 3.5 else str(int(t))
                final_seq.append(f"{base}{tone_val}")
                sandhi_types.append(item.get("sandhi_type"))
        return final_seq, sandhi_types

    def get_phonetic_pinyin(self, text: str) -> list[str]:
        """발음상 병음 (변조 및 반3성 3.5 적용)."""
        syllables, _ = self._get_phonetic_pinyin_and_types(text)
        return syllables

    def get_sandhi_types(self, text: str) -> list[Optional[str]]:
        """음절별 성조 변화 타입 (get_phonetic_pinyin과 동일 순서/길이). 표시용 키: bu, yi, tone3_2, tone3_half, reduplication, neutral_char."""
        _, types = self._get_phonetic_pinyin_and_types(text)
        return types

    def full_convert(self, text: str) -> str:
        """표기상 병음을 성조 기호로 변환 (pinyin_marks용). 발음 변조 없음."""
        if not self.g2p or not text.strip():
            return ""
        lexical_list = self.get_lexical_pinyin(text)
        return " ".join([self.tone3_to_mark(p) for p in lexical_list])


# 싱글톤처럼 쓸 수 있는 기본 인스턴스 (지연 초기화 시 사용)
_default_processor: Optional[PinyinProcessor] = None


def get_pinyin_processor() -> PinyinProcessor:
    """PinyinProcessor 싱글톤 인스턴스를 반환한다."""
    global _default_processor
    if _default_processor is None:
        _default_processor = PinyinProcessor()
    return _default_processor


def parse_tone_from_syllable(syllable: str) -> Optional[float]:
    """병음 음절 문자열에서 성조 숫자만 추출. 예: 'guo3.5' -> 3.5, 'ni3' -> 3.0, 'ma1' -> 1.0."""
    if not syllable:
        return None
    s = syllable.strip()
    # 반3성 "3.5" 먼저 명시 처리 (끝이 3.5이면 3.5 반환)
    if re.search(r"3\.5$", s):
        return 3.5
    m = re.search(r"([0-5])(\.5)?$", s)
    if m:
        return float(m.group(1) + (m.group(2) or ""))
    return None


def diff_lexical_phonetic(lexical: str, phonetic: str) -> str:
    """pinyin_lexical과 pinyin_phonetic을 음절 단위로 비교해, 달라지는 음절만 발음형으로 반환.
    예: 'ping2 guo3 duo1 shao3 qian2' vs 'ping2 guo3.5 duo1 shao3.5 qian2' -> 'guo3.5 shao3.5'
    """
    if not lexical or not phonetic:
        return ""
    lex = lexical.strip().split()
    ph = phonetic.strip().split()
    out: list[str] = []
    for i, p in enumerate(ph):
        if i < len(lex) and lex[i] != p:
            out.append(p)
        elif i >= len(lex):
            out.append(p)
    return " ".join(out)


def diff_lexical_phonetic_per_syllable(lexical: str, phonetic: str) -> list[Optional[str]]:
    """음절 위치별로 lexical과 phonetic을 비교해, 달라지는 위치에는 발음(phonetic) 값을, 같으면 None 반환.
    pinyin_marks와 같은 길이로 쓸 수 있도록, marks 음절 수 기준으로 인덱스 맞춤.
    """
    if not lexical or not phonetic:
        return []
    lex = lexical.strip().split()
    ph = phonetic.strip().split()
    n = max(len(lex), len(ph))
    out: list[Optional[str]] = []
    for i in range(n):
        if i < len(lex) and i < len(ph) and lex[i] != ph[i]:
            out.append(ph[i])
        else:
            out.append(None)
    return out


__all__ = [
    "PinyinProcessor",
    "get_pinyin_processor",
    "parse_tone_from_syllable",
    "diff_lexical_phonetic",
    "diff_lexical_phonetic_per_syllable",
    "SANDHI_TYPE_LABELS",
]


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
