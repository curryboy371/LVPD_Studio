import pygame
import os
import cv2
import numpy as np
import json

from ffpyplayer.player import MediaPlayer

class VideoLayer:
    def __init__(self, video_path, pos=(0, 0), size=(1280, 720)):
        self.video_path = video_path
        self.pos = pos
        self.size = size
        
        # 1. 미디어 플레이어 초기화 (오디오/비디오 동시 핸들링)
        # ffpyplayer는 자체적으로 오디오를 재생하며 비디오 프레임 시간을 계산합니다.
        self.player = MediaPlayer(video_path)
        self.last_surf = None

    def get_surface(self):
        # 2. 플레이어로부터 프레임과 대기 시간(val)을 가져옴
        # frame: 비디오 데이터, val: 오디오와의 싱크를 맞추기 위한 지연 시간
        frame, val = self.player.get_frame()

        if val == 'eof':
            # 루프 재생을 원할 경우 (처음으로 되감기)
            self.player.seek(0, relative=False)
            return self.last_surf

        if frame is None:
            # 새로운 프레임이 아직 준비되지 않았다면 마지막 프레임 유지
            return self.last_surf

        # 3. 프레임 이미지 변환 (ffpyplayer 이미지는 RGB 형식이 다를 수 있음)
        img, t = frame
        w, h = img.get_size()
        
        # 이미지 데이터를 Pygame용으로 변환
        data = img.to_bytearray()[0]
        # ffpyplayer는 기본적으로 RGB 형식을 사용함
        current_surf = pygame.image.frombuffer(data, (w, h), "RGB")
        
        # 4. 크기 조정 (화면 전체 크기 등)
        if (w, h) != self.size:
            current_surf = pygame.transform.scale(current_surf, self.size)
        
        self.last_surf = current_surf
        return current_surf

    def close(self):
        """영상 교체 시 반드시 호출하여 소리를 끔"""
        if self.player:
            self.player.close_player()
            self.player = None

class ContentRenderer:
    def __init__(self, font_manager):
        self.fm = font_manager
        self.video_layer = None

    def update_video_source(self, video_path, pos, size):
        """영상을 교체할 때 기존 소리를 완전히 죽이고 새로 시작"""
        if self.video_layer:
            self.video_layer.close() # 기존 소리/영상 해제 (중요!)
            
        if video_path and os.path.exists(video_path):
            # 렌더러가 직접 비디오 레이어를 생성하여 관리
            self.video_layer = VideoLayer(video_path, pos, size)
        else:
            self.video_layer = None

    def draw_scene(self, screen, item, effect_engine, config):
        # 1. 배경
        screen.fill(config.bg_color)

        # 2. 전체 화면 비디오 출력
        if self.video_layer:
            surf = self.video_layer.get_surface()
            if surf:
                screen.blit(surf, self.video_layer.pos)

        # 3. 텍스트 출력 (가독성을 위해 약간의 쉐도우나 박스를 넣을 수 있음)
        if item:
            sentence = item['sentence'][0] if item['sentence'] else ""
            translation = item['translation'][0] if item['translation'] else ""
            
            # 중앙 하단 텍스트 배치 예시
            main_pos = config.get_pos(0.5, 0.75)
            sub_pos = config.get_pos(0.5, 0.85)
            
            self._render_text(screen, sentence, main_pos[0], main_pos[1], 70, (255, 255, 255), True)
            self._render_text(screen, translation, sub_pos[0], sub_pos[1], 40, (200, 200, 200), True)

        # 4. 이펙트 (파티클 등)
        effect_engine.draw(screen)

    def _render_text(self, screen, text, x, y, size, color, shadow=False):
        font = self.fm.get_font("notosans", size)
        if shadow: # 영상 위에서 잘 보이도록 그림자 효과
            shadow_surf = font.render(text, True, (0, 0, 0))
            screen.blit(shadow_surf, shadow_surf.get_rect(center=(x+2, y+2)))
            
        surf = font.render(text, True, color)
        screen.blit(surf, surf.get_rect(center=(x, y)))