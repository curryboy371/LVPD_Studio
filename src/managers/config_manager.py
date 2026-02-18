import pygame

class ConfigManager:
    def __init__(self, width=1920, height=1080):
        self.width = width
        self.height = height
        self.fps = 30
        self.bg_color = (20, 20, 25)

    def get_pos(self, rx, ry):
        """0.0~1.0 사이의 비율 좌표를 절대 좌표로 변환"""
        return (int(self.width * rx), int(self.height * ry))

    def get_size(self, rw, rh):
        """비율 크기를 절대 크기로 변환"""
        return (int(self.width * rw), int(self.height * rh))
    
    def get_contained_size(self, target_ratio_w, target_ratio_h, original_v_w, original_v_h):
        """지정한 비율 박스 안에 원본 영상 비율을 유지하며 꽉 차게 계산"""
        max_w, max_h = self.get_size(target_ratio_w, target_ratio_h)
        
        aspect_ratio = original_v_w / original_v_h
        # 가로 기준 세로 계산
        new_w = max_w
        new_h = int(new_w / aspect_ratio)
        
        if new_h > max_h: # 세로가 초과하면 세로 기준 재계산
            new_h = max_h
            new_w = int(new_h * aspect_ratio)
            
        return (new_w, new_h)