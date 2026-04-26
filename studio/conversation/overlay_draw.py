"""일시정지 라벨·디버그(FPS/PTS/오디오) 오버레이."""
from __future__ import annotations

from typing import Any

import pygame


def draw_paused_and_debug(studio: Any, screen: Any, config: Any) -> None:
    """일시정지 라벨 및 디버그 오버레이."""
    if studio._video_player.is_paused():
        if studio._paused_label is None:
            font_kr = studio._font_kr or pygame.font.Font(None, 36)
            studio._paused_label = font_kr.render("일시정지", True, (255, 255, 0))
        if studio._paused_label is not None:
            px, py = config.get_pos(0.08, 0.05)
            screen.blit(studio._paused_label, (px, py))

    actual_fps = getattr(config, "actual_fps", 0.0)
    if actual_fps >= 0:
        font_kr = studio._font_kr or pygame.font.Font(None, 28)
        vid_fps = studio._video_player.get_fps()
        pts = studio._video_player.get_pts()
        manager = getattr(studio, "_manager", None)
        scene_kind = None
        stage_text = "n/a"
        main_id_text = "—"
        item_idx_text = "— / —"
        if manager is not None:
            scene_kind = getattr(getattr(manager, "state", None), "scene_kind", None)
            st = getattr(manager, "state", None)
            if st is not None and hasattr(st, "item_index"):
                idx = int(getattr(st, "item_index", 0) or 0)
                items = getattr(manager, "_items", None) or []
                n = len(items) if items else 0
                item_idx_text = f"{idx + 1} / {n}" if n else f"{idx + 1} / 0"
                if items and 0 <= idx < len(items):
                    mid = items[idx].get("id")
                    main_id_text = str(mid) if mid is not None else "—"
            current_scene = None
            try:
                current_scene = manager._scenes.get(scene_kind)  # noqa: SLF001
            except Exception:
                current_scene = None
            # FSM 기반 Scene(LearningScene 등)면 현재 내부 Stage 이름을 디버그 라인에 노출한다.
            stage_obj = getattr(current_scene, "stage", None) if current_scene is not None else None
            if stage_obj is not None:
                stage_text = str(getattr(stage_obj, "name", stage_obj))
        scene_text = str(getattr(scene_kind, "value", scene_kind or "unknown"))
        audio_status = studio._video_audio.get_status()
        audio_pos = studio._video_audio.get_position_sec()
        if audio_pos is not None:
            sync_drift = pts - audio_pos
            lines = [
                f"FPS: {actual_fps:.1f}",
                f"Video FPS: {vid_fps:.1f}",
                f"PTS: {pts:.2f}s",
                f"Item index: {item_idx_text}",
                f"main id: {main_id_text}",
                f"SceneKind: {scene_text}",
                f"Stage: {stage_text}",
                f"Audio: {audio_status} | {audio_pos:.2f}s",
                f"Sync: {'+' if sync_drift >= 0 else ''}{sync_drift:.3f}s (vid−aud)",
            ]
        else:
            lines = [
                f"FPS: {actual_fps:.1f}",
                f"Video FPS: {vid_fps:.1f}",
                f"PTS: {pts:.2f}s",
                f"Item index: {item_idx_text}",
                f"main id: {main_id_text}",
                f"SceneKind: {scene_text}",
                f"Stage: {stage_text}",
                f"Audio: {audio_status}",
            ]
        y_debug = 8
        for line in lines:
            surf = font_kr.render(line, True, (0, 255, 128))
            screen.blit(surf, (8, y_debug))
            y_debug += 22
