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

from utils.fonts import attach_font_fgcolor, load_font_chinese, load_font_chinese_freetype, load_font_korean

from .constants import _REPO_ROOT
from .data_loading import build_data_list
from .overlay_draw import draw_paused_and_debug
from .video_players import SimpleVideoPlayer, VideoAudioPlayer

from .core.playback_manager import LastSceneSequencePolicy, PlaybackManager, SceneKind
from .core.types import ColorStyle, FrameContext, LayoutStyle, SentenceStyleConfig
from .execution.learning_scene import LearningScene
from .execution.practice_scene import PracticeScene
from .execution.video_scene import VideoScene
from .tools.common_drawer import CommonDrawer
from .tools.fonts import (
    AMBER,
    ConversationFontSizes,
    ConversationRenderSettings,
    DEFAULT_CONVERSATION_RENDER_SETTINGS,
    FontBundle,
    GRAY_MUTED,
    RED,
    WHITE,
)


logger = logging.getLogger(__name__)


class ConversationStudio:
    """회화 스튜디오: LoadedContent/CSV 기반 비디오 + 텍스트 표시."""

    def __init__(
        self,
        csv_path: str = "",
        content: Any = None,
        **_: Any,
    ) -> None:
        """CSV·콘텐츠로 재생 목록을 만들고, 비디오/오디오 플레이어를 준비한다."""
        self._csv_path = csv_path
        self._data_list = build_data_list(csv_path, content)
        self._render_settings: Optional[ConversationRenderSettings] = None

        self._video_player = SimpleVideoPlayer()
        # 기존 디버그 오버레이가 깨지지 않게 유지(로직은 최소)
        self._video_audio = VideoAudioPlayer()

        # 폰트 핸들은 init()에서 pygame 초기화 이후 로드
        # `_load_fonts`에서 채움. 크기별 용도는 init()의 FontBundle 주석과 동일.
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
        self._last_config: Any = None

        # 첫 아이템의 미디어 소스 적용
        if self._data_list:
            self._apply_media_for_index(0)

    # ------------------------------------------------------------------
    # IStudio methods
    # ------------------------------------------------------------------

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 한 번 호출. 폰트/3계층 객체 생성."""
        if self._drawer is not None and self._manager is not None:
            return
        self._last_config = config

        settings = self._resolve_render_settings(config)
        self._render_settings = settings

        _lsp = getattr(settings, "conversation_last_scene_sequence_policy", None)
        if _lsp is None:
            _lsp = getattr(settings, "conversation_last_step_sequence_policy", None)
        if isinstance(_lsp, LastSceneSequencePolicy):
            _last_scene_policy = _lsp
        elif isinstance(_lsp, str) and _lsp.strip().lower() in ("advance_item", "advance", "next_item"):
            _last_scene_policy = LastSceneSequencePolicy.ADVANCE_ITEM
        else:
            _last_scene_policy = LastSceneSequencePolicy.STAY

        learn_style, practice_style = self._load_fonts(settings.font_sizes)
        self._apply_font_fallbacks(settings.font_sizes)

        fs = settings.font_sizes
        fonts = FontBundle(
            hanzi_ft=self._font_cn_step1_ft or self._font_cn_big_ft,
            hanzi_pg=self._font_cn_big or pygame.font.Font(None, fs.cn_big),
            pinyin_ft=self._font_cn_step1_pinyin_ft or self._font_cn_ft,
            pinyin_pg=self._font_cn or pygame.font.Font(None, fs.cn),
            translation_pg=self._font_kr_step1 or self._font_kr or pygame.font.Font(None, fs.kr),
        )
        self._drawer = CommonDrawer(fonts=fonts)

        def _play_insert_voice(path: str, *, item: Any = None) -> None:
            """학습 단계 삽입 음성을 재생하고, 녹화 모드면 타임라인 이벤트로 남긴다."""
            _ = item
            if not path:
                return
            try:
                if pygame.mixer.get_init() is None:
                    pygame.mixer.init()
            except Exception:
                return
            try:
                snd = pygame.mixer.Sound(path)
            except Exception:
                return
            # mixer.music(VideoAudioPlayer)와 충돌 방지: 전용 채널 사용
            try:
                ch = pygame.mixer.Channel(1)
                ch.play(snd)
            except Exception:
                try:
                    snd.play()
                except Exception:
                    pass

            # record 모드면 이벤트도 남김(사후 mux용)
            cfg = self._last_config
            log = getattr(cfg, "recording_log_event", None)
            if log is None:
                return
            try:
                from studio.recording_events import InsertSound, recording_log_event
                timeline_sec = float(getattr(cfg, "recording_time_sec", 0.0) or 0.0)
                dur = float(getattr(snd, "get_length", lambda: 0.0)() or 0.0)
                recording_log_event(log, InsertSound(timeline_sec=timeline_sec, path=path, duration_sec=dur))
            except Exception:
                return

        _adv = str(getattr(settings, "learning_voice_advance", "immediate") or "immediate").lower()
        _wait_for_sound_end = _adv in ("after_sound", "sound_length", "wait_sound")

        scenes = {
            SceneKind.VIDEO: VideoScene(drawer=self._drawer, video_player=self._video_player),
            SceneKind.LEARNING: LearningScene(
                drawer=self._drawer,
                video_player=self._video_player,
                style=learn_style,
                hold_sec=float(getattr(settings, "learning_hold_sec", 2.0) or 2.0),
                play_voice=_play_insert_voice,
                title_text=str(getattr(settings, "learning_title_text", "학습") or "학습"),
                layer_channel_prefix=str(
                    getattr(settings, "learning_layer_channel_prefix", None) or "learning"
                ),
                stage_audio_keys=getattr(settings, "learning_stage_audio_keys", None),
                wait_for_sound_end=_wait_for_sound_end,
            ),
            SceneKind.PRACTICE: PracticeScene(
                drawer=self._drawer,
                video_player=self._video_player,
                style=practice_style,
            ),
        }
        # 컨텐츠(화면) 시퀀스:
        # - SceneKind.VIDEO: 비디오만 재생(프레임 표시)하는 화면
        # - SceneKind.LEARNING: 비디오 위에 문장(한자/병음/번역)을 출력하는 화면
        #
        # "다음 컨텐츠로 전환"은 각 ConversationStep이 transition_signal=True로 올리면 PlaybackManager가 감지해
        # 다음 SceneKind로 자동 전환한다.
        self._manager = PlaybackManager(
            items=self._data_list,
            scenes=scenes,
            video_player=self._video_player,
            scene_sequence=[SceneKind.VIDEO, SceneKind.LEARNING, SceneKind.PRACTICE],
            last_scene_sequence_policy=_last_scene_policy,
        )

    def get_title(self) -> str:
        """창 제목 표시용 문자열."""
        return "LVPD Studio - 회화"

    def handle_events(self, events: list, config: Any = None) -> bool:
        """키 입력으로 데이터·SceneKind(장면 종류)을 전환하는 최소 이벤트만 처리."""
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

            # SceneKind(장면) 전환
            if e.key in (pygame.K_1, pygame.K_KP1):
                self._manager.set_scene_kind(SceneKind.VIDEO)
                continue
            if e.key in (pygame.K_2, pygame.K_KP2):
                self._manager.set_scene_kind(SceneKind.LEARNING)
                continue
            if e.key in (pygame.K_3, pygame.K_KP3):
                self._manager.set_scene_kind(SceneKind.PRACTICE)
                continue

        return True

    def update(self, config: Any = None) -> None:
        """프레임당 dt·해상도 컨텍스트를 만들고 비디오 오디오·PlaybackManager를 갱신한다."""
        if self._manager is None:
            return
        self._last_config = config

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
        """배경 채우기 후 현재 Step 화면을 그리고 일시정지·디버그 오버레이를 덧씌운다."""
        bg = getattr(config, "bg_color", (20, 20, 25))
        screen.fill(bg)

        if self._manager is None:
            # 데이터가 없거나 init 전이면 안내 문구만 표시
            kr_sz = self._render_settings.font_sizes.kr if self._render_settings else 28
            font = self._font_kr or pygame.font.Font(None, kr_sz)
            msg = font.render("ConversationStudio: manager not initialized", True, (180, 180, 180))
            screen.blit(msg, (20, 20))
            return

        ctx = FrameContext(width=int(config.width), height=int(config.height), dt_sec=float(getattr(config, "dt_sec", 1.0 / 30.0)))
        self._manager.render(screen, ctx)
        draw_paused_and_debug(self, screen, config)

    def get_recording_prefix(self) -> Optional[str]:
        """녹화 파일명 접두사(현재 아이템 id 기준). 데이터 없으면 None."""
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
        """지정 인덱스 아이템의 비디오 경로·구간을 플레이어와 동기 추출 오디오에 반영한다."""
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

    def _resolve_render_settings(self, config: Any) -> ConversationRenderSettings:
        """`config.conversation_render`가 있으면 사용, 없으면 기본값."""
        if config is not None:
            cr = getattr(config, "conversation_render", None)
            if isinstance(cr, ConversationRenderSettings):
                return cr
        return DEFAULT_CONVERSATION_RENDER_SETTINGS

    def _load_fonts(
        self,
        font_sizes: ConversationFontSizes,
    ) -> tuple[SentenceStyleConfig, SentenceStyleConfig]:
        """폰트 로드(가능하면 freeType). 색은 `load_font_*` 두 번째 인자(RGB 튜플)로만."""

        fs = font_sizes
        # 색은 아래 RGB 튜플 상수(RED, WHITE, …)만 두 번째 인자로 넘긴다.
        self._font_cn_big = load_font_chinese(fs.cn_big, WHITE)
        self._font_cn = load_font_chinese(fs.cn, RED)
        self._font_cn_big_ft = load_font_chinese_freetype(fs.cn_big, WHITE)
        self._font_cn_ft = load_font_chinese_freetype(fs.cn, RED)
        self._font_cn_step1_ft = load_font_chinese_freetype(fs.cn_step1_hanzi, WHITE) or self._font_cn_big_ft
        self._font_cn_step1_pinyin_ft = load_font_chinese_freetype(fs.cn_step1_pinyin, RED) or self._font_cn_ft
        self._font_kr = load_font_korean(fs.kr, GRAY_MUTED)
        self._font_kr_step1 = load_font_korean(fs.kr_step1, GRAY_MUTED) or self._font_kr

        # 문장 렌더 색은 위 `load_font_*`에 넘긴 RGB와 동일한 상수로 맞춘다(연습 한자만 AMBER).
        trans_gap = 36
        learn_style = SentenceStyleConfig(
            colors=ColorStyle(hanzi_color=WHITE, pinyin_color=RED, translation_color=GRAY_MUTED),
            layout=LayoutStyle(translation_extra_gap_px=trans_gap),
        )
        practice_style = SentenceStyleConfig(
            colors=ColorStyle(hanzi_color=AMBER, pinyin_color=RED, translation_color=GRAY_MUTED),
            layout=LayoutStyle(translation_extra_gap_px=trans_gap),
        )
        return learn_style, practice_style

    def _apply_font_fallbacks(self, sizes: ConversationFontSizes) -> None:
        """폰트 미로드 시 기본 폰트로 폴백."""
        from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME

        if self._font_cn_big is None:
            self._font_cn_big = attach_font_fgcolor(pygame.font.Font(None, sizes.cn_big), WHITE)
            logger.warning(
                "중국어 폰트 미로드 → 기본 폰트 사용(중국어 네모 가능). 다음 경로에 %s 넣기: %s",
                FONT_CN_FILENAME,
                DEFAULT_FONT_DIR.resolve(),
            )
        if self._font_cn is None:
            self._font_cn = attach_font_fgcolor(pygame.font.Font(None, sizes.cn), RED)
        if self._font_kr is None:
            self._font_kr = attach_font_fgcolor(pygame.font.Font(None, sizes.kr), GRAY_MUTED)

