import pygame

class FontManager:
    def __init__(self):
        pygame.font.init()
        self.fonts = {}

    def get_font(self, name, size):
        key = f"{name}_{size}"
        if key not in self.fonts:
            # 시스템에 설치된 중국어 지원 폰트(예: SimHei)나 경로 지정
            self.fonts[key] = pygame.font.SysFont(["malgungothic", "simhei", "arial"], size)
        return self.fonts[key]