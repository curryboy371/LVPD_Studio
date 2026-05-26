# LVPD Studio TODO

프로젝트 작업 목록. 완료 시 `[x]`로 표시합니다.

---

## 쇼츠 회화 모드

- [ ] **한국어 TTS**
  - 회화 클립용 한국어 나레이션 TTS 생성·연동
  - 관련: `ko_narration_sets` / `ko_narration_lines`, `audio/ko_narration.py`, `batch_tts.bat`

- [ ] **구독 유도**
  - 회화 모드 영상 내 구독 유도(CTA) 장면·자막·타이밍

- [ ] **이미지 — `sub_sentences` `main_id` 컬럼**
  - `sub_sentences` 테이블에 `main_id` 컬럼 추가
  - 회화 모드 이미지 매핑·로딩 로직 반영 (`data_loading`, `clip_scene` 등)

---

## 인프라

- [ ] **테이블 자동화**
  - 엑셀 ↔ CSV 변환·검증·일괄 생성 파이프라인 정리·확장
  - 관련: `tools/csv_gen`, `lvpd.bat csv`, `docs/table_structure.md`
