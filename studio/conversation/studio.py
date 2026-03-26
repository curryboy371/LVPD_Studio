"""회화 스튜디오(Conversation): pygame 러너용 IStudio 구현체.

목표: `studio/conversation` 내부를 '제어-실행-도구' 3계층으로 분리하고,
현재 단계(render)와 데이터(item)만으로 화면이 만들어지도록 단순화한다.

이번 범위(render_only):
- 복잡한 Step1 상태머신/사운드 스케줄링/페이드 등은 제거
- 데이터 주입 + 텍스트(한자/병음/번역) 출력이 안정적으로 되게 구성
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import pygame

from utils.fonts import load_font_chinese, load_font_chinese_freetype, load_font_korean

from .constants import _REPO_ROOT
from .data_loading import build_data_list
from .overlay_draw import draw_paused_and_debug
from .video_players import SimpleVideoPlayer, VideoAudioPlayer

from .core.playback_manager import PlaybackManager, StepKind
from .core.types import FrameContext
from .execution.learning_step import LearningStep
from .execution.practice_step import PracticeStep
from .execution.video_step import VideoStep
from .tools.common_drawer import CommonDrawer
from .tools.fonts import FontBundle


logger = logging.getLogger(__name__)


class ConversationStudio:
    """회화 스튜디오: LoadedContent/CSV 기반 비디오 + 텍스트 표시."""

    def __init__(self, csv_path: str = "", content: Any = None, **_: Any) -> None:
        self._csv_path = csv_path
        self._data_list = build_data_list(csv_path, content)

        self._video_player = SimpleVideoPlayer()
        # 기존 디버그 오버레이가 깨지지 않게 유지(로직은 최소)
        self._video_audio = VideoAudioPlayer()

        # 폰트 핸들은 init()에서 pygame 초기화 이후 로드
        self._font_cn_big: Optional[pygame.font.Font] = None
        self._font_cn: Optional[pygame.font.Font] = None
        self._font_cn_big_ft: Any = None
        self._font_cn_ft: Any = None
        self._font_cn_step1_ft: Any = None
        self._font_cn_step1_pinyin_ft: Any = None
        self._font_kr: Optional[pygame.font.Font] = None
        self._font_kr_step1: Optional[pygame.font.Font] = None

        self._paused_label: Optional[pygame.Surface] = None

        self._drawer: Optional[CommonDrawer] = None
        self._manager: Optional[PlaybackManager] = None

        # 첫 아이템의 미디어 소스 적용
        if self._data_list:
            self._apply_media_for_index(0)

    # ------------------------------------------------------------------
    # IStudio methods
    # ------------------------------------------------------------------

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 한 번 호출. 폰트/3계층 객체 생성."""
        _ = config
        if self._drawer is not None and self._manager is not None:
            return

        self._load_fonts()
        self._apply_font_fallbacks()

        fonts = FontBundle(
            hanzi_ft=self._font_cn_step1_ft or self._font_cn_big_ft,
            hanzi_pg=self._font_cn_big or pygame.font.Font(None, 36),
            pinyin_ft=self._font_cn_step1_pinyin_ft or self._font_cn_ft,
            pinyin_pg=self._font_cn or pygame.font.Font(None, 28),
            translation_pg=self._font_kr_step1 or self._font_kr or pygame.font.Font(None, 28),
        )
        self._drawer = CommonDrawer(fonts=fonts)

        steps = {
            StepKind.VIDEO: VideoStep(drawer=self._drawer, video_player=self._video_player),
            StepKind.LEARNING: LearningStep(drawer=self._drawer, video_player=self._video_player),
            StepKind.PRACTICE: PracticeStep(drawer=self._drawer, video_player=self._video_player),
        }
        # 컨텐츠(화면) 시퀀스:
        # - StepKind.VIDEO: 비디오만 재생(프레임 표시)하는 화면
        # - StepKind.LEARNING: 비디오 위에 문장(한자/병음/번역)을 출력하는 화면
        #
        # "다음 컨텐츠로 전환"은 각 Step이 transition_signal=True로 올리면 PlaybackManager가 감지해
        # 다음 StepKind로 자동 전환한다.
        self._manager = PlaybackManager(
            items=self._data_list,
            steps=steps,
            video_player=self._video_player,
            step_sequence=[StepKind.VIDEO, StepKind.LEARNING],
        )

    def get_title(self) -> str:
        return "LVPD Studio - 회화"

    def handle_events(self, events: list, config: Any = None) -> bool:
        """키 입력으로 데이터/step을 전환하는 최소 이벤트만 처리."""
        _ = config
        if self._manager is None:
            return True

        for e in events:
            if e.type != pygame.KEYDOWN:
                continue

            # item navigation
            if e.key == pygame.K_SPACE:
                self._manager.next_item()
                self._apply_media_for_index(self._manager.state.item_index)
                continue
            if e.key == pygame.K_b:
                self._manager.prev_item()
                self._apply_media_for_index(self._manager.state.item_index)
                continue

            # playback controls
            if e.key == pygame.K_p:
                self._manager.toggle_pause()
                if self._video_player.is_paused():
                    self._video_audio.pause()
                else:
                    self._video_audio.unpause()
                continue
            if e.key in (pygame.K_HOME, pygame.K_r):
                self._manager.restart_segment()
                st = float(self._manager.current_item().get("start_time", 0.0) or 0.0)
                self._video_audio.seek_to(st)
                self._video_audio.unpause()
                continue
            if e.key in (pygame.K_LEFT, pygame.K_j):
                self._manager.seek(-5.0)
                self._video_audio.seek_to(self._video_player.get_pts())
                if self._video_player.is_paused():
                    self._video_audio.pause()
                continue
            if e.key in (pygame.K_RIGHT, pygame.K_l):
                self._manager.seek(5.0)
                self._video_audio.seek_to(self._video_player.get_pts())
                if self._video_player.is_paused():
                    self._video_audio.pause()
                continue

            # step switching
            if e.key in (pygame.K_1, pygame.K_KP1):
                self._manager.set_step(StepKind.VIDEO)
                continue
            if e.key in (pygame.K_2, pygame.K_KP2):
                self._manager.set_step(StepKind.LEARNING)
                continue
            if e.key in (pygame.K_3, pygame.K_KP3):
                self._manager.set_step(StepKind.PRACTICE)
                continue

        return True

    def update(self, config: Any = None) -> None:
        if self._manager is None:
            return

        dt = 1.0 / 30.0
        if config is not None and getattr(config, "dt_sec", None) is not None:
            dt = float(config.dt_sec)
        width = int(getattr(config, "width", 1280))
        height = int(getattr(config, "height", 720))
        ctx = FrameContext(width=width, height=height, dt_sec=dt)

        # 오디오 추출이 pending이면 적용(기존 VideoAudioPlayer 동작 유지)
        try:
            if self._video_audio.has_pending():
                self._video_audio._apply_pending()
        except Exception:
            pass

        self._manager.update(ctx)

    def draw(self, screen: Any, config: Any) -> None:
        bg = getattr(config, "bg_color", (20, 20, 25))
        screen.fill(bg)

        if self._manager is None:
            # 데이터가 없거나 init 전이면 안내 문구만 표시
            font = self._font_kr or pygame.font.Font(None, 28)
            msg = font.render("ConversationStudio: manager not initialized", True, (180, 180, 180))
            screen.blit(msg, (20, 20))
            return

        ctx = FrameContext(width=int(config.width), height=int(config.height), dt_sec=float(getattr(config, "dt_sec", 1.0 / 30.0)))
        self._manager.render(screen, ctx)
        draw_paused_and_debug(self, screen, config)

    def get_recording_prefix(self) -> Optional[str]:
        if not self._data_list:
            return None
        idx = self._manager.state.item_index if self._manager is not None else 0
        idx = max(0, min(len(self._data_list) - 1, idx))
        item = self._data_list[idx]
        vid = item.get("id", 0)
        return f"REC_{vid}"

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _apply_media_for_index(self, index: int) -> None:
        if not self._data_list or index < 0 or index >= len(self._data_list):
            return
        item = self._data_list[index]
        path = self._resolve_video_path(str(item.get("video_path") or ""))
        st = float(item.get("start_time", 0.0) or 0.0)
        et_raw = item.get("end_time", -1.0)
        et = float(et_raw) if et_raw not in (None, "") else -1.0
        self._video_player.set_source(path, st, et)
        self._video_audio.set_source(path, st)

    def _resolve_video_path(self, path: str) -> str:
        """상대 경로는 repo 루트 기준으로 해석."""
        path = (path or "").strip()
        if not path:
            return ""
        if os.path.isabs(path):
            return path
        resolved = _REPO_ROOT / path.replace("\\", "/")
        return str(resolved)

    def _load_fonts(self) -> None:
        """폰트 로드 (가능하면 freeType 사용)."""
        self._font_cn_big = load_font_chinese(36)
        self._font_cn = load_font_chinese(28)
        self._font_cn_big_ft = load_font_chinese_freetype(36)
        self._font_cn_ft = load_font_chinese_freetype(28)
        self._font_cn_step1_ft = load_font_chinese_freetype(124) or self._font_cn_big_ft
        self._font_cn_step1_pinyin_ft = load_font_chinese_freetype(66) or self._font_cn_ft
        self._font_kr = load_font_korean(28)
        self._font_kr_step1 = load_font_korean(56) or self._font_kr

    def _apply_font_fallbacks(self) -> None:
        """폰트 미로드 시 기본 폰트로 폴백."""
        from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME

        if self._font_cn_big is None:
            self._font_cn_big = pygame.font.Font(None, 36)
            logger.warning(
                "중국어 폰트 미로드 → 기본 폰트 사용(중국어 네모 가능). 다음 경로에 %s 넣기: %s",
                FONT_CN_FILENAME,
                DEFAULT_FONT_DIR.resolve(),
            )
        if self._font_cn is None:
            self._font_cn = pygame.font.Font(None, 28)
        if self._font_kr is None:
            self._font_kr = pygame.font.Font(None, 28)

