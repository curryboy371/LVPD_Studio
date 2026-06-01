"""단어 외우기 모드 — word box 배치 편집기 (FHD 좌표, 9:16 미리보기)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Literal

from core.paths import SHORTS_HEIGHT, SHORTS_WIDTH, get_repo_root
from extra.table_editor.services.word_lookup import lookup_word_details
from extra.table_editor.services.word_memorize_grid import (
    MIN_USABLE_HEIGHT,
    apply_grid_layout,
)
from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LAYOUTS_DIR,
    WordMemorizeBox,
    WordMemorizeLayout,
    box_overlaps_any,
    find_non_overlapping_position,
    layout_has_overlaps,
    load_layout,
    save_layout,
)
from extra.table_editor.ui.word_memorize_vocab_import_dialog import (
    WordMemorizeVocabImportDialog,
)
from extra.table_editor.ui.word_memorize_word_pick_dialog import (
    WordMemorizeWordPickDialog,
)
from extra.table_editor.services.shorts_editor_choices import (
    BG_PATH_RANDOM_LABEL,
    bg_path_for_combo,
    bg_path_from_combo,
    list_bg_path_choices,
    normalize_vocab_bg_path,
)
from extra.table_editor.ui.shorts_bg_path_preview import (
    ShortsBgPathPreviewPlayer,
    attach_bg_path_preview,
)
from extra.table_editor.ui.window_placement import schedule_center_toplevel_on_parent

# 미리보기 캔버스 (9:16 — 세로는 1080p 화면에 맞춤)
PREVIEW_WIDTH = 504
PREVIEW_HEIGHT = 896
SCALE = PREVIEW_WIDTH / float(SHORTS_WIDTH)

SIDEBAR_WIDTH = 360
WINDOW_WIDTH = 1320
WINDOW_HEIGHT = 1000
LISTBOX_HEIGHT_HOLDING = 5
LISTBOX_HEIGHT_DISPLAY = 6
_SCREEN_MARGIN_Y = 48

MIN_BOX_W = 80
MIN_BOX_H = 60
DEFAULT_BOX_W = 280
DEFAULT_BOX_H = 160
HANDLE_HIT = 12
HANDLE_DRAW = 8

BOX_PINYIN_FONT = ("Noto Sans SC", 13)
BOX_HANZI_FONT = ("Noto Sans SC", 18, "bold")
BOX_EN_FONT = ("Segoe UI", 10)
BOX_BADGE_FONT = ("Segoe UI", 11, "bold")
BOX_PINYIN_COLOR = "#c62828"
BOX_HANZI_COLOR = "#212121"
BOX_EN_COLOR = "#4caf50"
BOX_CONTENT_PAD = 8
BOX_LINE_GAP = 3
BOX_IMG_BOTTOM_PAD = 6
BOX_IMG_LIFT = 12
BOX_IMG_MAX_RATIO = 0.42

GUIDE_LINE_COLOR = "#6a7588"
GUIDE_LINE_DASH = (5, 7)
GUIDE_BAND_STIPPLE = "gray25"
GUIDE_BAND_FILL = "#8899aa"

MARGIN_RAIL_WIDTH = 56
MARGIN_HANDLE_HIT = 12
MARGIN_RAIL_BAND_FILL = "#b0bec5"
MARGIN_RAIL_CONTENT_FILL = "#e8f5e9"
MARGIN_RAIL_HANDLE_COLOR = "#1565c0"
MARGIN_RAIL_HANDLE_WIDTH = 40
# Windows Tk: sb_v_resize 미지원 — 후보 순서대로 시도
_MARGIN_DRAG_CURSOR_CANDIDATES = ("size_ns", "sb_v_double_arrow", "exchange", "arrow")


def _try_configure_cursor(widget: tk.Widget, names: tuple[str, ...]) -> None:
    for name in names:
        try:
            widget.configure(cursor=name)
            return
        except tk.TclError:
            continue


ResizeHandle = Literal[
    "nw", "n", "ne", "e", "se", "s", "sw", "w", "move", ""
]
MarginDragMode = Literal["", "top", "bottom"]

_active_editor: WordMemorizeLayoutEditorWindow | None = None


def open_word_memorize_layout_editor(parent: tk.Misc) -> None:
    global _active_editor
    if _active_editor is not None:
        try:
            if _active_editor.winfo_exists():
                _active_editor.lift()
                _active_editor.focus_force()
                return
        except tk.TclError:
            _active_editor = None
    _active_editor = WordMemorizeLayoutEditorWindow(parent)


class WordMemorizeLayoutEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("단어 외우기 — 배치 편집")
        self.transient(parent.winfo_toplevel())
        self._layout = WordMemorizeLayout()
        self._file_path: str | None = None
        self._selected_key: str | None = None
        self._drag_mode: ResizeHandle = ""
        self._drag_start: tuple[int, int] | None = None
        self._drag_box_snapshot: WordMemorizeBox | None = None
        self._next_box_num = 1
        self._box_photos: dict[str, object] = {}
        self._dirty = False
        self._margin_drag: MarginDragMode = ""

        self._build_ui()
        self._redraw_canvas()
        self._refresh_holding_list()
        self._refresh_order_list()
        self._update_window_title()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._place_center_on_screen()
        self.after_idle(self._place_center_on_screen)

    def _place_center_on_screen(self) -> None:
        """화면 중앙에 배치 (작은 모니터는 높이를 화면에 맞춤)."""
        self.update_idletasks()
        w = WINDOW_WIDTH
        h = min(WINDOW_HEIGHT, self.winfo_screenheight() - _SCREEN_MARGIN_Y)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(1100, w), min(760, h))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        hint = ttk.Label(
            root,
            text=(
                f"좌표·크기는 FHD {SHORTS_WIDTH}×{SHORTS_HEIGHT} 기준 · "
                f"미리보기 {PREVIEW_WIDTH}×{PREVIEW_HEIGHT} (9:16) · "
                "박스끼리 겹침 불가 · 우측 띠=상·하 여백 드래그"
            ),
            foreground="#555",
        )
        hint.pack(anchor="w", pady=(0, 6))

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="새 배치", command=self._new_layout).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=2
        )
        ttk.Button(toolbar, text="불러오기…", command=self._open).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="저장", command=self._save).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="다른 이름으로 저장…", command=self._save_as).pack(
            side=tk.LEFT, padx=4
        )
        self.bind("<Control-o>", lambda _e: self._open())
        self.bind("<Control-s>", lambda _e: self._save())
        self.bind("<Control-Shift-S>", lambda _e: self._save_as())

        body = ttk.Frame(root)
        body.pack(fill=tk.BOTH, expand=True)

        sidebar = ttk.LabelFrame(body, text="Word box", width=SIDEBAR_WIDTH)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)

        btn_col = ttk.Frame(sidebar)
        btn_col.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_col, text="추가 (검색)", command=self._add_box).pack(
            fill=tk.X, pady=3
        )
        ttk.Button(
            btn_col,
            text="단어장에서 가져오기…",
            command=self._open_vocab_import,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(btn_col, text="선택 삭제", command=self._delete_selected).pack(
            fill=tk.X, pady=3
        )
        ttk.Button(
            btn_col,
            text="선택한 크기로 전부 맞추기",
            command=self._match_all_to_selected_size,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(btn_col, text="배경 설정", command=self._edit_background).pack(
            fill=tk.X, pady=3
        )

        bg_music_frame = ttk.LabelFrame(sidebar, text="쇼츠 배경음")
        bg_music_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        bg_music_in = ttk.Frame(bg_music_frame)
        bg_music_in.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(
            bg_music_in,
            text="resource/sound/bg_short",
            foreground="#555",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))
        self._bg_music_var = tk.StringVar(value=BG_PATH_RANDOM_LABEL)
        bg_choices = [BG_PATH_RANDOM_LABEL] + list_bg_path_choices()
        self._bg_music_combo = ttk.Combobox(
            bg_music_in,
            textvariable=self._bg_music_var,
            values=bg_choices,
            state="readonly",
            width=28,
        )
        self._bg_music_combo.pack(fill=tk.X, pady=(0, 4))
        self._bg_music_combo.bind(
            "<<ComboboxSelected>>", self._on_bg_music_combo_changed, add="+"
        )
        bg_preview_row = ttk.Frame(bg_music_in)
        bg_preview_row.pack(fill=tk.X)
        attach_bg_path_preview(bg_preview_row, self._bg_music_combo).pack(side=tk.LEFT)
        self._sync_bg_music_combo()

        grid_frame = ttk.LabelFrame(sidebar, text="격자 정렬")
        grid_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        grid_in = ttk.Frame(grid_frame)
        grid_in.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(grid_in, text="행").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._grid_rows_var = tk.StringVar(value="3")
        ttk.Spinbox(
            grid_in,
            from_=1,
            to=20,
            width=4,
            textvariable=self._grid_rows_var,
        ).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(grid_in, text="열").grid(row=0, column=2, sticky="w", padx=(0, 4))
        self._grid_cols_var = tk.StringVar(value="3")
        ttk.Spinbox(
            grid_in,
            from_=1,
            to=20,
            width=4,
            textvariable=self._grid_cols_var,
        ).grid(row=0, column=3)
        ttk.Button(
            grid_frame,
            text="격자 정렬",
            command=lambda: self._apply_grid_align(uniform=False),
        ).pack(fill=tk.X, padx=6, pady=(0, 3))
        ttk.Button(
            grid_frame,
            text="균일하게 정렬",
            command=lambda: self._apply_grid_align(uniform=True),
        ).pack(fill=tk.X, padx=6, pady=(0, 6))

        holding_frame = ttk.LabelFrame(sidebar, text="보관함 (미표시)")
        holding_frame.pack(fill=tk.X, expand=False, padx=8, pady=(0, 4))
        hold_wrap = ttk.Frame(holding_frame)
        hold_wrap.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._holding_list = tk.Listbox(
            hold_wrap,
            height=LISTBOX_HEIGHT_HOLDING,
            exportselection=False,
            selectmode=tk.EXTENDED,
            font=("Segoe UI", 10),
        )
        hold_scroll = ttk.Scrollbar(
            hold_wrap, orient=tk.VERTICAL, command=self._holding_list.yview
        )
        self._holding_list.configure(yscrollcommand=hold_scroll.set)
        self._holding_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hold_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._holding_list.bind(
            "<Double-Button-1>", lambda _e: self._move_holding_to_display()
        )

        transfer_row = ttk.Frame(sidebar)
        transfer_row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(
            transfer_row,
            text="▼ 표시에 넣기",
            command=self._move_holding_to_display,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            transfer_row,
            text="▲ 보관함으로",
            command=self._move_display_to_holding,
        ).pack(fill=tk.X, pady=2)

        order_frame = ttk.LabelFrame(sidebar, text="표시 — 캔버스 (order)")
        order_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        list_wrap = ttk.Frame(order_frame)
        list_wrap.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._order_list = tk.Listbox(
            list_wrap,
            height=LISTBOX_HEIGHT_DISPLAY,
            exportselection=False,
            selectmode=tk.EXTENDED,
            font=("Segoe UI", 10),
        )
        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self._order_list.yview)
        self._order_list.configure(yscrollcommand=scroll.set)
        self._order_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._order_list.bind("<<ListboxSelect>>", self._on_order_list_select)
        self._order_list.bind(
            "<Double-Button-1>", lambda _e: self._move_display_to_holding()
        )

        order_btns = ttk.Frame(order_frame)
        order_btns.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Button(order_btns, text="▲", width=4, command=self._move_order_up).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(order_btns, text="▼", width=4, command=self._move_order_down).pack(
            side=tk.LEFT, padx=2
        )

        self._path_var = tk.StringVar(value="(새 배치 — 저장 전)")
        ttk.Label(
            sidebar,
            textvariable=self._path_var,
            wraplength=SIDEBAR_WIDTH - 24,
            foreground="#444",
        ).pack(fill=tk.X, padx=8, pady=(0, 8))

        preview_host = ttk.LabelFrame(body, text="9:16 미리보기")
        preview_host.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        preview_row = ttk.Frame(preview_host)
        preview_row.pack(padx=8, pady=8)

        self._canvas = tk.Canvas(
            preview_row,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            highlightthickness=1,
            highlightbackground="#888",
            bg="#222",
            cursor="arrow",
        )
        self._canvas.pack(side=tk.LEFT)
        self._canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self._canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        rail_wrap = ttk.Frame(preview_row)
        rail_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        ttk.Label(
            rail_wrap,
            text="여백",
            font=("Segoe UI", 9),
            foreground="#555",
        ).pack(anchor="n")
        self._margin_rail = tk.Canvas(
            rail_wrap,
            width=MARGIN_RAIL_WIDTH,
            height=PREVIEW_HEIGHT,
            highlightthickness=1,
            highlightbackground="#aaa",
            bg="#eceff1",
            cursor="arrow",
        )
        self._margin_rail.pack(anchor="n")
        self._margin_rail.bind("<ButtonPress-1>", self._on_margin_rail_press)
        self._margin_rail.bind("<B1-Motion>", self._on_margin_rail_motion)
        self._margin_rail.bind("<ButtonRelease-1>", self._on_margin_rail_release)
        self._margin_label_var = tk.StringVar()
        ttk.Label(
            rail_wrap,
            textvariable=self._margin_label_var,
            font=("Segoe UI", 8),
            foreground="#666",
            wraplength=MARGIN_RAIL_WIDTH + 8,
        ).pack(anchor="n", pady=(4, 0))
        self._update_margin_label()
        self._draw_margin_rail()

    def _fhd_to_screen(self, x: int, y: int) -> tuple[int, int]:
        return int(round(x * SCALE)), int(round(y * SCALE))

    def _guide_y_fhd(self) -> tuple[int, int]:
        """FHD Y: 상·하단 비권장 구역 경계."""
        fh = self._layout.frame_height
        y_top_band_end = int(round(self._layout.margin_top_ratio * fh))
        y_bottom_band_start = int(
            round((1.0 - self._layout.margin_bottom_ratio) * fh)
        )
        return y_top_band_end, y_bottom_band_start

    def _update_margin_label(self) -> None:
        top_pct = int(round(self._layout.margin_top_ratio * 100))
        bot_pct = int(round(self._layout.margin_bottom_ratio * 100))
        self._margin_label_var.set(f"위 {top_pct}% · 아래 {bot_pct}% (가이드 띠)")

    def _parse_grid_dimension(self, raw: str, name: str) -> int | None:
        text = (raw or "").strip()
        if not text:
            messagebox.showwarning("입력", f"{name}을(를) 입력하세요.", parent=self)
            return None
        try:
            value = int(text)
        except ValueError:
            messagebox.showwarning(
                "입력",
                f"{name}은(는) 1 이상의 정수여야 합니다.",
                parent=self,
            )
            return None
        if value < 1:
            messagebox.showwarning(
                "입력",
                f"{name}은(는) 1 이상이어야 합니다.",
                parent=self,
            )
            return None
        return value

    def _apply_grid_align(self, *, uniform: bool) -> None:
        rows = self._parse_grid_dimension(self._grid_rows_var.get(), "행")
        if rows is None:
            return
        cols = self._parse_grid_dimension(self._grid_cols_var.get(), "열")
        if cols is None:
            return
        msg = apply_grid_layout(
            self._layout,
            rows,
            cols,
            uniform=uniform,
            min_box_w=MIN_BOX_W,
            min_box_h=MIN_BOX_H,
        )
        self._mark_dirty()
        self._redraw_canvas()
        if msg:
            messagebox.showinfo(
                "격자 정렬" if not uniform else "균일 정렬",
                msg,
                parent=self,
            )

    def _screen_y_to_fhd(self, sy: int) -> int:
        return int(round(sy / SCALE))

    def _fhd_y_to_screen(self, y_fhd: int) -> int:
        return int(round(y_fhd * SCALE))

    def _apply_margin_bounds(self, y_top_fhd: int, y_bottom_fhd: int) -> None:
        fh = self._layout.frame_height
        y_top = max(0, min(y_top_fhd, fh - MIN_USABLE_HEIGHT))
        y_bottom = max(y_top + MIN_USABLE_HEIGHT, min(y_bottom_fhd, fh))
        self._layout.margin_top_ratio = y_top / fh
        self._layout.margin_bottom_ratio = (fh - y_bottom) / fh

    def _draw_margin_rail(self) -> None:
        c = self._margin_rail
        c.delete("all")
        w = MARGIN_RAIL_WIDTH
        h = PREVIEW_HEIGHT
        y_top, y_bottom = self._guide_y_fhd()
        sy_top = self._fhd_y_to_screen(y_top)
        sy_bottom = self._fhd_y_to_screen(y_bottom)

        if sy_top > 0:
            c.create_rectangle(
                0, 0, w, sy_top,
                fill=MARGIN_RAIL_BAND_FILL,
                outline="",
                tags="rail",
            )
        c.create_rectangle(
            0, sy_top, w, sy_bottom,
            fill=MARGIN_RAIL_CONTENT_FILL,
            outline="",
            tags="rail",
        )
        if sy_bottom < h:
            c.create_rectangle(
                0, sy_bottom, w, h,
                fill=MARGIN_RAIL_BAND_FILL,
                outline="",
                tags="rail",
            )

        cx = w // 2
        hw = MARGIN_RAIL_HANDLE_WIDTH // 2
        for sy, tag in ((sy_top, "handle_top"), (sy_bottom, "handle_bottom")):
            c.create_line(0, sy, w, sy, fill=MARGIN_RAIL_HANDLE_COLOR, width=2, tags=tag)
            c.create_rectangle(
                cx - hw, sy - 5, cx + hw, sy + 5,
                fill=MARGIN_RAIL_HANDLE_COLOR,
                outline="white",
                width=1,
                tags=tag,
            )

        c.create_text(
            4, 4, text="상", anchor="nw", fill="#546e7a",
            font=("Segoe UI", 8), tags="rail",
        )
        c.create_text(
            4, h - 4, text="하", anchor="sw", fill="#546e7a",
            font=("Segoe UI", 8), tags="rail",
        )

    def _margin_rail_hit(self, sy: int) -> MarginDragMode:
        y_top, y_bottom = self._guide_y_fhd()
        sy_top = self._fhd_y_to_screen(y_top)
        sy_bottom = self._fhd_y_to_screen(y_bottom)
        if abs(sy - sy_top) <= MARGIN_HANDLE_HIT:
            return "top"
        if abs(sy - sy_bottom) <= MARGIN_HANDLE_HIT:
            return "bottom"
        return ""

    def _set_margin_rail_cursor(self, *, resize: bool) -> None:
        if resize:
            _try_configure_cursor(
                self._margin_rail, _MARGIN_DRAG_CURSOR_CANDIDATES
            )
        else:
            _try_configure_cursor(self._margin_rail, ("arrow",))

    def _on_margin_rail_press(self, event: tk.Event) -> None:
        mode = self._margin_rail_hit(event.y)
        if mode:
            self._margin_drag = mode
            self._set_margin_rail_cursor(resize=True)

    def _on_margin_rail_motion(self, event: tk.Event) -> None:
        if self._margin_drag:
            y_fhd = self._screen_y_to_fhd(event.y)
            y_top, y_bottom = self._guide_y_fhd()
            if self._margin_drag == "top":
                self._apply_margin_bounds(y_fhd, y_bottom)
            else:
                self._apply_margin_bounds(y_top, y_fhd)
            self._mark_dirty()
            self._refresh_margin_views()
            return
        hit = self._margin_rail_hit(event.y)
        self._set_margin_rail_cursor(resize=bool(hit))

    def _on_margin_rail_release(self, _event: tk.Event) -> None:
        self._margin_drag = ""
        self._set_margin_rail_cursor(resize=False)

    def _draw_shorts_zone_guides(self) -> None:
        """상·하단(숏츠에서 덜 쓰는 영역) 약한 선·띠."""
        c = self._canvas
        y_top, y_bottom = self._guide_y_fhd()
        _, sy_top = self._fhd_to_screen(0, y_top)
        _, sy_bottom = self._fhd_to_screen(0, y_bottom)

        if sy_top > 0:
            c.create_rectangle(
                0,
                0,
                PREVIEW_WIDTH,
                sy_top,
                fill=GUIDE_BAND_FILL,
                outline="",
                stipple=GUIDE_BAND_STIPPLE,
                tags="guide",
            )
        if sy_bottom < PREVIEW_HEIGHT:
            c.create_rectangle(
                0,
                sy_bottom,
                PREVIEW_WIDTH,
                PREVIEW_HEIGHT,
                fill=GUIDE_BAND_FILL,
                outline="",
                stipple=GUIDE_BAND_STIPPLE,
                tags="guide",
            )

        for sy in (sy_top, sy_bottom):
            c.create_line(
                0,
                sy,
                PREVIEW_WIDTH,
                sy,
                fill=GUIDE_LINE_COLOR,
                dash=GUIDE_LINE_DASH,
                width=1,
                tags="guide",
            )

        label_font = ("Segoe UI", 8)
        label_fill = "#8a96a8"
        c.create_text(
            6,
            4,
            text="상단 여백",
            anchor="nw",
            fill=label_fill,
            font=label_font,
            tags="guide",
        )
        c.create_text(
            6,
            PREVIEW_HEIGHT - 4,
            text="하단 여백",
            anchor="sw",
            fill=label_fill,
            font=label_font,
            tags="guide",
        )

    def _screen_to_fhd(self, x: int, y: int) -> tuple[int, int]:
        return int(round(x / SCALE)), int(round(y / SCALE))

    def _box_by_key(self, key: str) -> WordMemorizeBox | None:
        for box in self._layout.boxes:
            if box.box_key == key:
                return box
        return None

    def _selected_box(self) -> WordMemorizeBox | None:
        if not self._selected_key:
            return None
        return self._box_by_key(self._selected_key)

    def _mark_dirty(self) -> None:
        if self._dirty:
            return
        self._dirty = True
        self._update_window_title()

    def _clear_dirty(self) -> None:
        self._dirty = False
        self._update_window_title()

    def _update_window_title(self) -> None:
        n = len(self._layout.boxes)
        title = "단어 외우기 — 배치 편집"
        if n:
            title += f" ({n}개)"
        if self._dirty:
            title = f"*{title}"
        if self._file_path:
            title += f" — {Path(self._file_path).name}"
        self.title(title)

    def _confirm_discard_dirty(self, action: str) -> bool:
        """저장 안 된 변경이 있으면 저장/무시/취소."""
        if not self._dirty:
            return True
        ans = messagebox.askyesnocancel(
            "저장되지 않은 변경",
            f"{action}\n\n저장하지 않은 변경이 있습니다. 먼저 저장할까요?",
            parent=self,
        )
        if ans is None:
            return False
        if ans:
            self._save()
            if self._dirty:
                return False
        else:
            self._clear_dirty()
        return True

    def _set_file_path(self, path: Path | None) -> None:
        if path is None:
            self._file_path = None
            self._path_var.set("(새 배치 — 저장 전)")
        else:
            self._file_path = str(path.resolve())
            try:
                rel = path.resolve().relative_to(get_repo_root().resolve())
                display = rel.as_posix()
            except ValueError:
                display = self._file_path
            self._path_var.set(display)
        self._update_window_title()

    def _new_box_key(self) -> str:
        key = f"box_{self._next_box_num}"
        self._next_box_num += 1
        return key

    def _default_box_rect(self) -> tuple[int, int, int, int]:
        n = len(self._layout.boxes)
        x = 40 + (n % 3) * 120
        y = 120 + (n // 3) * 140
        return x, y, DEFAULT_BOX_W, DEFAULT_BOX_H

    def _try_set_box_rect(
        self,
        box: WordMemorizeBox,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> bool:
        old = (box.x, box.y, box.w, box.h)
        box.x = int(x)
        box.y = int(y)
        box.w = int(w)
        box.h = int(h)
        box.clamp_to_frame(
            self._layout.frame_width,
            self._layout.frame_height,
            MIN_BOX_W,
            MIN_BOX_H,
        )
        if box_overlaps_any(box, self._layout.boxes):
            box.x, box.y, box.w, box.h = old
            return False
        return True

    def _pick_word_id(self) -> str | None:
        picked: list[str] = []

        def _on_pick(word_id: str) -> None:
            picked.append(word_id)

        dlg = WordMemorizeWordPickDialog(self, _on_pick)
        self.wait_window(dlg)
        return picked[0] if picked else None

    def _used_word_ids(self) -> set[str]:
        used = {
            (b.word_id or "").strip()
            for b in self._layout.boxes
            if (b.word_id or "").strip()
        }
        used.update(
            wid for wid in self._layout.holding_word_ids if (wid or "").strip()
        )
        return used

    def _open_vocab_import(self) -> None:
        WordMemorizeVocabImportDialog(
            self,
            exclude_ids=self._used_word_ids(),
            on_import=self._import_word_ids_to_holding,
        )

    def _import_word_ids_to_holding(self, word_ids: list[str]) -> None:
        added = 0
        for wid in word_ids:
            w = (wid or "").strip()
            if not w or w in self._used_word_ids():
                continue
            self._layout.holding_word_ids.append(w)
            added += 1
        if added:
            self._mark_dirty()
            self._refresh_holding_list()

    def _holding_list_label(self, word_id: str) -> str:
        details = lookup_word_details(word_id)
        hanzi = details.get("word", "?")
        meaning = (details.get("meaning") or "").strip()
        label = f"{word_id:>6}  {hanzi}"
        if meaning:
            label += f"  {meaning[:18]}"
        return label

    def _refresh_holding_list(self) -> None:
        self._holding_list.delete(0, tk.END)
        for wid in self._layout.holding_word_ids:
            self._holding_list.insert(tk.END, self._holding_list_label(wid))

    def _create_box_for_word_id(self, word_id: str) -> WordMemorizeBox | None:
        wid = (word_id or "").strip()
        if not wid:
            return None
        if any((b.word_id or "").strip() == wid for b in self._layout.boxes):
            return None
        px, py, w, h = self._default_box_rect()
        x, y = find_non_overlapping_position(
            self._layout, w, h, prefer_x=px, prefer_y=py
        )
        box = WordMemorizeBox(
            word_id=wid,
            order=self._layout.next_order(),
            x=x,
            y=y,
            w=w,
            h=h,
            box_key=self._new_box_key(),
        )
        self._layout.boxes.append(box)
        return box

    def _move_holding_to_display(self) -> None:
        sel = self._holding_list.curselection()
        if not sel:
            messagebox.showinfo(
                "선택 없음",
                "보관함에서 표시할 단어를 선택하세요.",
                parent=self,
            )
            return
        ids = [
            self._layout.holding_word_ids[int(i)]
            for i in sel
            if 0 <= int(i) < len(self._layout.holding_word_ids)
        ]
        if not ids:
            return
        last_box: WordMemorizeBox | None = None
        placed: list[str] = []
        for wid in ids:
            box = self._create_box_for_word_id(wid)
            if box is None:
                continue
            placed.append(wid)
            last_box = box
        if not placed:
            messagebox.showinfo(
                "표시 불가",
                "선택한 단어를 캔버스에 둘 수 없습니다(이미 표시 중이거나 겹침).",
                parent=self,
            )
            return
        self._layout.holding_word_ids = [
            w
            for w in self._layout.holding_word_ids
            if w not in placed
        ]
        self._layout.renumber_orders()
        if last_box is not None:
            self._select_box(last_box.box_key)
        self._mark_dirty()
        self._refresh_holding_list()
        self._refresh_order_list()
        self._redraw_canvas()
        self._update_window_title()

    def _move_display_to_holding(self) -> None:
        sel = self._order_list.curselection()
        if not sel:
            messagebox.showinfo(
                "선택 없음",
                "표시 목록에서 보관함으로 보낼 항목을 선택하세요.",
                parent=self,
            )
            return
        sorted_boxes = self._layout.sorted_boxes()
        remove_keys: set[str] = set()
        for idx in sel:
            i = int(idx)
            if i < 0 or i >= len(sorted_boxes):
                continue
            box = sorted_boxes[i]
            wid = (box.word_id or "").strip()
            if wid and wid not in self._layout.holding_word_ids:
                self._layout.holding_word_ids.append(wid)
            if box.box_key:
                remove_keys.add(box.box_key)
        if not remove_keys:
            return
        self._layout.boxes = [
            b for b in self._layout.boxes if b.box_key not in remove_keys
        ]
        self._layout.renumber_orders()
        self._selected_key = None
        self._mark_dirty()
        self._refresh_holding_list()
        self._refresh_order_list()
        self._redraw_canvas()
        self._update_window_title()

    def _add_box(self) -> None:
        word_id = self._pick_word_id()
        if not word_id:
            return
        if word_id in self._layout.holding_word_ids:
            self._layout.holding_word_ids = [
                w for w in self._layout.holding_word_ids if w != word_id
            ]
            self._refresh_holding_list()
        box = self._create_box_for_word_id(word_id)
        if box is None:
            messagebox.showinfo(
                "추가 불가",
                "이미 표시 중이거나 배치할 수 없습니다.",
                parent=self,
            )
            return
        self._select_box(box.box_key)
        self._redraw_canvas()
        self._refresh_order_list()
        self._mark_dirty()
        self._update_window_title()

    def _delete_selected(self) -> None:
        box = self._selected_box()
        if box is None:
            messagebox.showinfo("선택 없음", "삭제할 word box를 선택하세요.", parent=self)
            return
        self._layout.boxes = [b for b in self._layout.boxes if b.box_key != box.box_key]
        self._layout.renumber_orders()
        self._selected_key = None
        self._redraw_canvas()
        self._refresh_order_list()
        self._mark_dirty()
        self._update_window_title()

    def _match_all_to_selected_size(self) -> None:
        ref = self._selected_box()
        if ref is None:
            messagebox.showinfo(
                "선택 없음",
                "기준이 될 word box를 먼저 선택하세요.",
                parent=self,
            )
            return
        others = [b for b in self._layout.boxes if b.box_key != ref.box_key]
        if not others:
            messagebox.showinfo(
                "대상 없음",
                "맞출 다른 word box가 없습니다.",
                parent=self,
            )
            return
        skipped = 0
        for box in others:
            if not self._try_set_box_rect(box, box.x, box.y, ref.w, ref.h):
                skipped += 1
        self._redraw_canvas()
        if skipped < len(others):
            self._mark_dirty()
        if skipped:
            messagebox.showinfo(
                "일부 미적용",
                f"{skipped}개 박스는 겹침 때문에 크기를 바꿀 수 없습니다.",
                parent=self,
            )

    def _sync_bg_music_combo(self) -> None:
        label = bg_path_for_combo(self._layout.bg_music_path)
        choices = [BG_PATH_RANDOM_LABEL] + list_bg_path_choices()
        self._bg_music_combo["values"] = choices
        if label in choices:
            self._bg_music_var.set(label)
        elif choices:
            self._bg_music_var.set(choices[0])

    def _on_bg_music_combo_changed(self, _event: tk.Event | None = None) -> None:
        self._layout.bg_music_path = normalize_vocab_bg_path(
            bg_path_from_combo(self._bg_music_var.get())
        )
        self._mark_dirty()

    def _edit_background(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("배경 설정")
        dlg.transient(self)
        dlg.grab_set()
        frame = ttk.Frame(dlg, padding=12)
        frame.pack()

        kind_var = tk.StringVar(
            value=self._layout.background_type
        )
        ttk.Radiobutton(frame, text="단색", variable=kind_var, value="color").pack(
            anchor="w"
        )
        ttk.Radiobutton(frame, text="이미지", variable=kind_var, value="image").pack(
            anchor="w", pady=(0, 8)
        )

        color_var = tk.StringVar(value=self._layout.background_value)
        path_var = tk.StringVar(value=self._layout.background_value)

        color_row = ttk.Frame(frame)
        color_row.pack(fill=tk.X, pady=4)
        ttk.Label(color_row, text="색상:").pack(side=tk.LEFT)
        color_entry = ttk.Entry(color_row, textvariable=color_var, width=14)
        color_entry.pack(side=tk.LEFT, padx=4)

        def _pick_color() -> None:
            initial = color_var.get() or "#ffffff"
            chosen = colorchooser.askcolor(color=initial, parent=dlg)
            if chosen and chosen[1]:
                color_var.set(chosen[1])

        ttk.Button(color_row, text="…", width=3, command=_pick_color).pack(
            side=tk.LEFT
        )

        path_row = ttk.Frame(frame)
        path_row.pack(fill=tk.X, pady=4)
        ttk.Label(path_row, text="이미지:").pack(side=tk.LEFT)
        path_entry = ttk.Entry(path_row, textvariable=path_var, width=28)
        path_entry.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        def _browse_image() -> None:
            repo = get_repo_root()
            initial = repo / "resource" / "image"
            path = filedialog.askopenfilename(
                parent=dlg,
                title="배경 이미지",
                initialdir=str(initial if initial.is_dir() else repo),
                filetypes=[
                    ("이미지", "*.png *.jpg *.jpeg *.webp *.bmp"),
                    ("모든 파일", "*.*"),
                ],
            )
            if path:
                try:
                    rel = Path(path).resolve().relative_to(repo.resolve())
                    path_var.set(rel.as_posix())
                except ValueError:
                    path_var.set(path)

        ttk.Button(path_row, text="찾기", command=_browse_image).pack(side=tk.LEFT)

        def _apply() -> None:
            bg_type = kind_var.get()
            if bg_type == "image":
                val = path_var.get().strip()
                if not val:
                    messagebox.showwarning(
                        "경로 없음", "이미지 경로를 입력하세요.", parent=dlg
                    )
                    return
            else:
                val = color_var.get().strip() or "#ffffff"
            self._layout.background_type = bg_type  # type: ignore[assignment]
            self._layout.background_value = val
            self._mark_dirty()
            self._redraw_canvas()
            dlg.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=(12, 0))
        ttk.Button(btn_row, text="적용", command=_apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="취소", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        schedule_center_toplevel_on_parent(dlg, self, width=420, height=220)

    def _refresh_order_list(self) -> None:
        self._order_list.delete(0, tk.END)
        for box in self._layout.sorted_boxes():
            details = lookup_word_details(box.word_id)
            hanzi = details.get("word", "?")
            meaning = (details.get("meaning") or "").strip()
            en = (details.get("en_meaning") or "").strip()
            label = f"{box.order:2d}. id={box.word_id}  {hanzi}"
            if meaning:
                label += f"  {meaning}"
            if en:
                label += f"  ({en})"
            self._order_list.insert(tk.END, label)
        self._sync_order_list_selection()

    def _sync_order_list_selection(self) -> None:
        if not self._selected_key:
            return
        box = self._selected_box()
        if box is None:
            return
        sorted_boxes = self._layout.sorted_boxes()
        try:
            idx = sorted_boxes.index(box)
        except ValueError:
            return
        self._order_list.selection_clear(0, tk.END)
        self._order_list.selection_set(idx)
        self._order_list.see(idx)

    def _on_order_list_select(self, _event: tk.Event | None = None) -> None:
        sel = self._order_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        sorted_boxes = self._layout.sorted_boxes()
        if 0 <= idx < len(sorted_boxes):
            self._select_box(sorted_boxes[idx].box_key)

    def _move_order_up(self) -> None:
        self._swap_order(-1)

    def _move_order_down(self) -> None:
        self._swap_order(1)

    def _swap_order(self, delta: int) -> None:
        box = self._selected_box()
        if box is None:
            return
        ordered = self._layout.sorted_boxes()
        try:
            idx = ordered.index(box)
        except ValueError:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(ordered):
            return
        other = ordered[new_idx]
        box.order, other.order = other.order, box.order
        self._layout.renumber_orders()
        self._refresh_order_list()
        self._sync_order_list_selection()
        self._redraw_canvas()
        self._mark_dirty()

    def _select_box(self, key: str | None) -> None:
        self._selected_key = key
        self._sync_order_list_selection()
        self._redraw_canvas()

    def _screen_rect(self, box: WordMemorizeBox) -> tuple[int, int, int, int]:
        x1, y1 = self._fhd_to_screen(box.x, box.y)
        x2, y2 = self._fhd_to_screen(box.x + box.w, box.y + box.h)
        return x1, y1, x2, y2

    def _hit_test(self, sx: int, sy: int) -> tuple[str | None, ResizeHandle]:
        box = self._selected_box()
        if box is not None:
            handle = self._hit_handles(box, sx, sy)
            if handle:
                return box.box_key, handle
            x1, y1, x2, y2 = self._screen_rect(box)
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return box.box_key, "move"

        for other in reversed(self._layout.sorted_boxes()):
            x1, y1, x2, y2 = self._screen_rect(other)
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return other.box_key, "move"
        return None, ""

    def _hit_handles(self, box: WordMemorizeBox, sx: int, sy: int) -> ResizeHandle:
        x1, y1, x2, y2 = self._screen_rect(box)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        points: list[tuple[ResizeHandle, int, int]] = [
            ("nw", x1, y1),
            ("n", cx, y1),
            ("ne", x2, y1),
            ("e", x2, cy),
            ("se", x2, y2),
            ("s", cx, y2),
            ("sw", x1, y2),
            ("w", x1, cy),
        ]
        for name, px, py in points:
            if abs(sx - px) <= HANDLE_HIT and abs(sy - py) <= HANDLE_HIT:
                return name
        return ""

    def _on_canvas_press(self, event: tk.Event) -> None:
        key, mode = self._hit_test(event.x, event.y)
        if key:
            self._select_box(key)
            box = self._box_by_key(key)
            if box is None:
                return
            self._drag_mode = mode
            self._drag_start = (event.x, event.y)
            self._drag_box_snapshot = WordMemorizeBox(
                word_id=box.word_id,
                order=box.order,
                x=box.x,
                y=box.y,
                w=box.w,
                h=box.h,
                box_key=box.box_key,
            )
        else:
            self._select_box(None)
            self._drag_mode = ""
            self._drag_start = None
            self._drag_box_snapshot = None

    def _on_canvas_motion(self, event: tk.Event) -> None:
        if not self._drag_mode or not self._drag_start or not self._drag_box_snapshot:
            return
        box = self._box_by_key(self._drag_box_snapshot.box_key)
        if box is None:
            return
        snap = self._drag_box_snapshot
        dx_s = event.x - self._drag_start[0]
        dy_s = event.y - self._drag_start[1]
        dx, dy = self._screen_to_fhd(dx_s, dy_s)
        fw, fh = self._layout.frame_width, self._layout.frame_height

        if self._drag_mode == "move":
            if self._try_set_box_rect(
                box, snap.x + dx, snap.y + dy, snap.w, snap.h
            ):
                self._redraw_canvas()
            return

        x1, y1, x2, y2 = snap.x, snap.y, snap.x + snap.w, snap.y + snap.h
        if "w" in self._drag_mode:
            x1 = min(x1 + dx, x2 - MIN_BOX_W)
        if "e" in self._drag_mode:
            x2 = max(x2 + dx, x1 + MIN_BOX_W)
        if "n" in self._drag_mode:
            y1 = min(y1 + dy, y2 - MIN_BOX_H)
        if "s" in self._drag_mode:
            y2 = max(y2 + dy, y1 + MIN_BOX_H)

        nx = max(0, x1)
        ny = max(0, y1)
        nw = min(x2 - x1, fw - nx)
        nh = min(y2 - y1, fh - ny)
        if self._try_set_box_rect(box, nx, ny, nw, nh):
            self._redraw_canvas()

    def _on_canvas_release(self, _event: tk.Event) -> None:
        if self._drag_mode:
            self._mark_dirty()
        self._drag_mode = ""
        self._drag_start = None
        self._drag_box_snapshot = None

    def _draw_background(self) -> None:
        c = self._canvas
        c.delete("bg")
        if self._layout.background_type == "image":
            path = Path(self._layout.background_value)
            if not path.is_absolute():
                path = get_repo_root() / path.as_posix().replace("\\", "/")
            if path.is_file():
                try:
                    from PIL import Image, ImageTk

                    img = Image.open(path).convert("RGB")
                    img = img.resize((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                    self._bg_photo = ImageTk.PhotoImage(img)
                    c.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg")
                    return
                except Exception:
                    pass
            c.create_rectangle(
                0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT,
                fill="#333", outline="", tags="bg",
            )
            c.create_text(
                PREVIEW_WIDTH // 2,
                PREVIEW_HEIGHT // 2,
                text="배경 이미지 없음",
                fill="#aaa",
                tags="bg",
            )
            return
        fill = self._layout.background_value or "#ffffff"
        c.create_rectangle(
            0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT,
            fill=fill, outline="", tags="bg",
        )

    def _display_pinyin(self, details: dict[str, str]) -> str:
        hanzi = (details.get("word") or "").strip()
        raw = (details.get("pinyin") or "").strip()
        masking = (details.get("masking") or "").strip()
        if raw and hanzi:
            try:
                from utils.pinyin_masking import word_pinyin_to_marks_spaced

                marks = word_pinyin_to_marks_spaced(hanzi, raw).strip()
                if marks:
                    return marks
            except Exception:
                pass
            return raw
        if hanzi:
            try:
                from utils.pinyin_masking import (
                    get_masked_pinyin_marks,
                    normalize_word_masking,
                )

                marks = get_masked_pinyin_marks(
                    hanzi, normalize_word_masking(masking)
                ).strip()
                if marks:
                    return marks
            except Exception:
                pass
        return raw

    def _load_box_photo(
        self,
        box_key: str,
        details: dict[str, str],
        word_id: str,
        max_px: int,
    ) -> object | None:
        from extra.table_editor.services.image_paths import preview_image_path

        path = preview_image_path(
            get_repo_root(),
            details.get("img_path", ""),
            word_id=word_id,
            word=details.get("word", ""),
        )
        if path is None or max_px < 8:
            return None
        cache_key = f"{box_key}:{path}:{max_px}"
        if cache_key in self._box_photos:
            return self._box_photos[cache_key]
        try:
            from PIL import Image, ImageTk

            img = Image.open(path)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            w, h = img.size
            if w <= 0 or h <= 0:
                return None
            scale = min(max_px / w, max_px / h, 1.0)
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._box_photos[cache_key] = photo
            return photo
        except Exception:
            return None

    def _draw_box_content(
        self,
        c: tk.Canvas,
        box: WordMemorizeBox,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        details: dict[str, str],
    ) -> None:
        """박스 안: 병음(빨강) → 한자 → 영어 → 이미지(하단)."""
        cx = (x1 + x2) // 2
        inner_w = max(24, x2 - x1 - BOX_CONTENT_PAD * 2)
        top_y = y1 + BOX_CONTENT_PAD + 14
        bottom_limit = y2 - BOX_CONTENT_PAD

        box_h = max(1, y2 - y1)
        img_max = int(min(inner_w, box_h * BOX_IMG_MAX_RATIO))
        photo = self._load_box_photo(box.box_key, details, box.word_id, img_max)
        img_h = photo.height() if photo is not None else 0
        if img_h > 0:
            bottom_limit -= img_h + BOX_IMG_BOTTOM_PAD + BOX_IMG_LIFT

        y = top_y
        tags = ("box", box.box_key)

        pinyin = self._display_pinyin(details)
        if pinyin:
            tid = c.create_text(
                cx,
                y,
                text=pinyin[:48],
                anchor="n",
                fill=BOX_PINYIN_COLOR,
                font=BOX_PINYIN_FONT,
                width=inner_w,
                tags=tags,
            )
            bbox = c.bbox(tid)
            if bbox:
                y = bbox[3] + BOX_LINE_GAP

        hanzi = (details.get("word") or "?").strip() or "?"
        tid = c.create_text(
            cx,
            y,
            text=hanzi,
            anchor="n",
            fill=BOX_HANZI_COLOR,
            font=BOX_HANZI_FONT,
            width=inner_w,
            tags=tags,
        )
        bbox = c.bbox(tid)
        if bbox:
            y = bbox[3] + BOX_LINE_GAP

        en = (details.get("en_meaning") or "").strip()
        if en and y < bottom_limit:
            tid = c.create_text(
                cx,
                y,
                text=en[:40],
                anchor="n",
                fill=BOX_EN_COLOR,
                font=BOX_EN_FONT,
                width=inner_w,
                tags=tags,
            )
            bbox = c.bbox(tid)
            if bbox:
                y = bbox[3] + BOX_LINE_GAP

        if photo is not None and img_h > 0:
            iy = y2 - BOX_IMG_BOTTOM_PAD - BOX_IMG_LIFT - img_h
            c.create_image(cx, iy, anchor="n", image=photo, tags=tags)

    def _redraw_canvas(self) -> None:
        c = self._canvas
        c.delete("all")
        self._box_photos.clear()
        self._draw_background()
        self._draw_shorts_zone_guides()

        for box in self._layout.sorted_boxes():
            selected = box.box_key == self._selected_key
            x1, y1, x2, y2 = self._screen_rect(box)
            outline = "#4fc3f7" if selected else "#90a4ae"
            width = 3 if selected else 1
            c.create_rectangle(
                x1, y1, x2, y2,
                outline=outline,
                width=width,
                fill="#ffffff",
                tags=("box", box.box_key),
            )
            details = lookup_word_details(box.word_id)
            self._draw_box_content(c, box, x1, y1, x2, y2, details)
            badge = f"#{box.order}"
            c.create_text(
                x1 + 6, y1 + 6,
                text=badge,
                anchor="nw",
                fill="#1565c0",
                font=BOX_BADGE_FONT,
                tags=("box", box.box_key),
            )

        box = self._selected_box()
        if box is not None:
            self._draw_handles(box)
        self._draw_margin_rail()

    def _refresh_margin_views(self) -> None:
        """여백만 변경 시 가이드·레일만 갱신."""
        self._update_margin_label()
        self._draw_margin_rail()
        self._canvas.delete("guide")
        self._draw_shorts_zone_guides()

    def _draw_handles(self, box: WordMemorizeBox) -> None:
        c = self._canvas
        x1, y1, x2, y2 = self._screen_rect(box)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        points = [
            (x1, y1), (cx, y1), (x2, y1),
            (x2, cy), (x2, y2), (cx, y2),
            (x1, y2), (x1, cy),
        ]
        r = HANDLE_DRAW
        for px, py in points:
            c.create_rectangle(
                px - r, py - r, px + r, py + r,
                fill="#ffeb3b",
                outline="#f57f17",
                tags="handle",
            )

    def _save(self) -> None:
        if self._file_path:
            path = Path(self._file_path)
        else:
            self._save_as()
            return
        self._write_layout(path)

    def _save_as(self) -> None:
        DEFAULT_LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="배치 다른 이름으로 저장",
            initialdir=str(DEFAULT_LAYOUTS_DIR),
            initialfile=Path(self._file_path).name if self._file_path else "layout.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        self._write_layout(Path(path))

    def _write_layout(self, path: Path) -> None:
        self._layout.renumber_orders()
        try:
            save_layout(path, self._layout)
        except OSError as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self)
            return
        self._set_file_path(path)
        self._clear_dirty()

    def _new_layout(self) -> None:
        if not self._confirm_discard_dirty("새 배치를 시작합니다."):
            return
        self._layout = WordMemorizeLayout()
        self._set_file_path(None)
        self._selected_key = None
        self._next_box_num = 1
        self._clear_dirty()
        self._redraw_canvas()
        self._refresh_holding_list()
        self._refresh_order_list()
        self._update_margin_label()
        self._sync_bg_music_combo()

    def _open(self) -> None:
        if not self._confirm_discard_dirty("다른 배치 파일을 불러옵니다."):
            return
        DEFAULT_LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self,
            title="배치 불러오기",
            initialdir=str(DEFAULT_LAYOUTS_DIR),
            filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            self._layout = load_layout(Path(path))
        except Exception as ex:
            messagebox.showerror("불러오기 실패", str(ex), parent=self)
            return
        self._set_file_path(Path(path))
        self._selected_key = None
        max_num = 0
        for box in self._layout.boxes:
            if box.box_key.startswith("box_"):
                try:
                    max_num = max(max_num, int(box.box_key.split("_", 1)[1]))
                except (IndexError, ValueError):
                    pass
            if not box.box_key:
                box.box_key = self._new_box_key()
        self._next_box_num = max_num + 1
        self._clear_dirty()
        self._redraw_canvas()
        self._refresh_holding_list()
        self._refresh_order_list()
        self._update_margin_label()
        if layout_has_overlaps(self._layout):
            messagebox.showwarning(
                "박스 겹침",
                "불러온 배치에 겹치는 word box가 있습니다. "
                "이동·크기 조절 시 겹치지 않게만 변경됩니다.",
                parent=self,
            )
        self._sync_bg_music_combo()

    def _on_close(self) -> None:
        if not self._confirm_discard_dirty("창을 닫습니다."):
            return
        ShortsBgPathPreviewPlayer.stop_global()
        global _active_editor
        if _active_editor is self:
            _active_editor = None
        self.destroy()
