# LVPD Table Editor

`resource/table` 엑셀을 그리드로 보고 편집·저장한 뒤, 기존 `tools.csv_gen` 규칙으로 CSV를 생성하는 데스크톱 도구입니다.

## 실행

프로젝트 루트에서:

```bat
run_table_editor.bat
```

또는:

```bat
python -m extra.table_editor
lvpd.bat editor
```

`lvpd.bat` 메인 메뉴에서 **E) 테이블 편집기** 도 동일합니다.

## 모드

### 단어 외우기 배치 (별도 창)

모드 영역 **단어 외우기 배치…** 버튼으로 9:16 미리보기(504×896) + 왼쪽 Word box 패널을 엽니다. 창은 **화면 중앙**에 열립니다.

- **추가 (검색)**: word id·한자 검색으로 캔버스에 바로 추가
- **단어장에서 가져오기…**: `words.xlsx` **시트·품사** 콤보로 목록 필터 → 더블클릭 또는 **가져오기**(Ctrl·Shift 복수 선택) → **보관함(미표시)**. **▼ 표시에 넣기** / **▲ 보관함으로** 로 캔버스·보관함 이동(목록 더블클릭도 동일). 저장 JSON에 `holding_word_ids` 포함.
- **Word box 미리보기** (위→아래): 병음(빨강) → 한자 → 영어 뜻 → 단어 이미지(`words.img_path`)
- **선택 삭제** / **선택한 크기로 전부 맞추기**: 선택 박스의 w×h를 나머지에 적용(위치 유지)
- **순서**: order·word id 지정, ▲▼로 재생 순서 변경
- **배경 설정**: 단색 또는 `resource` 기준 이미지 경로
- 박스는 FHD **1080×1920** 좌표로 저장·드래그 이동·가장자리 핸들로 크기 조절(프레임 밖·다른 박스와 겹침 불가)
- 미리보기 배경: 상·하단 여백 가이드(숏츠 zone의 **상 6% / 하 24%** 수준, 저장되지 않음)
- **저장/불러오기**: 상단 **새 배치** · **불러오기…** · **저장** · **다른 이름으로 저장…** → `resource/table/word_memorize_layouts/*.json` (단축키: Ctrl+O / Ctrl+S / Ctrl+Shift+S). 변경 후 저장 전에는 제목에 `*` 표시.
- **격자 정렬**: 행·열 입력 후 **격자 정렬** (order 순 1→2→3…) 또는 **균일하게 정렬**. 미리보기 **우측 여백 띠**에서 상·하 파란 핸들을 **드래그**해 배치 영역(가이드) 조절.

녹화·순차 하이라이트/TTS 재생은 이후 단계입니다.

### 메인 (빠른 작업)

`lvpd.bat` 메뉴와 동일한 작업을 버튼으로 실행합니다. **topic / set_id / word_id** 입력란은 TTS·F5 미리보기에 사용합니다.

- **데이터**: CSV 전체 생성
- **TTS**: 회화 sub KO / 단어장 KO / 숏츠 회화 / 숏츠 단어
- **에셋**: `resource/video` → MP3 추출, 한자 프레임(`--skip-existing`)
- **F5 debug**: 회화 / 단어장 / 숏츠 회화 / 숏츠 단어 화면 미리보기

실행 로그는 패널 오른쪽에 표시됩니다. 작업 중에는 다른 버튼이 잠시 비활성화됩니다.

### 단어장 (`words.xlsx`)

- **시트**: 엑셀 시트별로 데이터 표시 (다른 시트는 저장 시 유지).
- **pos**: `(전체)` 또는 시트 내 `pos` 값으로 필터.
- **검색** (Enter):
  - 숫자 → `id` 일치 행으로 이동.
  - 한자 → `word` 완전 일치. 여러 id면 선택 대화상자, 하나면 바로 이동.
- **더블클릭** / **새로 만들기**: 동일 편집 창. **새로 만들기**는 시트 id 구간 안 **비어 있는 최소 id**·pos 필터·TTS 기본(`edge` / `ko-KR-SunHiNeural`) 자동 입력. 시트별 id 구간은 `extra/table_editor/services/word_sheet_id_ranges.py` 참고.
- **새 단어** 편집에서 `word` 입력 후 **Enter**: `img_path`·`sound_path` = 한자, `masking` = 글자 수만큼 `0` (입력 `000` → 저장 `"000"`).
- **masking**: 편집창에는 `000`처럼 숫자만 보이고, 저장 시 엑셀/CSV에는 `"000"` 형태로 기록.
- **삭제**: 행 선택 후 **삭제** 버튼 또는 `Delete` 키. 확인 후 현재 시트에서 제거(저장 전까지 메모리만 변경).
- **tts_type** / **tts_voice**: 드롭다운 선택 (`edge` \| `gtts`, Edge 목소리 `ko-KR-SunHiNeural` \| `ko-KR-InJoonNeural`). `gtts`일 때 voice는 비움.
- **tip**: 줄마다 `[입력] [+] [-]` 한 줄. `+` 는 아래 줄 추가, `-` 는 해당 줄 삭제. 저장 시 `\\n` 으로 합침.
- **img_path**: **이미지 사용** / **이미지 미사용** — 미사용 시 `none`·입력·클립보드 비활성. 사용 시 `word`와 동일 stem·입력 가능. **클립보드 사용** 또는 미리보기 영역에 이미지 파일 **드래그 앤 드롭** 시 [rembg](https://github.com/danielgatis/rembg)로 배경 제거 → 1:1 정사각형(중앙·최대 cover)·투명 PNG 임시 저장 후 **저장** 시 `resource/image/word/{stem}.png` 반영 (Windows 드롭: `windnd`). 의존성: `pip install -r extra/table_editor/requirements.txt` (최초 실행 시 모델 다운로드로 시간이 걸릴 수 있음). 이미 투명 채널이 있는 PNG는 rembg를 건너뜀.

### 단어장 행 (`vocabulary_word_rows.xlsx`)

단어장 세션에 포함할 `(topic, word_id)` 목록입니다. 컬럼: `id`, `topic`, `word_id`, `desc`.
그리드에는 `words.xlsx` 기준 **한자·뜻·시트·품사**가 `word_id`로 조회되어 표시됩니다(읽기 전용).

- **topic**: `(전체)` 또는 표에 있는 topic 값으로 필터.
- **검색** (Enter):
  - 숫자 → `id` 일치 행으로 이동. 없으면 `word_id` 일치 행.
  - 문자열 → `topic` 완전 일치 시 해당 topic 필터 적용.
- **더블클릭** / **새로 만들기**: 행 편집. **새로 만들기**는 다음 `id`·현재 topic 필터를 자동 입력.
- **삭제**: 행 선택 후 **삭제** 버튼 또는 `Delete` 키.
- **저장** / **현재 탭 CSV**: `resource/csv/vocabulary_word_rows.csv` 생성 (`word_id` ≥ 1 행만 포함).

### 숏츠 단어 (`shorts_vocabulary_clips.xlsx`)

topic당 1행. `word_id`·단어별 옵션은 `+/−` 행. `hook_title`·`repeat`·`read_meaning_ko`는 topic 공통.

- **topic** 필터, **검색** (id / topic / word_id)
- **더블클릭** / **새로 만들기**: 전용 편집 창(기본·topic 인트로 / 단어·hook / 마무리). words 콤보·한자·뜻 미리보기, `ko_narration_id`·`bg_path` 콤보
- **캐시**: 최초 진입 시 words·ko sets 전역 캐시 (`warm_shorts_vocab_editor_cache`)

### 숏츠 회화 (`shorts_conversation_clips.xlsx`)

숏츠 회화 클립 정의: `base_id`, `hook_title`, `ko_narration_id`, `sub_sentence_id` 등.

- **topic**: `(전체)` 또는 표에 있는 topic 값으로 필터.
- **검색** (Enter):
  - 숫자 → `id` 일치 행으로 이동. 없으면 `base_id` 일치 행.
  - 문자열 → `topic` 완전 일치 시 해당 topic 필터 적용.
- **더블클릭** / **새로 만들기**: 전용 편집 창. **멘트·sub 매칭**: `base_id`·`ko_narration_id` 기준 콤보(+/− 행), 선택 시 KO `text`·sub 완성형 문장 미리보기. `topic`·`bg_path` 콤보. **새로 만들기**는 다음 `id`·현재 topic 필터를 자동 입력.
- **캐시**: 숏츠 회화 모드 최초 진입 시 `base`/`sub`/`ko_narration_lines`·완성문·콤보 목록을 전역 캐시에 적재(모드 전환 후에도 유지). 회화·TTS 탭에서 해당 xlsx 저장 시 캐시만 무효화.
- **삭제**: 행 선택 후 **삭제** 버튼 또는 `Delete` 키.
- **저장** / **현재 탭 CSV**: `resource/csv/shorts_conversation_clips.csv` 생성.

### 회화모드

- **topic**: `(전체)` 또는 base 시트의 `topic` 값으로 목록 필터.
- **위·아래 분할**: `base_sentences`(전체) / `sub_sentences`(선택한 base id의 `base_id`와 일치하는 행만).
- 처음에는 **sub** 영역이 숨겨지고, base 그리드에서 행을 **클릭**하면 아래에 sub가 나타납니다. 각 그리드는 세로·가로 스크롤.
- **base 열기** / **sub 열기**: 각각 별도 xlsx. 툴바 **저장**은 base·sub 모두 저장.
- **검색**: base id(숫자) — 선택 및 sub 필터 연동.
- **sub 새로 만들기**: base 선택 후 가능 (`base_id` 자동).
- **base raw_sentence**: 슬롯별 편집 (`단어` / `, ` / `?` / `？`). 미리보기 아래 **칸 그리드**에 슬롯마다 한자·`words.id` 표시(미등록 빨강, 중복 id 주황).
- **현재 탭 CSV** / **회화 전체 CSV**: base·sub CSV 동시 생성.

## 단축키

- 입력창: `Ctrl+C` / `Ctrl+V` / `Ctrl+X` / `Ctrl+A`
- 편집 창 저장: **저장** 버튼 (또는 `Ctrl+Enter`)

## 기본 경로

| 테이블 | 엑셀 | CSV |
|--------|------|-----|
| words | `resource/table/words.xlsx` | `resource/csv/words.csv` |
| vocabulary_word_rows | `resource/table/vocabulary_word_rows.xlsx` | `resource/csv/vocabulary_word_rows.csv` |
| shorts_conversation_clips | `resource/table/shorts_conversation_clips.xlsx` | `resource/csv/shorts_conversation_clips.csv` |
| shorts_vocabulary_clips | `resource/table/shorts_vocabulary_clips.xlsx` | `resource/csv/shorts_vocabulary_clips.csv` |
| base | `resource/table/base_sentences.xlsx` | `resource/csv/base_sentences.csv` |
| sub | `resource/table/sub_sentences.xlsx` | `resource/csv/sub_sentences.csv` |

CSV 보내기는 `python -m tools.csv_gen` / `lvpd.bat csv` 와 동일한 변환 함수를 호출합니다.

## 백업

파일을 **처음 저장**할 때 같은 폴더에 `*.xlsx.bak` 이 없으면 1회 복사합니다.

## 의존성

- Python 표준 `tkinter`
- `pandas`, `openpyxl`

설치 (프로젝트 루트):

```bat
py -3 -m pip install -r extra\table_editor\requirements.txt
```

전체 스튜디오 의존성은 루트 [`requirements.txt`](../../requirements.txt) 를 사용합니다.

한자 가독성이 낮으면 Windows에 CJK 폰트(예: Noto Sans CJK) 설치를 권장합니다.
