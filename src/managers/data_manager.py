import pandas as pd
import json
import os
import sys
import csv
import ast
import logging

class DataManager:
    def __init__(self):
        # 경로 설정 (src/manager/data_manager.py 기준)
        self.CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.PROJECT_ROOT = os.path.normpath(os.path.join(self.CURRENT_FILE_DIR, "..", ".."))
        
        self.RESOURCE_DIR = os.path.join(self.PROJECT_ROOT, "resource")
        self.TABLE_DIR = os.path.join(self.RESOURCE_DIR, "table")
        self.CSV_DIR = os.path.join(self.RESOURCE_DIR, "csv")
        self.VIDEO_ROOT = os.path.join(self.RESOURCE_DIR, "video")
        
        # 출력 파일명 설정 (기존 video_data.csv)
        self.output_file = os.path.join(self.CSV_DIR, "video_data.csv")
        
        # 데이터 저장소
        self.video_data_list = []

    # --- [1] Generation 영역: 엑셀 -> CSV ---
    def generate_csv(self, excel_filename="video_data.xlsx"):
        input_path = os.path.join(self.TABLE_DIR, excel_filename)

        if not os.path.exists(input_path):
            print(f"❌ 오류: '{input_path}' 파일을 찾을 수 없습니다.")
            return

        print(f"🔄 '{excel_filename}' 로드 중... CSV 변환을 시작합니다.")

        try:
            # 엑셀 로드 시 숫자 앞 0 유지를 위해 dtype=str
            df = pd.read_excel(input_path, dtype=str)
        except Exception as e:
            print(f"❌ 파일 로드 중 오류 발생: {e}")
            return

        def process_row(row):
            def combine_to_list_str(prefix):
                items = []
                for i in range(1, 10):
                    col_name = f"{prefix}{i}"
                    if col_name in row and pd.notna(row[col_name]):
                        items.append(str(row[col_name]).strip())
                    else: break
                return json.dumps(items, ensure_ascii=False)

            tip_dict = {}
            mapping = {'word_tip': 'word', 'tone_tip': 'tone', 'expr_tip': 'expr', 'life_tip': 'life'}
            for excel_col, json_key in mapping.items():
                if excel_col in row and pd.notna(row[excel_col]):
                    val = row[excel_col]
                    parts = [p.strip() for p in val.split('|') if p.strip()] if isinstance(val, str) else [str(val)]
                    if parts: tip_dict[json_key] = parts

            return pd.Series({
                'sentence': combine_to_list_str('sentence'),
                'pinyin_mask': combine_to_list_str('pinyin_mask'),
                'pron_mask': combine_to_list_str('pron_mask'),
                'translation': combine_to_list_str('translation'),
                'tip_json': json.dumps(tip_dict, ensure_ascii=False)
            })

        new_data = df.apply(process_row, axis=1)
        
        final_df = pd.DataFrame()
        final_df['topic'] = df['topic'] if 'topic' in df.columns else "default_topic"
        final_df['id'] = df['id']
        final_df['index'] = range(len(df))
        final_df['sentence'] = new_data['sentence']
        final_df['pinyin_mask'] = new_data['pinyin_mask']
        final_df['pron_mask'] = new_data['pron_mask']
        final_df['translation'] = new_data['translation']
        final_df['split_ms'] = df['split_ms'].fillna(0)
        final_df['tip'] = new_data['tip_json']

        if not os.path.exists(self.CSV_DIR):
            os.makedirs(self.CSV_DIR)
            
        final_df.to_csv(self.output_file, index=False, encoding='utf-8-sig', quoting=1)
        print(f"✅ 성공: {self.output_file} 생성 완료.")

    # --- [2] Load 영역: CSV -> 메모리(객체) ---
    def load_video_data(self, target_topic=None):
        """저장된 CSV를 읽어와서 파이썬 객체 리스트로 반환"""
        self.video_data_list = []
        path = self.output_file

        if not os.path.exists(path):
            print(f"❌ 파일이 없습니다: {path}")
            return []

        print(f"📂 데이터 로딩 시작: {path}")

        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    topic = row.get("topic", "").strip()
                    
                    # 토픽 필터링 (target_topic이 지정된 경우에만)
                    if target_topic and topic != target_topic:
                        continue
                    
                    v_id = row.get("id", "0").strip()
                    
                    # [핵심] 비디오 경로 규칙 생성: resource/video/{topic}/{id}.mp4
                    video_path = os.path.join(self.VIDEO_ROOT, topic, f"{v_id}.mp4")
                    
                    if not os.path.exists(video_path):
                        video_path = None

                    # JSON으로 저장된 컬럼들을 다시 리스트/딕셔너리로 복구
                    # generate 단계에서 json.dumps를 썼으므로 json.loads가 가장 빠르고 안전합니다.
                    parsed_row = {
                        "topic": topic,
                        "id": int(row.get("id", 0)),
                        "video_path": video_path,
                        "index": int(row.get("index", 0)),
                        "sentence": json.loads(row.get("sentence", "[]")),
                        "pinyin_mask": json.loads(row.get("pinyin_mask", "[]")),
                        "pron_mask": json.loads(row.get("pron_mask", "[]")),
                        "translation": json.loads(row.get("translation", "[]")),
                        "split_ms": int(row.get("split_ms", 0)),
                        "tip": json.loads(row.get("tip", "{}"))
                    }
                    
                    self.video_data_list.append(parsed_row)

                except Exception as e:
                    logging.warning(f"⚠️ 데이터 파싱 에러 (ID: {row.get('id')}): {e}")

        print(f"✅ 로딩 완료: {len(self.video_data_list)}개 아이템 로드됨.")
        return self.video_data_list

if __name__ == "__main__":
    dm = DataManager()
    
    # 1. 제너레이트 테스트
    target = sys.argv[1] if len(sys.argv) > 1 else "video_data.xlsx"
    dm.generate_csv(target)
    
    # 2. 로드 테스트
    data = dm.load_video_data() # 전체 로드
    if data:
        print(f"샘플 데이터 (첫 번째): {data[0]['sentence']}")