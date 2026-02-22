"""
CSV 또는 엑셀(table/video)을 읽어 영상 소스 모델(VideoSegment, OverlayItem, AudioTrack) 리스트로 반환하는 로더.
video_list 형식: topic, id, index, sentence, pinyin_mask, pron_mask, translation, split_ms, tip

- .csv → csv.DictReader로 직접 읽기
- .xlsx / .xls → pandas로 읽은 뒤 동일한 행 딕셔너리로 변환해 처리

최종 테이블 생성: generate_final_table() — 입력 CSV → sentence 정제, words/life_tips 추출, 병음 3종 저장.
"""
import ast
import csv
import logging
import re
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from data.models import (
    AudioTrack,
    LoadedContent,
    OverlayItem,
    VideoSegment,
)
from utils.pinyin_processor import get_pinyin_processor

EXCEL_EXTENSIONS = (".xlsx", ".xls")


def _to_float(val: Any, default: float = 0.0, as_sec: bool = False) -> float:
    """값을 float으로 변환. as_sec이 True이고 값이 1000 초과면 ms로 간주해 초로 변환."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    if as_sec and x > 1000:
        x = x / 1000.0
    return max(0.0, x)


def _to_int(val: Any, default: int = 0) -> int:
    """값을 int로 변환."""
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _safe_literal_eval(val: Any, default: list | dict) -> list | dict:
    """문자열을 ast.literal_eval로 파싱. 실패 시 default 반환."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    s = val.strip().strip('"') if isinstance(val, str) else val
    try:
        return ast.literal_eval(s)  # type: ignore[return-value]
    except (ValueError, SyntaxError):
        return default


def _excel_cell_to_str(val: Any) -> str:
    """엑셀 셀 값을 문자열로. NaN/None은 빈 문자열."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _iter_rows_from_path(path: Path, encoding: str = "utf-8-sig") -> Iterator[dict[str, Any]]:
    """경로가 CSV면 DictReader로, 엑셀(.xlsx/.xls)이면 pandas로 읽어 행 딕셔너리를 yield한다."""
    suffix = path.suffix.lower()
    if suffix in EXCEL_EXTENSIONS:
        df = pd.read_excel(path).dropna(axis=1, how="all")
        cols = [str(c).strip() for c in df.columns]
        for _, r in df.iterrows():
            yield {cols[i]: _excel_cell_to_str(r.iloc[i]) for i in range(len(cols))}
        return
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)


def load_content_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> LoadedContent:
    """CSV 또는 엑셀(table/video) 파일을 읽어 VideoSegment, OverlayItem, AudioTrack 리스트를 담은 LoadedContent를 반환한다.
    비디오 경로는 테이블에 resource/... 형태로 있으면 repo 루트 기준 해석. video_path 없으면 resource/video/{topic}/{id}.mp4 로 조합.
    """
    from core.paths import get_repo_root

    path = Path(csv_path)
    if not path.exists():
        return LoadedContent()

    repo = get_repo_root()
    video_segments: list[VideoSegment] = []
    overlay_items: list[OverlayItem] = []
    audio_tracks: list[AudioTrack] = []

    for row in _iter_rows_from_path(path, encoding):
        try:
            topic = (row.get("topic") or "").strip().strip('"')
            row_id = row.get("id", "").strip().strip('"')
            if not topic or not row_id:
                continue

            # 리스트/딕셔너리 컬럼 파싱 (video_list 형식)
            sentence = _safe_literal_eval(row.get("sentence"), [])
            translation = _safe_literal_eval(row.get("translation"), [])
            split_ms = _to_int(row.get("split_ms", 0), 0)
            _ = _safe_literal_eval(row.get("pinyin_mask"), [])  # 필요 시 활용
            _ = _safe_literal_eval(row.get("pron_mask"), [])
            _ = _safe_literal_eval(row.get("tip"), {})

            # VideoSegment: 테이블 video_path(resource/...) 또는 resource/video/topic/id.mp4
            vpath = str(row.get("video_path") or "").strip()
            if not vpath:
                vpath = str(Path("resource", "video", topic, f"{row_id}.mp4"))
            if not Path(vpath).is_absolute():
                vpath = str(repo / vpath)
            end_sec = _to_float(split_ms, default=0.0, as_sec=True) if split_ms else 0.0
            video_segments.append(
                VideoSegment(
                    file_path=vpath,
                    start_time=0.0,
                    end_time=end_sec,
                    volume=_to_float(row.get("volume", 1.0), default=1.0),
                )
            )

            # OverlayItem: sentence / translation / pinyin 종류별
            sen_str = str(sentence[0]).strip() if isinstance(sentence, list) and sentence else ""
            trans_str = str(translation[0]).strip() if isinstance(translation, list) and translation else ""
            text = trans_str or sen_str  # 하위 호환용

            pinyin_str = None
            if sen_str:
                try:
                    processor = get_pinyin_processor()
                    if processor.available:
                        pinyin_str = processor.full_convert(sen_str) or None
                except Exception as e:
                    logging.debug("Pinyin conversion skipped for row id=%s: %s", row.get("id"), e)

            overlay_items.append(
                OverlayItem(
                    sentence=sen_str or None,
                    translation=trans_str or None,
                    pinyin=pinyin_str,
                    text=text,
                    font_name=(row.get("font_name") or "").strip() or None,
                    font_size=_to_int(row.get("font_size", 24), 24),
                    position_x=_to_float(row.get("position_x", 0)),
                    position_y=_to_float(row.get("position_y", 0)),
                    image_path=(row.get("image_path") or "").strip() or None,
                )
            )

            # AudioTrack: resource/... 경로면 repo 기준 해석
            spath = (row.get("sound_path") or "").strip()
            if spath:
                if not Path(spath).is_absolute():
                    spath = str(repo / spath)
                audio_tracks.append(
                    AudioTrack(
                        sound_path=spath,
                        fade_in_sec=_to_float(row.get("fade_in_sec", 0)),
                        fade_out_sec=_to_float(row.get("fade_out_sec", 0)),
                    )
                )
        except Exception as e:
            logging.warning("CSV row parse error (id=%s): %s", row.get("id"), e)

    return LoadedContent(
        video_segments=video_segments,
        overlay_items=overlay_items,
        audio_tracks=audio_tracks,
    )


def generate_final_table(
    input_path: str | Path,
    output_csv: str | Path,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """입력 CSV 또는 엑셀을 읽어 sentence 정제, words/life_tips 추출, 병음 3종 생성 후 최종 CSV로 저장.

    - 입력: .csv 또는 .xlsx/.xls (엑셀 원본 사용 시 여기서 CSV 생성)
    - sentence: `{}` 제거한 정제 문장
    - words: `{}` 안의 단어만 추출 (저장 시 `|` 구분)
    - life_tips: life_tip 컬럼을 `|` 기준으로 분리 (저장 시 `|` 구분)
    - 병음 3종 (PinyinProcessor): pinyin_marks, pinyin_phonetic, pinyin_lexical

    입력 예상 컬럼: topic, id, level, sentence, translation, life_tip,
    start_ms, end_ms, video_path, sound_level1_path, sound_level2_path
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {input_path}")

    if path.suffix.lower() in EXCEL_EXTENSIONS:
        df = pd.read_excel(path).dropna(axis=1, how="all")
    else:
        df = pd.read_csv(path, encoding=encoding).dropna(axis=1, how="all")
    processor = get_pinyin_processor()
    final_rows = []

    for _, row in df.iterrows():
        raw_sent = str(row.get("sentence", ""))
        clean_sentence = re.sub(r"\{|\}", "", raw_sent)
        words_list = re.findall(r"\{(.*?)\}", raw_sent)

        raw_tip = str(row.get("life_tip", "")) if pd.notna(row.get("life_tip")) else ""
        tips_list = [t.strip() for t in raw_tip.split("|") if t.strip()] if raw_tip else []

        # 병음 3종 (g2pM 없으면 빈 문자열)
        # 1) 표기병음: 숫자 없이 성조만 기호로 표시 (예: nǐ hǎo)
        # 2) 표기병음숫자용: 성조 기호 없이, 뒤에 표기 성조 숫자 (예: ni3 hao3)
        # 3) 발음용병음: 성조 기호 없이, 뒤에 실제 발음(변조 반영) 성조 숫자 (예: 반3성 등)
        pinyin_marks = ""      # 1) 표기병음 (성조 기호)
        pinyin_lexical = ""    # 2) 표기병음숫자용
        pinyin_phonetic = ""   # 3) 발음용병음
        if clean_sentence and processor.available:
            try:
                pinyin_marks = processor.full_convert(clean_sentence) or ""
                pinyin_lexical = " ".join(processor.get_lexical_pinyin(clean_sentence))
                pinyin_phonetic = " ".join(processor.get_phonetic_pinyin(clean_sentence))
            except Exception as e:
                logging.error("Pinyin conversion skipped for row: %s", e)

        def _r(key: str, default: Any = ""):
            v = row.get(key, default)
            return v if pd.notna(v) else default

        final_rows.append({
            "topic": _r("topic"),
            "id": _r("id"),
            "level": _r("level"),
            "sentence": clean_sentence,
            "pinyin_marks": pinyin_marks,
            "pinyin_phonetic": pinyin_phonetic,
            "pinyin_lexical": pinyin_lexical,
            "translation": _r("translation"),
            "words": "|".join(words_list),
            "start_ms": _r("start_ms"),
            "end_ms": _r("end_ms"),
            "video_path": _r("video_path"),
            "sound_l1": _r("sound_level1_path"),
            "sound_l2": _r("sound_level2_path"),
            "life_tips": "|".join(tips_list),
        })

    result_df = pd.DataFrame(final_rows)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(out_path, index=False, encoding=encoding)
    logging.info("최종 테이블 저장: %s (%d행)", output_csv, len(result_df))

    # 데이터 관리 모듈에 저장 → 재생 시 여기서 로드
    from data.table_manager import set_table
    set_table(result_df)

    return result_df


def ensure_video_data_csv(
    csv_path: str | Path,
    excel_path: str | Path,
) -> str | None:
    """엑셀에서 CSV를 무조건 생성한다. 엑셀이 있으면 생성 후 csv_path 반환, 없으면 None."""
    csv_path = Path(csv_path)
    excel_path = Path(excel_path)
    if not excel_path.exists():
        return None
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("엑셀 → CSV 생성: %s → %s", excel_path, csv_path)
    generate_final_table(str(excel_path), str(csv_path))
    return str(csv_path)


class CSVProcessor:
    """CSV 파일에서 LoadedContent를 읽어오는 프로세서. 경로는 테이블의 resource/... 를 repo 기준으로 해석."""

    def __init__(self, encoding: str = "utf-8-sig") -> None:
        self.encoding = encoding

    def load(self, csv_path: str | Path) -> LoadedContent:
        """CSV 경로를 받아 LoadedContent를 반환한다."""
        return load_content_from_csv(csv_path, encoding=self.encoding)
