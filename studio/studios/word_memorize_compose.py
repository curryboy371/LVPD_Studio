"""단어 외우기 — 조합형(부품 한자 2개 → 결과 도장 + 트레이 누적) 전용 씬 렌더러.

shorts_plan.md의 A(미리보기/복습)–B1–B2–B3–A 루프를 그린다. 표준 박스 그리드
렌더링과는 완전히 별개의 씬이라 word_memorize_renderer.py에서 이 모듈로 바로 분기한다.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pygame

from core.paths import get_repo_root
from studio.conversation.tools.karaoke_wipe import (
    blit_horizontal_karaoke_wipe,
    compute_karaoke_progress,
)
from utils.fonts import load_font, load_font_noto_sans_cjk_sc
from utils.pinyin_masking import get_pinyin_processor

# ---------------------------------------------------------------------------
# 타이밍 — shorts_plan.md §2/§3 (B 구간 ~10초) 기준. word_memorize.py가
# substep="compose" 동안 self._timer(0→hold_sec)를 그대로 이 초 단위로 넘긴다.
# ---------------------------------------------------------------------------
PART_A_STAMP_SEC = 0.5
PLUS_POP_SEC = 1.2
PART_B_STAMP_SEC = 1.8
ARROW_POP_SEC = 2.8
IMPACT_SEC = 2.9
PINYIN_POP_SEC = 3.5
MEANING_POP_SEC = 3.8
HIGHLIGHT_SEC = 4.2
TRAY_SLIDE_SEC = 5.0
COMPOSE_B_TOTAL_SEC = 10.0

PREVIEW_STAMP_INTERVAL_SEC = 0.15
COMPOSE_PREVIEW_HOLD_SEC = 4.0
COMPOSE_REVIEW_HOLD_SEC = 1.0

# 부품1/2/3 내레이션이 실제로 끝난 뒤에도 화면이 이미 앞서가 있지 않도록 두는 여유.
COMPOSE_GAP_AFTER_C1_NARRATION_SEC = 0.05
COMPOSE_GAP_AFTER_C2_NARRATION_SEC = 0.05
COMPOSE_GAP_AFTER_C3_NARRATION_SEC = 0.05


@dataclass(frozen=True)
class ComposeTiming:
    """B 구간 등장 시점 — 기본값은 고정 상수와 동일. 부품 내레이션이 길면
    build_compose_timing()이 뒤쪽 시점들을 늦춰 화면이 오디오보다 앞서가지 않게 한다.

    plus2_pop/part_c_stamp는 부품이 3개(长颈鹿=长+颈+鹿 같은 경우)일 때만 쓰이고,
    부품 2개짜리 조합에서는 0.0(=없음)으로 남는다."""

    part_a_stamp: float = PART_A_STAMP_SEC
    plus_pop: float = PLUS_POP_SEC
    part_b_stamp: float = PART_B_STAMP_SEC
    plus2_pop: float = 0.0
    part_c_stamp: float = 0.0
    arrow_pop: float = ARROW_POP_SEC
    impact: float = IMPACT_SEC
    pinyin_pop: float = PINYIN_POP_SEC
    meaning_pop: float = MEANING_POP_SEC
    highlight: float = HIGHLIGHT_SEC
    tray_slide: float = TRAY_SLIDE_SEC

    @property
    def has_part_c(self) -> bool:
        return self.part_c_stamp > 0.0


def build_compose_timing(*component_narration_secs: float) -> ComposeTiming:
    """부품(2개 또는 3개)의 실제 내레이션 총 길이(뜻 TTS + 간격 + 단어 TTS)에 맞춰
    다음 부품 타일·화살표 등장 시점을 늦춘다. 내레이션이 원래 고정 타이밍보다 짧으면
    max()로 원래의 스냅피한 템포를 그대로 유지한다 — 짧은 단어에 대해서까지
    불필요하게 느려지지 않도록.

    화살표 이후(임팩트·병음·뜻·라벨·트레이) 간격은 원본 고정 타이밍의 상대
    간격을 그대로 보존해 이어지는 연출 리듬은 바뀌지 않는다.
    """
    secs = list(component_narration_secs)
    while len(secs) < 2:
        secs.append(0.0)
    has_c3 = len(secs) >= 3

    part_a = PART_A_STAMP_SEC
    plus = part_a + (PLUS_POP_SEC - PART_A_STAMP_SEC)
    part_b = max(
        PART_B_STAMP_SEC,
        part_a + max(0.0, secs[0]) + COMPOSE_GAP_AFTER_C1_NARRATION_SEC,
    )

    if has_c3:
        plus2 = part_b + (PLUS_POP_SEC - PART_A_STAMP_SEC)
        part_c = max(
            plus2 + 0.1,
            part_b + max(0.0, secs[1]) + COMPOSE_GAP_AFTER_C2_NARRATION_SEC,
        )
        last_gate = part_c + max(0.0, secs[2]) + COMPOSE_GAP_AFTER_C3_NARRATION_SEC
    else:
        plus2 = 0.0
        part_c = 0.0
        last_gate = part_b + max(0.0, secs[1]) + COMPOSE_GAP_AFTER_C2_NARRATION_SEC

    arrow = max(ARROW_POP_SEC, last_gate)
    impact = arrow + (IMPACT_SEC - ARROW_POP_SEC)
    pinyin = impact + (PINYIN_POP_SEC - IMPACT_SEC)
    meaning = impact + (MEANING_POP_SEC - IMPACT_SEC)
    highlight = impact + (HIGHLIGHT_SEC - IMPACT_SEC)
    tray = highlight + (TRAY_SLIDE_SEC - HIGHLIGHT_SEC)
    return ComposeTiming(
        part_a_stamp=part_a,
        plus_pop=plus,
        part_b_stamp=part_b,
        plus2_pop=plus2,
        part_c_stamp=part_c,
        arrow_pop=arrow,
        impact=impact,
        pinyin_pop=pinyin,
        meaning_pop=meaning,
        highlight=highlight,
        tray_slide=tray,
    )


@dataclass(frozen=True)
class ComposeSentenceInfo:
    """4단 활용 문장 카드 데이터 — word_memorize.py가 words.csv의
    example_sentence/example_translation + 문장 TTS 길이를 미리 재서 채운다.
    sentence_zh가 비어 있으면 카드 자체를 그리지 않는다(문장 미작성 단어)."""

    sentence_zh: str = ""
    translation_ko: str = ""
    card_start: float = 0.0
    zh_start: float = 0.0
    zh_duration: float = 0.0


# 화면 전환 — A(미리보기)→B1→B2→B3→A(복습) 구간이 바뀔 때 스마트폰 스와이프처럼
# 좌→우로 넘어가는 효과(이전 화면 우측으로 퇴장 + 새 화면 좌측에서 진입).
SCREEN_TRANSITION_DURATION_SEC = 0.7

# ---------------------------------------------------------------------------
# 효과음 — 부품 타일 등장(랜덤 1개)/획 그어짐(화살표)/뜻 팝업. word_memorize.py가
# PART_A_STAMP_SEC/PART_B_STAMP_SEC/ARROW_POP_SEC/MEANING_POP_SEC 통과 시점에 재생한다.
# ---------------------------------------------------------------------------
WORD_MEMORIZE_COMPOSE_BLOCK_SOUND_RELS = (
    "resource/sound/effect/block1.mp3",
    "resource/sound/effect/block2.mp3",
)
WORD_MEMORIZE_COMPOSE_BRUSH_SOUND_REL = "resource/sound/effect/brush.mp3"
WORD_MEMORIZE_COMPOSE_OPEN_SOUND_REL = "resource/sound/effect/open.mp3"
WORD_MEMORIZE_COMPOSE_POP_SOUND_REL = "resource/sound/effect/pop.mp3"


def pick_random_compose_block_sound_path() -> Path:
    """부품 타일 등장 — block1/block2 중 무작위 1개."""
    return get_repo_root() / random.choice(WORD_MEMORIZE_COMPOSE_BLOCK_SOUND_RELS)


def compose_brush_sound_path() -> Path:
    """획 그어짐(화살표 등장) 효과음 절대 경로."""
    return get_repo_root() / WORD_MEMORIZE_COMPOSE_BRUSH_SOUND_REL


def compose_open_sound_path() -> Path:
    """뜻 팝업 효과음 절대 경로."""
    return get_repo_root() / WORD_MEMORIZE_COMPOSE_OPEN_SOUND_REL


def compose_pop_sound_path() -> Path:
    """조합 결과 단어 등장(임팩트) 효과음 절대 경로."""
    return get_repo_root() / WORD_MEMORIZE_COMPOSE_POP_SOUND_REL

IMPACT_RING_DURATION_SEC = 0.6
IMPACT_SHAKE_DURATION_SEC = 0.4
IMPACT_SHAKE_MAGNITUDE_PX = 6.0
PARTICLE_LIFETIME_SEC = 0.75
PARTICLE_COUNT = 22

RESULT_IMAGE_SIZE = 230
RESULT_CARD_PAD = 28
RESULT_CARD_GAP = 26
RESULT_CARD_ROW_GAP = 8

# ---------------------------------------------------------------------------
# 4단 결과 단어 활용 문장 카드(병음/문장/뜻) — shorts_plan.md 4단 자리를 대체.
# 재료1/재료2 색은 위 부품 타일 테두리와 1:1 매칭(재사용된 정보라는 인지 부담 감소).
# 병음·문장은 가라오케 워프(회화모드 karaoke_wipe 재사용)로 문장 TTS 재생과 동기화.
# ---------------------------------------------------------------------------
COMPONENT1_ACCENT_COLOR = (0x0C, 0x38, 0x10)
COMPONENT2_ACCENT_COLOR = (0x8A, 0x40, 0x00)
COMPONENT3_ACCENT_COLOR = (0x1A, 0x23, 0x7A)
COMPONENT_TILE_BORDER_WIDTH = 5

SENTENCE_CARD_BG_COLOR = (0xB3, 0xE5, 0xFC)
SENTENCE_CARD_BORDER_COLOR = (0x2A, 0x22, 0x18)
SENTENCE_CARD_BORDER_WIDTH = 5
SENTENCE_CARD_SHADOW_COLOR = (0x14, 0x10, 0x0A, 200)
SENTENCE_CARD_SHADOW_OFFSET = (10, 10)
SENTENCE_CARD_MAX_WIDTH_RATIO = 0.86
SENTENCE_CARD_FADE_IN_SEC = 0.6
SENTENCE_CARD_BOUNCE_WINDOW_SEC = 0.7
SENTENCE_PINYIN_FONT_SIZE = 42
SENTENCE_HANZI_FONT_SIZE = 64
SENTENCE_TRANSLATION_FONT_SIZE = 36
SENTENCE_LINE_GAP = 14
# 가라오케 비활성(아직 재생 안 된) 구간 — 활성 텍스트와 같은 색이되 알파만 낮춤.
SENTENCE_KARAOKE_INACTIVE_ALPHA = 100
SENTENCE_HANZI_ACTIVE_COLOR = (0x00, 0x00, 0x00)
SENTENCE_PINYIN_COLOR = (0xC6, 0x28, 0x28)
SENTENCE_TRANSLATION_COLOR = (0x5A, 0x5A, 0x5A)
# 결과 카드(붉은 도장) 위 병음 — 카드 배경 자체가 빨강 계열이라 병음도 빨간색이면
# 묻혀서, 여기만 금색으로 대비를 확보한다(문장 카드는 하늘색 배경이라 빨강 유지).
RESULT_PINYIN_COLOR = (0xFF, 0xC1, 0x07)

# 상단 질문 카피 — 스크롤 중에도 시선을 붙잡아야 하는 훅이라 화면 폭의 70~80%를
# 채우도록 자동으로 폰트 크기를 키운다(_get_fitted_header_fonts).
HEADER_TARGET_WIDTH_RATIO = 0.78
HEADER_FONT_MIN_SIZE = 42
HEADER_FONT_MAX_SIZE = 160
HEADER_FONT_STEP = 4

# ---------------------------------------------------------------------------
# 색 — shorts_plan.md §6
# ---------------------------------------------------------------------------
TILE_BG_COLOR = (0xF6, 0xF0, 0xE3)
TILE_TEXT_COLOR = (0x2A, 0x22, 0x1C)
SEAL_COLOR = (0xE0, 0x50, 0x3A)
HIGHLIGHT_COLOR = (0xF6, 0xD3, 0x4B)
HEADER_COLOR = (0xF0, 0xEA, 0xDD)
MEANING_COLOR = (0xFF, 0xFF, 0xFF)
# 흰 글자가 배경(영상/이미지)에 상관없이 항상 보이도록 충분히 짙은 배경.
TRAY_CHIP_BG = (0xE0, 0x50, 0x3A, 210)
TRAY_CHIP_BORDER = (0xE0, 0x50, 0x3A)
TRAY_CHIP_H = 64
TRAY_CHIP_GAP = 16
TRAY_SLIDE_ANIM_SEC = 0.5
PARTICLE_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0xD4, 0xAF, 0x37),
    (0xF6, 0xF0, 0xE3),
    (0xE8, 0xC5, 0x6E),
)


def _ease_out_quad(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 2


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _ease_out_back(x: float, overshoot: float = 1.4) -> float:
    """0..1 → 살짝 넘쳤다 정착하는 바운스 스케일(과하지 않은 오버슈트)."""
    x = max(0.0, min(1.0, x))
    c1 = overshoot
    c3 = c1 + 1.0
    return 1.0 + c3 * (x - 1.0) ** 3 + c1 * (x - 1.0) ** 2


def stamp_bounce_scale(t: float) -> float:
    """임팩트 후 경과 비율(0..1) → 0.3→1.15→0.96→1.0 바운스 스케일."""
    t = max(0.0, min(1.0, t))
    if t < 0.45:
        return 0.3 + (1.15 - 0.3) * _ease_out_quad(t / 0.45)
    if t < 0.75:
        local = (t - 0.45) / 0.30
        return 1.15 + (0.96 - 1.15) * _smoothstep(local)
    local = (t - 0.75) / 0.25
    return 0.96 + (1.0 - 0.96) * _smoothstep(local)


def stamp_bounce_rotation_deg(t: float) -> float:
    """임팩트 후 경과 비율(0..1) → -8°→+3°→-1°→0° 회전 흔들림."""
    t = max(0.0, min(1.0, t))
    if t < 0.4:
        return -8.0 + 11.0 * _ease_out_quad(t / 0.4)
    if t < 0.7:
        return 3.0 - 4.0 * _smoothstep((t - 0.4) / 0.3)
    return -1.0 + 1.0 * _smoothstep((t - 0.7) / 0.3)


def screen_shake_offset(
    elapsed_since_impact: float,
    *,
    duration: float = IMPACT_SHAKE_DURATION_SEC,
    magnitude: float = IMPACT_SHAKE_MAGNITUDE_PX,
) -> tuple[int, int]:
    if elapsed_since_impact < 0.0 or elapsed_since_impact > duration:
        return (0, 0)
    decay = 1.0 - (elapsed_since_impact / duration)
    freq = 46.0
    dx = magnitude * decay * math.sin(elapsed_since_impact * freq)
    dy = magnitude * decay * math.cos(elapsed_since_impact * freq * 1.3)
    return (int(round(dx)), int(round(dy)))


def draw_impact_ring(
    surface: pygame.Surface,
    center: tuple[int, int],
    elapsed_since_impact: float,
    *,
    duration: float = IMPACT_RING_DURATION_SEC,
    max_radius: float = 190.0,
    color: tuple[int, int, int] = SEAL_COLOR,
) -> None:
    if elapsed_since_impact < 0.0 or elapsed_since_impact > duration:
        return
    t = elapsed_since_impact / duration
    radius = max(1, int(max_radius * _ease_out_quad(t)))
    alpha = int(220 * (1.0 - t))
    if alpha <= 0:
        return
    width = max(2, int(10 * (1.0 - t)))
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*color, alpha), center, radius, width=width)
    surface.blit(layer, (0, 0))


def draw_seal_glow(
    surface: pygame.Surface,
    center: tuple[int, int],
    *,
    radius: int = 170,
    alpha: int = 90,
    color: tuple[int, int, int] = SEAL_COLOR,
) -> None:
    if radius <= 0 or alpha <= 0:
        return
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(radius, 0, -4):
        a = int(alpha * (1.0 - i / radius) ** 2)
        pygame.draw.circle(layer, (*color, a), (radius, radius), i)
    surface.blit(layer, (center[0] - radius, center[1] - radius))


@dataclass(frozen=True)
class _Particle:
    angle: float
    speed: float
    size: float
    color: tuple[int, int, int]
    twinkle_phase: float


def _spawn_particles(seed: int, count: int = PARTICLE_COUNT) -> list[_Particle]:
    """결과 도장 임팩트 파티클 — 카드보다 멀리 퍼져야 카드에 가려지지 않고
    바깥 여백에서 보인다(카드 반폭 약 300px보다 크게 날아가도록 speed를 잡음)."""
    rng = random.Random(seed)
    out: list[_Particle] = []
    for _ in range(count):
        out.append(
            _Particle(
                angle=rng.uniform(0.0, math.tau),
                speed=rng.uniform(480.0, 820.0),
                size=rng.uniform(3.0, 8.0),
                color=rng.choice(PARTICLE_PALETTE),
                twinkle_phase=rng.uniform(0.0, math.tau),
            )
        )
    return out


def draw_particle_burst(
    surface: pygame.Surface,
    center: tuple[int, int],
    particles: Sequence[_Particle],
    elapsed_since_impact: float,
    *,
    lifetime: float = PARTICLE_LIFETIME_SEC,
) -> None:
    """부드러운 글로우(halo) + 밝은 코어 두 겹으로 그려 반짝이는 느낌을 준다.
    카드(결과 도장)는 이 함수 호출 뒤에 그려지므로, 카드 영역과 겹치는 파티클은
    자연히 카드에 가려지고 카드 바깥으로 퍼진 파티클만 보여 글자를 가리지 않는다.
    """
    if elapsed_since_impact < 0.0 or elapsed_since_impact > lifetime:
        return
    t = elapsed_since_impact / lifetime
    # 앞부분은 완전 불투명으로 유지하고(카드 밖으로 다 퍼져나갈 때까지) 뒷부분에서만
    # 페이드 — 선형으로 처음부터 흐려지면 카드를 벗어나기도 전에 다 사라져 버린다.
    hold = 0.35
    fade_alpha = 1.0 if t < hold else max(0.0, 1.0 - (t - hold) / (1.0 - hold))
    if fade_alpha <= 0:
        return
    gravity = 200.0
    ease_out = 1.0 - (1.0 - min(1.0, elapsed_since_impact / 0.12)) ** 2
    for p in particles:
        dist = p.speed * ease_out * elapsed_since_impact
        x = center[0] + math.cos(p.angle) * dist
        y = center[1] + math.sin(p.angle) * dist + 0.5 * gravity * elapsed_since_impact**2
        size = max(1.0, p.size * (1.0 - 0.3 * t))
        twinkle = 0.7 + 0.3 * math.sin(elapsed_since_impact * 14.0 + p.twinkle_phase)
        alpha = max(0, min(255, int(255 * fade_alpha * twinkle)))
        if alpha <= 0:
            continue
        halo_r = size * 2.2
        dia = int(halo_r * 2) + 2
        spr = pygame.Surface((dia, dia), pygame.SRCALPHA)
        c = spr.get_width() // 2
        pygame.draw.circle(spr, (*p.color, int(alpha * 0.35)), (c, c), halo_r)
        pygame.draw.circle(spr, (*p.color, alpha), (c, c), size)
        pygame.draw.circle(spr, (255, 255, 255, alpha), (c, c), max(1.0, size * 0.45))
        surface.blit(spr, (x - c, y - c))


def _resolve_pinyin_display(word: Any) -> str:
    """word.pinyin이 비어 있으면(데이터 누락) 한자(word.word)에서 g2pM으로 자동 변환한다."""
    pinyin = str(getattr(word, "pinyin", "") or "").strip()
    if pinyin:
        return pinyin
    hanzi = str(getattr(word, "word", "") or "").strip()
    if not hanzi:
        return ""
    pp = get_pinyin_processor()
    if not pp.available:
        return ""
    return pp.full_convert(hanzi)


def _is_cjk_ideograph(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _split_cjk_runs(text: str) -> list[tuple[str, bool]]:
    """(부분 문자열, 한자 여부) 리스트 — 한글용 폰트가 한자 글리프를 갖지 않아 폰트를 갈라 그린다."""
    runs: list[tuple[str, bool]] = []
    buf = ""
    buf_is_cjk: bool | None = None
    for ch in text:
        is_cjk = _is_cjk_ideograph(ch)
        if buf_is_cjk is None or is_cjk == buf_is_cjk:
            buf += ch
            buf_is_cjk = is_cjk
        else:
            runs.append((buf, bool(buf_is_cjk)))
            buf = ch
            buf_is_cjk = is_cjk
    if buf:
        runs.append((buf, bool(buf_is_cjk)))
    return runs


def render_mixed_script(
    font_kr: "pygame.font.Font | None",
    font_cn: "pygame.font.Font | None",
    text: str,
    color: tuple[int, int, int],
) -> pygame.Surface:
    """한글·한자가 섞인 문자열 — 구간별로 알맞은 폰트로 렌더링 후 이어붙임."""
    surfaces: list[pygame.Surface] = []
    for chunk, is_cjk in _split_cjk_runs(text):
        font = font_cn if is_cjk else font_kr
        if font is None:
            continue
        surfaces.append(font.render(chunk, True, color))
    if not surfaces:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    total_w = sum(s.get_width() for s in surfaces)
    max_h = max(s.get_height() for s in surfaces)
    out = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
    x = 0
    for s in surfaces:
        out.blit(s, (x, (max_h - s.get_height()) // 2))
        x += s.get_width()
    return out


def _fade_scale_alpha(t: float, *, in_sec: float = 0.3) -> tuple[float, int]:
    """0에서 시작해 in_sec에 걸쳐 등장 — (스케일, 알파)."""
    if t <= 0.0:
        return 0.0, 0
    ratio = min(1.0, t / in_sec)
    return _ease_out_quad(ratio), int(255 * ratio)


_CARD_GLOW_COLOR = (0x5B, 0x9C, 0xFF)


def _draw_card_glow(band: pygame.Surface, card_rect: pygame.Rect, *, radius: int = 18) -> None:
    """카드 테두리에 은은하게 번지는 파란 광채 — 참고 이미지("Generate" 버튼)
    스타일. 카드 바깥으로 살짝씩 부풀린 테두리를 여러 겹(바깥일수록 흐리게)
    그려서 유리질 네온 테두리처럼 보이게 한다."""
    for step, glow_alpha in ((12, 8), (8, 14), (5, 22), (3, 36)):
        r = card_rect.inflate(step * 2, step * 2)
        pygame.draw.rect(
            band, (*_CARD_GLOW_COLOR, glow_alpha), r,
            width=max(2, step), border_radius=radius + step,
        )
    pygame.draw.rect(
        band, (*_CARD_GLOW_COLOR, 190), card_rect, width=2, border_radius=radius
    )


def _scaled_surface(surf: pygame.Surface, scale: float) -> pygame.Surface:
    if scale <= 0.0:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    w = max(1, int(surf.get_width() * scale))
    h = max(1, int(surf.get_height() * scale))
    return pygame.transform.smoothscale(surf, (w, h))


def _resolve_word_image_path(word: Any) -> "Path | None":
    """words.xlsx img_path — 실사진/일러스트 에셋 (기존 카드형 타입과 동일 리소스 재사용)."""
    from extra.table_editor.services.image_paths import preview_image_path

    raw = str(getattr(word, "img_path", "") or "").strip()
    if not raw or raw.lower() == "none":
        return None
    return preview_image_path(
        get_repo_root(),
        raw,
        word_id=str(getattr(word, "id", "")),
        word=str(getattr(word, "word", "")),
    )


def _load_scaled_image(path: "Path", max_w: int, max_h: int) -> "pygame.Surface | None":
    if max_w < 4 or max_h < 4:
        return None
    try:
        surf = pygame.image.load(str(path))
        surf = surf.convert_alpha() if surf.get_alpha() is not None else surf.convert()
        w, h = surf.get_size()
        if w <= 0 or h <= 0:
            return None
        scale = min(max_w / w, max_h / h, 1.0)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        if (nw, nh) != (w, h):
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        return surf
    except Exception:
        return None


_CHARACTER_LOGO_DIR = get_repo_root() / "resource" / "image" / "game" / "character"


def _pick_random_character_logo() -> "Path | None":
    """미리보기/복습 화면 하단에 로고처럼 띄울 캐릭터 이미지 — 영상 1개당 무작위 1개."""
    if not _CHARACTER_LOGO_DIR.is_dir():
        return None
    candidates = sorted(p for p in _CHARACTER_LOGO_DIR.glob("*.png") if p.is_file())
    if not candidates:
        return None
    return random.choice(candidates)


class ComposeSceneRenderer:
    """조합형 전용 씬(A 미리보기/복습, B 조합 연출, 트레이) — 표준 박스 그리드와 완전 분리."""

    def __init__(self) -> None:
        # 폰트는 여기서 바로 로드하지 않는다 — WordMemorizeStudio.__init__은
        # runner.main()에서 pygame.init() 이전(_create_studio 시점)에 호출되므로,
        # 여기서 로드하면 pygame.font가 아직 준비되지 않아 전부 조용히 실패한다
        # (WordMemorizeRenderer.ensure_fonts()와 동일하게 draw() 시점까지 지연).
        self._fonts_ready = False
        self._font_header: "pygame.font.Font | None" = None
        self._font_header_cn: "pygame.font.Font | None" = None
        self._font_component_hanzi: "pygame.font.Font | None" = None
        self._font_component_pinyin: "pygame.font.Font | None" = None
        self._font_component_meaning: "pygame.font.Font | None" = None
        # 부품이 3개(长颈鹿=长+颈+鹿)일 때 좁아진 타일에 맞춘 축소 폰트
        self._font_component_hanzi_small: "pygame.font.Font | None" = None
        self._font_component_pinyin_small: "pygame.font.Font | None" = None
        self._font_component_meaning_small: "pygame.font.Font | None" = None
        self._font_plus: "pygame.font.Font | None" = None
        self._font_arrow: "pygame.font.Font | None" = None
        self._font_result_hanzi: "pygame.font.Font | None" = None
        self._font_result_pinyin: "pygame.font.Font | None" = None
        self._font_result_meaning: "pygame.font.Font | None" = None
        self._font_sentence_pinyin: "pygame.font.Font | None" = None
        self._font_sentence_hanzi: "pygame.font.Font | None" = None
        self._font_sentence_translation: "pygame.font.Font | None" = None
        self._font_tray: "pygame.font.Font | None" = None
        self._font_preview_word: "pygame.font.Font | None" = None
        self._font_preview_pinyin: "pygame.font.Font | None" = None
        self._font_preview_meaning: "pygame.font.Font | None" = None
        self._font_preview_header: "pygame.font.Font | None" = None
        self._font_preview_topic: "pygame.font.Font | None" = None
        self._image_cache: dict[tuple[int, int, int], "pygame.Surface | None"] = {}
        self._header_font_cache: dict[int, tuple[str, "pygame.font.Font | None", "pygame.font.Font | None"]] = {}
        self._active_scene_key: tuple[str, int | None] | None = None
        self._prev_scene_frame: "pygame.Surface | None" = None
        self._latest_current_frame: "pygame.Surface | None" = None
        self._scene_changed_at: float | None = None
        # 미리보기/복습 화면 하단 캐릭터 로고 — 영상 1개당 무작위로 1개 골라 고정.
        self._character_logo_path = _pick_random_character_logo()
        self._character_logo_loaded = False
        self._character_logo_cache: "pygame.Surface | None" = None

    def ensure_fonts(self) -> None:
        if self._fonts_ready:
            return
        self._fonts_ready = True
        self._font_header = load_font(size=42, weight="bold", lang_hint="kr")
        self._font_header_cn = load_font_noto_sans_cjk_sc(42, HEADER_COLOR, weight="bold")
        self._font_component_hanzi = load_font_noto_sans_cjk_sc(72, TILE_TEXT_COLOR)
        self._font_component_pinyin = load_font_noto_sans_cjk_sc(38, TILE_TEXT_COLOR)
        self._font_component_meaning = load_font(size=32, weight="regular", lang_hint="kr")
        self._font_component_hanzi_small = load_font_noto_sans_cjk_sc(54, TILE_TEXT_COLOR)
        self._font_component_pinyin_small = load_font_noto_sans_cjk_sc(30, TILE_TEXT_COLOR)
        self._font_component_meaning_small = load_font(size=24, weight="regular", lang_hint="kr")
        self._font_plus = load_font(size=52, weight="bold", lang_hint="kr")
        self._font_arrow = load_font(size=46, weight="bold", lang_hint="kr")
        self._font_result_hanzi = load_font_noto_sans_cjk_sc(120, MEANING_COLOR)
        self._font_result_pinyin = load_font_noto_sans_cjk_sc(46, RESULT_PINYIN_COLOR)
        self._font_result_meaning = load_font(size=44, weight="bold", lang_hint="kr")
        self._font_sentence_pinyin = load_font_noto_sans_cjk_sc(
            SENTENCE_PINYIN_FONT_SIZE, SENTENCE_HANZI_ACTIVE_COLOR, weight="bold"
        )
        self._font_sentence_hanzi = load_font_noto_sans_cjk_sc(
            SENTENCE_HANZI_FONT_SIZE, SENTENCE_HANZI_ACTIVE_COLOR, weight="bold"
        )
        self._font_sentence_translation = load_font(
            size=SENTENCE_TRANSLATION_FONT_SIZE, weight="bold", lang_hint="kr"
        )
        self._font_tray = load_font_noto_sans_cjk_sc(26, MEANING_COLOR)
        self._font_preview_word = load_font_noto_sans_cjk_sc(68, MEANING_COLOR)
        self._font_preview_pinyin = load_font_noto_sans_cjk_sc(33, SEAL_COLOR, weight="bold")
        self._font_preview_meaning = load_font(size=41, weight="regular", lang_hint="kr")
        self._font_preview_header = load_font(size=64, weight="bold", lang_hint="kr")
        self._font_preview_topic = load_font(size=50, weight="bold", lang_hint="kr")

    def _get_fitted_header_fonts(
        self, result_id: int, header_text: str, target_w: int
    ) -> tuple["pygame.font.Font | None", "pygame.font.Font | None"]:
        """상단 질문 카피 — 화면 폭의 70~80%를 채우도록 폰트 크기를 자동으로 키운다.

        스크롤 중에도 눈에 띄어야 하는 훅 문구라 고정 폰트 크기로는 짧은/긴
        헤더 문구에 대응하기 어렵다. result_id당 한 번만 탐색해 캐시한다
        (매 프레임 폰트 로드는 비용이 크다 — B 구간 안에서는 헤더 문구가 바뀌지 않음).
        """
        cached = self._header_font_cache.get(result_id)
        if cached is not None and cached[0] == header_text:
            return cached[1], cached[2]
        size = HEADER_FONT_MIN_SIZE
        font_kr = load_font(size=size, weight="bold", lang_hint="kr")
        font_cn = load_font_noto_sans_cjk_sc(size, HEADER_COLOR, weight="bold")
        size += HEADER_FONT_STEP
        while size <= HEADER_FONT_MAX_SIZE:
            cand_kr = load_font(size=size, weight="bold", lang_hint="kr")
            cand_cn = load_font_noto_sans_cjk_sc(size, HEADER_COLOR, weight="bold")
            surf = render_mixed_script(cand_kr, cand_cn, header_text, HEADER_COLOR)
            if surf.get_width() > target_w:
                break
            font_kr, font_cn = cand_kr, cand_cn
            size += HEADER_FONT_STEP
        self._header_font_cache[result_id] = (header_text, font_kr, font_cn)
        return font_kr, font_cn

    def _get_word_image(self, word: Any, max_w: int, max_h: int) -> "pygame.Surface | None":
        wid = int(getattr(word, "id", 0) or 0)
        key = (wid, max_w, max_h)
        if key not in self._image_cache:
            path = _resolve_word_image_path(word)
            self._image_cache[key] = (
                _load_scaled_image(path, max_w, max_h) if path is not None else None
            )
        return self._image_cache[key]

    def _get_character_logo(self, max_h: int) -> "pygame.Surface | None":
        if not self._character_logo_loaded:
            self._character_logo_loaded = True
            if self._character_logo_path is not None:
                self._character_logo_cache = _load_scaled_image(
                    self._character_logo_path, 10_000, max_h
                )
        return self._character_logo_cache

    # -- 공개 진입점 ---------------------------------------------------
    def draw(
        self,
        surface: pygame.Surface,
        *,
        words_by_id: dict[int, Any],
        card_meaning_by_id: dict[int, str],
        component_ids_by_result: dict[int, tuple[int, ...]],
        phase: str,
        active_word_id: int | None,
        word_substep: str,
        timer_sec: float,
        sequence_word_ids: list[int],
        tray_word_ids: list[int],
        timing: "ComposeTiming | None" = None,
        absolute_time_sec: float = 0.0,
        sentence: "ComposeSentenceInfo | None" = None,
        topic: str = "",
    ) -> None:
        self.ensure_fonts()
        scene_key = (phase, active_word_id if phase == "word" else None)

        current = surface.copy()
        if phase != "word" or word_substep != "compose" or active_word_id is None:
            self._draw_preview(
                current,
                sequence_word_ids,
                words_by_id,
                card_meaning_by_id,
                phase=phase,
                timer_sec=timer_sec,
                topic=topic,
            )
        else:
            self._draw_word_scene(
                current,
                active_word_id,
                words_by_id,
                card_meaning_by_id,
                component_ids_by_result,
                timer_sec=timer_sec,
                tray_word_ids=tray_word_ids,
                timing=timing or ComposeTiming(),
                sentence=sentence or ComposeSentenceInfo(),
            )

        if self._active_scene_key is None:
            self._active_scene_key = scene_key
            self._scene_changed_at = absolute_time_sec
        elif scene_key != self._active_scene_key:
            # 장면이 실제로 바뀐 첫 프레임에서만 갱신. 전환 진행도는 phase-local
            # timer_sec가 아니라 절대 시각(absolute_time_sec)으로 잰다 — outro
            # 등 한 구간의 hold가 끝나 timer_sec가 0으로 리셋되는 순간에도
            # scene_key 자체는 그대로인 경우가 있는데, timer_sec를 기준으로
            # 삼으면 그 순간을 "막 전환됨"으로 오인해 이미 여러 초 지난 이전
            # 장면(_prev_scene_frame)이 갑자기 다시 화면 전체를 덮어버린다.
            self._prev_scene_frame = self._latest_current_frame
            self._active_scene_key = scene_key
            self._scene_changed_at = absolute_time_sec

        self._composite_scene_transition(surface, current, absolute_time_sec)
        self._latest_current_frame = current

    def _composite_scene_transition(
        self,
        surface: pygame.Surface,
        current: pygame.Surface,
        absolute_time_sec: float,
    ) -> None:
        """A→B1→B2→B3→A 화면 전환 — 스마트폰에서 다음으로 넘기듯 이전 화면이
        왼쪽으로 빠지고 새 화면이 오른쪽에서 들어온다(우→좌 이동)."""
        elapsed = absolute_time_sec - (self._scene_changed_at or 0.0)
        if self._prev_scene_frame is None or elapsed >= SCREEN_TRANSITION_DURATION_SEC:
            surface.blit(current, (0, 0))
            return
        w = surface.get_width()
        t = _ease_out_quad(max(0.0, elapsed) / SCREEN_TRANSITION_DURATION_SEC)
        shift = int(w * t)
        surface.blit(self._prev_scene_frame, (-shift, 0))
        surface.blit(current, (w - shift, 0))

    # -- A 화면(미리보기/복습) ------------------------------------------
    def _draw_preview(
        self,
        surface: pygame.Surface,
        sequence_word_ids: list[int],
        words_by_id: dict[int, Any],
        card_meaning_by_id: dict[int, str],
        *,
        phase: str,
        timer_sec: float,
        topic: str = "",
    ) -> None:
        w, h = surface.get_size()
        title_y = int(h * 0.13)
        if self._font_preview_header is not None:
            header = self._font_preview_header.render("오늘의 조합 단어", True, HEADER_COLOR)
            surface.blit(header, (w // 2 - header.get_width() // 2, title_y))
            title_y += header.get_height()
        topic_text = (topic or "").strip()
        if topic_text and self._font_preview_topic is not None:
            subtitle = self._font_preview_topic.render(f'"{topic_text}"', True, SEAL_COLOR)
            surface.blit(subtitle, (w // 2 - subtitle.get_width() // 2, title_y + 12))

        row_h = 260  # 조합 세트는 최대 3개라 줄 하나에 넓게 쓸 수 있다.
        top = int(h * 0.32)
        for i, wid in enumerate(sequence_word_ids):
            word = words_by_id.get(wid)
            if word is None:
                continue
            reveal_at = i * PREVIEW_STAMP_INTERVAL_SEC
            t = timer_sec - reveal_at if phase == "intro" else 999.0
            scale, alpha = _fade_scale_alpha(t)
            if alpha <= 0:
                continue
            row_y = top + i * row_h
            self._draw_preview_row(
                surface, word, card_meaning_by_id.get(wid, ""), row_y, row_h, scale, alpha
            )

        rows_bottom = top + len(sequence_word_ids) * row_h
        logo_band_h = max(80, h - rows_bottom)
        logo = self._get_character_logo(int(logo_band_h * 0.9))
        if logo is not None:
            logo_copy = logo.copy()
            logo_copy.set_alpha(215)
            logo_y = rows_bottom + (logo_band_h - logo_copy.get_height()) // 2
            surface.blit(logo_copy, (w // 2 - logo_copy.get_width() // 2, logo_y))

    def _draw_preview_row(
        self,
        surface: pygame.Surface,
        word: Any,
        meaning: str,
        row_y: int,
        row_h: int,
        scale: float,
        alpha: int,
    ) -> None:
        w = surface.get_width()
        card_w = int(w * 0.78)
        card_h = row_h - 20
        margin = 26  # 카드 바깥으로 번지는 광채가 잘리지 않도록 여유 공간
        band_w, band_h = card_w + margin * 2, card_h + margin * 2
        band = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
        card_rect = pygame.Rect(margin, margin, card_w, card_h)

        # 참고 이미지("Generate" 버튼) 스타일 — 유리질 어두운 카드 + 테두리에
        # 은은하게 번지는 파란 광채. 배경(영상/이미지)이 밝아도 흰 글자가 항상
        # 보이도록 카드 내부는 짙게 채운다.
        _draw_card_glow(band, card_rect)
        pygame.draw.rect(band, (0x0A, 0x0E, 0x1C, 195), card_rect, border_radius=18)

        # 왼쪽: 사진 / 가운데: 병음(위, 붉은색)·한자(아래, 흰색) / 오른쪽: 한국어 뜻.
        pad = 28
        img_slot = card_h - pad * 2
        img = self._get_word_image(word, img_slot, img_slot)
        if img is not None:
            band.blit(img, (margin + pad, margin + (card_h - img.get_height()) // 2))

        hz = None
        if self._font_preview_word is not None:
            hz = self._font_preview_word.render(str(getattr(word, "word", "")), True, MEANING_COLOR)
        pinyin_text = _resolve_pinyin_display(word)
        pinyin_surf = None
        if self._font_preview_pinyin is not None and pinyin_text:
            pinyin_surf = self._font_preview_pinyin.render(pinyin_text, True, SEAL_COLOR)

        stack_gap = 6
        stack_h = (hz.get_height() if hz is not None else 0) + (
            stack_gap + pinyin_surf.get_height() if pinyin_surf is not None else 0
        )
        stack_w = max(
            hz.get_width() if hz is not None else 0,
            pinyin_surf.get_width() if pinyin_surf is not None else 0,
        )
        cx = margin + card_w // 2
        y = margin + (card_h - stack_h) // 2
        if pinyin_surf is not None:
            band.blit(pinyin_surf, (cx - pinyin_surf.get_width() // 2, y))
            y += pinyin_surf.get_height() + stack_gap
        if hz is not None:
            band.blit(hz, (cx - hz.get_width() // 2, y))

        if self._font_preview_meaning is not None and meaning:
            mn = self._font_preview_meaning.render(meaning, True, MEANING_COLOR)
            mn_x = min(margin + card_w - pad - mn.get_width(), cx + stack_w // 2 + 100)
            band.blit(mn, (mn_x, margin + card_h // 2 - mn.get_height() // 2))

        band = _scaled_surface(band, max(0.05, scale))
        band.set_alpha(alpha)
        surface.blit(band, (w // 2 - band.get_width() // 2, row_y - band.get_height() // 2 + row_h // 2))

    # -- B 화면(조합 연출) ------------------------------------------------
    def _draw_word_scene(
        self,
        surface: pygame.Surface,
        result_id: int,
        words_by_id: dict[int, Any],
        card_meaning_by_id: dict[int, str],
        component_ids_by_result: dict[int, tuple[int, ...]],
        *,
        timer_sec: float,
        tray_word_ids: list[int],
        timing: ComposeTiming,
        sentence: ComposeSentenceInfo,
    ) -> None:
        w, h = surface.get_size()
        result_word = words_by_id.get(result_id)
        if result_word is None:
            return
        comp_ids = component_ids_by_result.get(result_id, ())
        c1_id = comp_ids[0] if len(comp_ids) > 0 else 0
        c2_id = comp_ids[1] if len(comp_ids) > 1 else 0
        c3_id = comp_ids[2] if len(comp_ids) > 2 else 0
        c1 = words_by_id.get(c1_id)
        c2 = words_by_id.get(c2_id)
        c3 = words_by_id.get(c3_id) if c3_id else None

        shake = screen_shake_offset(timer_sec - timing.impact)

        header_text = f"왜 {getattr(result_word, 'word', '')} = {card_meaning_by_id.get(result_id, '')}?"
        font_kr, font_cn = self._get_fitted_header_fonts(result_id, header_text, int(w * HEADER_TARGET_WIDTH_RATIO))
        if font_kr is not None or font_cn is not None:
            header = render_mixed_script(font_kr, font_cn, header_text, HEADER_COLOR)
            surface.blit(
                header,
                (w // 2 - header.get_width() // 2 + shake[0], int(h * 0.08) + shake[1]),
            )

        cx = w // 2
        row_y = int(h * 0.27)
        # 부품이 3개(长颈鹿=长+颈+鹿 같은 경우)면 타일을 좁혀서 3칸을 한 줄에 맞춘다.
        if c3 is not None:
            # 3칸은 가로가 좁아 사진+글자를 옆으로 나란히 두면 글자가 잘리므로
            # 위(사진)/아래(글자) 2단으로 쌓는다 — 세로 여유가 더 필요해 타일도 높인다.
            tile_w, tile_h = 250, 300
            step = 320
            positions = (cx - step, cx, cx + step)
        else:
            tile_w, tile_h = 400, 260
            step = tile_w // 2 + 70
            positions = (cx - step, cx + step)
        small_fonts = c3 is not None

        if c1 is not None:
            self._draw_component_tile(
                surface, c1, card_meaning_by_id.get(c1_id, ""),
                center=(positions[0] + shake[0], row_y + shake[1]),
                size=(tile_w, tile_h),
                reveal_t=timer_sec - timing.part_a_stamp,
                accent_color=COMPONENT1_ACCENT_COLOR,
                small_fonts=small_fonts,
                stacked=small_fonts,
            )

        self._draw_compose_plus(
            surface,
            (positions[0] + positions[1]) // 2,
            row_y,
            timer_sec - timing.plus_pop,
            shake,
        )

        if c2 is not None:
            self._draw_component_tile(
                surface, c2, card_meaning_by_id.get(c2_id, ""),
                center=(positions[1] + shake[0], row_y + shake[1]),
                size=(tile_w, tile_h),
                reveal_t=timer_sec - timing.part_b_stamp,
                accent_color=COMPONENT2_ACCENT_COLOR,
                small_fonts=small_fonts,
                stacked=small_fonts,
            )

        if c3 is not None:
            self._draw_compose_plus(
                surface,
                (positions[1] + positions[2]) // 2,
                row_y,
                timer_sec - timing.plus2_pop,
                shake,
            )
            self._draw_component_tile(
                surface, c3, card_meaning_by_id.get(c3_id, ""),
                center=(positions[2] + shake[0], row_y + shake[1]),
                size=(tile_w, tile_h),
                reveal_t=timer_sec - timing.part_c_stamp,
                accent_color=COMPONENT3_ACCENT_COLOR,
                small_fonts=small_fonts,
                stacked=small_fonts,
            )

        if timer_sec >= timing.arrow_pop and self._font_arrow is not None:
            _, alpha = _fade_scale_alpha(timer_sec - timing.arrow_pop, in_sec=0.2)
            arrow = self._font_arrow.render("▼", True, SEAL_COLOR)
            arrow.set_alpha(alpha)
            surface.blit(
                arrow,
                (cx - arrow.get_width() // 2 + shake[0], int(h * 0.41) + shake[1]),
            )

        result_center = (cx + shake[0], int(h * 0.565) + shake[1])
        if timer_sec >= timing.impact:
            pinyin_alpha = (
                _fade_scale_alpha(timer_sec - timing.pinyin_pop, in_sec=0.3)[1]
                if timer_sec >= timing.pinyin_pop
                else 0
            )
            meaning_alpha = (
                _fade_scale_alpha(timer_sec - timing.meaning_pop, in_sec=0.3)[1]
                if timer_sec >= timing.meaning_pop
                else 0
            )
            self._draw_result_seal(
                surface,
                result_word,
                card_meaning_by_id.get(result_id, ""),
                result_center,
                timer_sec - timing.impact,
                pinyin_alpha=pinyin_alpha,
                meaning_alpha=meaning_alpha,
            )

        if sentence.sentence_zh:
            self._draw_sentence_card(
                surface,
                sentence,
                center=(cx + shake[0], int(h * 0.79) + shake[1]),
                timer_sec=timer_sec,
            )

        if tray_word_ids:
            self._draw_tray_scene(
                surface,
                tray_word_ids,
                result_id,
                words_by_id,
                timer_sec=timer_sec,
                result_center=result_center,
                tray_slide_sec=timing.tray_slide,
            )

    def _draw_compose_plus(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        reveal_t: float,
        shake: tuple[int, int],
    ) -> None:
        """부품 타일 사이 "＋" — 2부품일 땐 1개, 3부품일 땐 2개 찍힌다."""
        if reveal_t < 0.0 or self._font_plus is None:
            return
        _, alpha = _fade_scale_alpha(reveal_t, in_sec=0.25)
        plus = self._font_plus.render("＋", True, HIGHLIGHT_COLOR)
        plus.set_alpha(alpha)
        surface.blit(
            plus,
            (x - plus.get_width() // 2 + shake[0], y - plus.get_height() // 2 + shake[1]),
        )

    def _draw_component_tile(
        self,
        surface: pygame.Surface,
        word: Any,
        meaning: str,
        *,
        center: tuple[int, int],
        size: tuple[int, int],
        reveal_t: float,
        accent_color: tuple[int, int, int] | None = None,
        small_fonts: bool = False,
        stacked: bool = False,
    ) -> None:
        """부품 타일 — 실사진(img_path) + 한자/병음/뜻. 사진 없으면 기존처럼 텍스트만 중앙 배치.

        accent_color는 4단 등식 라벨에서 같은 색으로 재사용되는 재료 구분색
        (재료1=초록/재료2=주황/재료3=남색) — 타일 테두리에 얇게 둘러 "위 카드 색과
        매칭"되게 한다. small_fonts는 부품이 3개라 타일이 좁아졌을 때(축소 폰트) 씀.
        stacked=True면 사진(위)/글자(아래) 2단으로 쌓는다 — 3부품이라 타일 폭이
        좁을 때 사진+글자를 옆으로 나란히 두면 글자가 잘리는 문제를 해결한다.
        """
        if reveal_t < 0.0:
            return
        scale, alpha = _fade_scale_alpha(reveal_t, in_sec=0.3)
        tw, th = size
        tile = pygame.Surface((tw, th), pygame.SRCALPHA)
        pygame.draw.rect(tile, TILE_BG_COLOR, tile.get_rect(), border_radius=16)
        if accent_color is not None:
            pygame.draw.rect(
                tile, accent_color, tile.get_rect(), width=COMPONENT_TILE_BORDER_WIDTH, border_radius=16
            )

        hanzi_font = self._font_component_hanzi_small if small_fonts else self._font_component_hanzi
        pinyin_font = self._font_component_pinyin_small if small_fonts else self._font_component_pinyin
        meaning_font = self._font_component_meaning_small if small_fonts else self._font_component_meaning

        lines: list[pygame.Surface] = []
        if hanzi_font is not None:
            lines.append(
                hanzi_font.render(str(getattr(word, "word", "")), True, TILE_TEXT_COLOR)
            )
        pinyin = _resolve_pinyin_display(word)
        if pinyin_font is not None and pinyin:
            lines.append(pinyin_font.render(pinyin, True, SEAL_COLOR))
        if meaning_font is not None and meaning:
            lines.append(meaning_font.render(meaning, True, TILE_TEXT_COLOR))

        if stacked:
            pad = 14
            gap = 6
            img_area_w = tw - pad * 2
            img_area_h = 95
            img = self._get_word_image(word, img_area_w, img_area_h)
            text_h = sum(line.get_height() for line in lines) + gap * max(0, len(lines) - 1)
            content_h = (img.get_height() + gap if img is not None else 0) + text_h
            # 뜻(마지막 줄)이 타일 아래쪽 끝에 너무 붙지 않도록 살짝 위로 치우쳐 배치.
            y = max(pad, (th - content_h) // 2 - 8)
            if img is not None:
                tile.blit(img, ((tw - img.get_width()) // 2, y))
                y += img.get_height() + gap
            for line in lines:
                tile.blit(line, ((tw - line.get_width()) // 2, y))
                y += line.get_height() + gap
        else:
            pad = 20
            img_slot = th - pad * 2
            img = self._get_word_image(word, img_slot, img_slot)
            text_x0, text_w = 0, tw
            if img is not None:
                img_y = (th - img.get_height()) // 2
                tile.blit(img, (pad + (img_slot - img.get_width()) // 2, img_y))
                text_x0 = pad + img_slot + 16
                text_w = tw - text_x0 - pad

            gap = 16
            total_h = sum(line.get_height() for line in lines) + gap * max(0, len(lines) - 1)
            # 뜻(마지막 줄)이 타일 아래쪽 끝에 너무 붙지 않도록 살짝 위로 치우쳐 배치.
            y = max(0, (th - total_h) // 2 - 10)
            for line in lines:
                lx = text_x0 + max(0, (text_w - line.get_width()) // 2)
                tile.blit(line, (lx, y))
                y += line.get_height() + gap

        scaled = _scaled_surface(tile, max(0.05, scale))
        scaled.set_alpha(alpha)
        surface.blit(scaled, (center[0] - scaled.get_width() // 2, center[1] - scaled.get_height() // 2))

    def _draw_sentence_card(
        self,
        surface: pygame.Surface,
        sentence: ComposeSentenceInfo,
        *,
        center: tuple[int, int],
        timer_sec: float,
    ) -> None:
        """4단 결과 단어 활용 문장 카드(병음/문장/뜻) — shorts_plan.md 4단 자리를 대체.

        결과 단어 자체 내레이션(뜻+발음)이 끝나고 잠시 쉰 뒤(card_start)에야
        등장한다. 병음·문장 줄은 문장(중국어) TTS 재생 길이에 비례한 가라오케
        워프로 좌→우 하이라이트된다(회화모드 karaoke_wipe 재사용 — 음절 단위
        정밀 타이밍은 아니고 재생 길이 비례). 폰트는 테두리 없이 단색이고,
        카드 자체엔 두꺼운 다크 테두리 + 하드 섀도로 대비를 확보한다.
        """
        if timer_sec < sentence.card_start or not sentence.sentence_zh:
            return
        if self._font_sentence_pinyin is None or self._font_sentence_hanzi is None:
            return
        t = timer_sec - sentence.card_start
        _, alpha = _fade_scale_alpha(t, in_sec=SENTENCE_CARD_FADE_IN_SEC)
        if alpha <= 0:
            return
        scale = _ease_out_back(min(1.0, t / SENTENCE_CARD_BOUNCE_WINDOW_SEC))
        progress = compute_karaoke_progress(timer_sec - sentence.zh_start, sentence.zh_duration)

        pp = get_pinyin_processor()
        pinyin_text = pp.full_convert(sentence.sentence_zh) if pp.available else ""
        pinyin_active = (
            self._font_sentence_pinyin.render(pinyin_text, True, SENTENCE_PINYIN_COLOR)
            if pinyin_text
            else None
        )
        hanzi_active = self._font_sentence_hanzi.render(
            sentence.sentence_zh, True, SENTENCE_HANZI_ACTIVE_COLOR
        )

        translation_surf = None
        if sentence.translation_ko and self._font_sentence_translation is not None:
            translation_surf = self._font_sentence_translation.render(
                sentence.translation_ko, True, SENTENCE_TRANSLATION_COLOR
            )

        lines = [s for s in (pinyin_active, hanzi_active, translation_surf) if s is not None]
        if not lines:
            return
        row_w = max(s.get_width() for s in lines)
        row_h = sum(s.get_height() for s in lines) + SENTENCE_LINE_GAP * max(0, len(lines) - 1)

        pad_x, pad_y = 38, 26
        band_w = row_w + pad_x * 2
        band_h = row_h + pad_y * 2

        band = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
        pygame.draw.rect(band, SENTENCE_CARD_BG_COLOR, band.get_rect(), border_radius=22)
        pygame.draw.rect(
            band,
            SENTENCE_CARD_BORDER_COLOR,
            band.get_rect(),
            width=SENTENCE_CARD_BORDER_WIDTH,
            border_radius=22,
        )

        y = pad_y
        cx_band = band_w // 2
        if pinyin_active is not None:
            # 병음은 가라오케 워프 없이 항상 완성된 색으로 표시 — 한자 줄에서만 재생
            # 진행에 맞춰 좌→우로 하이라이트한다.
            band.blit(pinyin_active, (cx_band - pinyin_active.get_width() // 2, y))
            y += pinyin_active.get_height() + SENTENCE_LINE_GAP
        if hanzi_active is not None:
            hanzi_inactive = hanzi_active.copy()
            hanzi_inactive.set_alpha(SENTENCE_KARAOKE_INACTIVE_ALPHA)
            blit_horizontal_karaoke_wipe(
                band, hanzi_inactive, hanzi_active, center_x=cx_band, y=y, progress=progress
            )
            y += hanzi_active.get_height() + SENTENCE_LINE_GAP
        if translation_surf is not None:
            band.blit(translation_surf, (cx_band - translation_surf.get_width() // 2, y))

        shadow = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
        pygame.draw.rect(shadow, SENTENCE_CARD_SHADOW_COLOR, shadow.get_rect(), border_radius=22)

        composed = pygame.Surface(
            (band_w + SENTENCE_CARD_SHADOW_OFFSET[0], band_h + SENTENCE_CARD_SHADOW_OFFSET[1]),
            pygame.SRCALPHA,
        )
        composed.blit(shadow, SENTENCE_CARD_SHADOW_OFFSET)
        composed.blit(band, (0, 0))

        scaled = _scaled_surface(composed, max(0.05, scale))
        scaled.set_alpha(alpha)
        surface.blit(
            scaled, (center[0] - scaled.get_width() // 2, center[1] - scaled.get_height() // 2)
        )

    def _draw_result_seal(
        self,
        surface: pygame.Surface,
        word: Any,
        meaning: str,
        center: tuple[int, int],
        elapsed_since_impact: float,
        *,
        pinyin_alpha: int,
        meaning_alpha: int,
    ) -> None:
        """결과 카드 — 좌측 사진 + 우측 큰 한자, 그 아래 병음·뜻을 한 카드 안에 붙여서
        임팩트 때 전부 같은 바운스·회전으로 한 번에 튀어나오게 한다.

        병음·뜻은 항상 같은 자리를 차지하도록 미리 렌더해두고 알파만 0으로 시작한다
        (등장 시점에 따라 카드 크기 자체가 바뀌면 "커졌다 작아지는" 것처럼 보이는
        문제가 있었음 — 카드 크기는 임팩트 시점부터 끝까지 고정).
        """
        settle_alpha = int(60 * min(1.0, max(0.0, 1.0 - elapsed_since_impact / 1.5)) + 40)
        draw_seal_glow(surface, center, radius=240, alpha=settle_alpha)
        draw_impact_ring(surface, center, elapsed_since_impact, max_radius=230.0)
        particles = _spawn_particles(int(getattr(word, "id", 0) or 0))
        draw_particle_burst(surface, center, particles, elapsed_since_impact)

        bounce_window = 0.5
        t = min(1.0, elapsed_since_impact / bounce_window)
        scale = stamp_bounce_scale(t)
        rotation = stamp_bounce_rotation_deg(t)
        if self._font_result_hanzi is None:
            return

        pad = RESULT_CARD_PAD
        img = self._get_word_image(word, RESULT_IMAGE_SIZE, RESULT_IMAGE_SIZE)
        hz = self._font_result_hanzi.render(str(getattr(word, "word", "")), True, MEANING_COLOR)

        photo_w = RESULT_IMAGE_SIZE if img is not None else 0
        gap = RESULT_CARD_GAP if img is not None else 0
        top_row_h = max(RESULT_IMAGE_SIZE if img is not None else 0, hz.get_height())
        hanzi_zone_w = hz.get_width() + 32

        pinyin_text = _resolve_pinyin_display(word).strip()
        pinyin_surf: pygame.Surface | None = None
        if pinyin_text and self._font_result_pinyin is not None:
            pinyin_surf = self._font_result_pinyin.render(
                pinyin_text, True, RESULT_PINYIN_COLOR
            )
            pinyin_surf.set_alpha(pinyin_alpha)

        meaning_surf: pygame.Surface | None = None
        if meaning and self._font_result_meaning is not None:
            meaning_surf = self._font_result_meaning.render(meaning, True, MEANING_COLOR)
            meaning_surf.set_alpha(meaning_alpha)

        bottom_h = 0
        if pinyin_surf is not None:
            bottom_h += pinyin_surf.get_height()
        if meaning_surf is not None:
            bottom_h += (RESULT_CARD_ROW_GAP if pinyin_surf is not None else 0) + meaning_surf.get_height()
        bottom_inset = 18 if bottom_h else 0

        card_w = pad * 2 + photo_w + gap + hanzi_zone_w
        card_h = pad * 2 + top_row_h + bottom_inset + bottom_h

        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        pygame.draw.rect(card, (*SEAL_COLOR, 235), card.get_rect(), border_radius=26)

        if bottom_h:
            band_pad = 14
            band_rect = pygame.Rect(
                band_pad,
                pad + top_row_h + bottom_inset - band_pad,
                card_w - band_pad * 2,
                bottom_h + band_pad * 2 - 6,
            )
            band = pygame.Surface(band_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(band, (0, 0, 0, 70), band.get_rect(), border_radius=14)
            card.blit(band, band_rect.topleft)

        x = pad
        if img is not None:
            frame_pad = 6
            frame = pygame.Surface(
                (img.get_width() + frame_pad * 2, img.get_height() + frame_pad * 2), pygame.SRCALPHA
            )
            pygame.draw.rect(frame, TILE_BG_COLOR, frame.get_rect(), border_radius=18)
            frame.blit(img, (frame_pad, frame_pad))
            card.blit(frame, (x, pad + (top_row_h - frame.get_height()) // 2))
            x += photo_w + gap
        card.blit(hz, (x + (hanzi_zone_w - hz.get_width()) // 2, pad + (top_row_h - hz.get_height()) // 2))

        y = pad + top_row_h + bottom_inset
        if pinyin_surf is not None:
            card.blit(pinyin_surf, (card_w // 2 - pinyin_surf.get_width() // 2, y))
            y += pinyin_surf.get_height() + RESULT_CARD_ROW_GAP
        if meaning_surf is not None:
            card.blit(meaning_surf, (card_w // 2 - meaning_surf.get_width() // 2, y))

        composite = pygame.transform.rotozoom(card, rotation, max(0.05, scale))
        surface.blit(
            composite,
            (center[0] - composite.get_width() // 2, center[1] - composite.get_height() // 2),
        )

    # -- 트레이(누적 칩) ---------------------------------------------------
    def _build_tray_chip(self, word: Any) -> pygame.Surface | None:
        if word is None or self._font_tray is None:
            return None
        text = self._font_tray.render(str(getattr(word, "word", "")), True, MEANING_COLOR)
        chip = pygame.Surface((text.get_width() + 40, TRAY_CHIP_H), pygame.SRCALPHA)
        pygame.draw.rect(chip, TRAY_CHIP_BG, chip.get_rect(), border_radius=TRAY_CHIP_H // 2)
        pygame.draw.rect(
            chip, TRAY_CHIP_BORDER, chip.get_rect(), width=2, border_radius=TRAY_CHIP_H // 2
        )
        chip.blit(text, (20, TRAY_CHIP_H // 2 - text.get_height() // 2))
        return chip

    def _tray_row_positions(
        self, chips: list[pygame.Surface], surface_width: int, y: int
    ) -> list[tuple[int, int]]:
        total_w = sum(c.get_width() for c in chips) + TRAY_CHIP_GAP * (len(chips) - 1)
        x = surface_width // 2 - total_w // 2
        positions: list[tuple[int, int]] = []
        for chip in chips:
            positions.append((x, y))
            x += chip.get_width() + TRAY_CHIP_GAP
        return positions

    def _draw_tray_scene(
        self,
        surface: pygame.Surface,
        tray_word_ids: list[int],
        incoming_word_id: int,
        words_by_id: dict[int, Any],
        *,
        timer_sec: float,
        result_center: tuple[int, int],
        tray_slide_sec: float,
    ) -> None:
        """트레이 — 이전 B 완성 칩은 진입과 동시에(shorts_plan §3), 현재 B 완성 칩은 tray_slide_sec에 슥 이동.

        기존 칩과 현재 칩의 최종 위치를 한 번에 계산해야 진입 시점에 표시되는
        기존 칩 위치와, 슬라이드가 도착하는 위치가 어긋나지 않는다.
        """
        w, h = surface.get_size()
        existing_ids = list(tray_word_ids)
        incoming = self._build_tray_chip(words_by_id.get(incoming_word_id))
        full_ids = existing_ids + ([incoming_word_id] if incoming is not None else [])
        full_chips = [self._build_tray_chip(words_by_id.get(wid)) for wid in full_ids]
        full_chips = [c for c in full_chips if c is not None]
        if not full_chips:
            return
        y = int(h * 0.9)
        positions = self._tray_row_positions(full_chips, w, y)

        _, existing_alpha = _fade_scale_alpha(timer_sec, in_sec=0.35)
        if existing_alpha > 0:
            for chip, (x, cy) in zip(full_chips[: len(existing_ids)], positions):
                drawn = chip.copy()
                drawn.set_alpha(existing_alpha)
                surface.blit(drawn, (x, cy))

        if incoming is None or timer_sec < tray_slide_sec:
            return
        slide_elapsed = timer_sec - tray_slide_sec
        target_x, target_y = positions[-1]
        target_center = (target_x + incoming.get_width() / 2, target_y + incoming.get_height() / 2)
        t = _ease_out_quad(min(1.0, slide_elapsed / TRAY_SLIDE_ANIM_SEC))
        cx = result_center[0] + (target_center[0] - result_center[0]) * t
        cy = result_center[1] + (target_center[1] - result_center[1]) * t
        alpha = int(255 * min(1.0, slide_elapsed / (TRAY_SLIDE_ANIM_SEC * 0.6)))
        if alpha <= 0:
            return
        drawn = incoming.copy()
        drawn.set_alpha(alpha)
        surface.blit(drawn, (cx - drawn.get_width() / 2, cy - drawn.get_height() / 2))
