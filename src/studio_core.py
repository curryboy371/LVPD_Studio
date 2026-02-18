import pygame
import sys
from src.managers.data_manager import DataManager
from src.managers.recording_manager import RecordingManager
from src.managers.font_manager import FontManager
from src.managers.config_manager import ConfigManager
from src.engine.renderer import ContentRenderer, VideoLayer
from src.engine.ui_effect import UIEffectEngine

class LVPDStudio:
    def __init__(self):
        pygame.init()
        self.config = ConfigManager(1280, 720) # 720p 기준
        self.screen = pygame.display.set_mode((self.config.width, self.config.height))
        pygame.display.set_caption("LVPD Studio - Full Screen Mode")
        
        self.dm = DataManager()
        self.rm = RecordingManager()
        self.fm = FontManager()
        self.ui = UIEffectEngine()
        self.renderer = ContentRenderer(self.fm)
        
        self.dm.generate_csv("video_data.xlsx")
        self.data_list = self.dm.load_video_data()
        self.current_index = 0
        
        self.clock = pygame.time.Clock()
        self.is_recording = False
        self.running = True

    def update_content(self):
        """현재 인덱스의 비디오를 전체 화면 크기로 업데이트"""
        if not self.data_list: return
        item = self.data_list[self.current_index]

        # 전체 화면 좌표와 크기 계산
        full_pos = self.config.get_pos(0.0, 0.0)
        full_size = self.config.get_size(1.0, 1.0)
        
        self.renderer.update_video_source(item['video_path'], pos=full_pos, size=full_size)


    def run(self):
        # 첫 번째 콘텐츠 로드
        self.update_content()
    
        while self.running:
            # 1. UI 및 데이터 업데이트
            total = len(self.data_list)
            if total > 0:
                self.ui.target_val = ((self.current_index + 1) / total) * 100
            self.ui.update()

            # 2. 이벤트 처리
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False

                    if event.key == pygame.K_SPACE:
                        if self.current_index < total - 1:
                            self.current_index += 1
                            self.update_content() # 여기서 비디오 교체 및 크기 재설정
                            
                            # 파티클 터지는 위치를 게이지 위치 등으로 조정 가능
                            burst_pos = self.config.get_pos(0.5, 0.95)
                            self.ui.trigger_burst(*burst_pos)
                        else:
                            print("학습 종료")

                    if event.key == pygame.K_r:
                        if not self.is_recording:
                            item = self.data_list[self.current_index]
                            self.rm.start_recording_threaded(filename_prefix=f"REC_{item['id']}")
                            self.is_recording = True
                        else:
                            self.rm.stop_recording_threaded()
                            self.is_recording = False

            # 3. 렌더링 (Renderer에게 계산된 config 전달)
            current_item = self.data_list[self.current_index] if self.data_list else None
            self.renderer.draw_scene(self.screen, current_item, self.ui, self.config)

            # 4. 녹화 인디케이터 (우측 상단 비율 배치)
            if self.is_recording:
                rec_pos = self.config.get_pos(0.95, 0.05)
                pygame.draw.circle(self.screen, (255, 0, 0), rec_pos, 10)

            pygame.display.flip()
            self.clock.tick(self.config.fps)

        # 종료 처리
        if self.is_recording:
            self.rm.stop_recording_threaded()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    studio = LVPDStudio()
    studio.run()