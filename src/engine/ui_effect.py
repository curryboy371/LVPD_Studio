import pygame
import random

class Particle:
    def __init__(self, x, y):
        self.pos = [x, y]
        self.vel = [random.uniform(-4, 4), random.uniform(-8, -2)]
        self.life = 255

    def update(self):
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.vel[1] += 0.3 # 중력 가속도
        self.life -= 10

class UIEffectEngine:
    def __init__(self):
        self.particles = []
        self.gauge_val = 0.0 # 현재 게이지 (0~100)
        self.target_val = 0.0

    def trigger_burst(self, x, y):
        for _ in range(20):
            self.particles.append(Particle(x, y))

    def update(self):
        # 게이지 부드러운 애니메이션 (LERP)
        self.gauge_val += (self.target_val - self.gauge_val) * 0.1
        
        # 파티클 업데이트
        for p in self.particles[:]:
            p.update()
            if p.life <= 0:
                self.particles.remove(p)

    def draw(self, screen):
        # 게이지 바 렌더링
        bar_x, bar_y, bar_w, bar_h = 240, 650, 800, 15
        pygame.draw.rect(screen, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=10)
        current_w = bar_w * (self.gauge_val / 100)
        if current_w > 0:
            pygame.draw.rect(screen, (0, 255, 150), (bar_x, bar_y, current_w, bar_h), border_radius=10)

        # 파티클 렌더링
        for p in self.particles:
            p_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(p_surf, (255, 255, 0, p.life), (3, 3), 3)
            screen.blit(p_surf, p.pos)