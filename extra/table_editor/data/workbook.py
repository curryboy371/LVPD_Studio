"""In-memory Excel load/save for table editor."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

EXCEL_EXTENSIONS = (".xlsx", ".xls")


def _ensure_excel(path: Path) -> None:
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")


def normalize_id_display(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        f = float(value)
        if f == int(f):
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def cell_to_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float):
        try:
            if value == int(value):
                return str(int(value))
        except (OverflowError, ValueError):
            pass
    return str(value).strip()


def dataframe_to_rows(df: pd.DataFrame, fieldnames: list[str]) -> list[dict[str, str]]:
    """DataFrame → list of row dicts with string values for UI."""
    rows: list[dict[str, str]] = []
    if df is None or df.empty:
        return rows
    for _, series in df.iterrows():
        row: dict[str, str] = {}
        for col in fieldnames:
            if col in series.index:
                val = series[col]
            else:
                val = ""
            if col == "id":
                row[col] = normalize_id_display(val)
            else:
                row[col] = cell_to_str(val)
        rows.append(row)
    return rows


def rows_to_dataframe(rows: list[dict[str, str]], fieldnames: list[str]) -> pd.DataFrame:
    """Row dicts → DataFrame with fieldnames columns."""
    data: list[dict[str, Any]] = []
    for row in rows:
        out: dict[str, Any] = {}
        for col in fieldnames:
            out[col] = row.get(col, "")
        data.append(out)
    return pd.DataFrame(data, columns=fieldnames)


def _row_lists_equal(
    left: list[dict[str, str]],
    right: list[dict[str, str]],
    fieldnames: list[str],
) -> bool:
    """UI flush 시 내용이 같으면 dirty 로 잡히지 않도록 비교."""
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        for col in fieldnames:
            if (a.get(col, "") or "").strip() != (b.get(col, "") or "").strip():
                return False
    return True


def align_dataframe_columns(
    df: pd.DataFrame,
    fieldnames: list[str],
    *,
    drop_extra_columns: bool = False,
) -> pd.DataFrame:
    """Ensure editor columns exist.

    drop_extra_columns: True면 fieldnames 외 엑셀 열은 버린다 (words.xlsx 등).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=fieldnames)
    out = df.copy()
    for col in fieldnames:
        if col not in out.columns:
            out[col] = ""
    if drop_extra_columns:
        return out[fieldnames]
    extra = [c for c in out.columns if c not in fieldnames]
    ordered = list(fieldnames) + [c for c in extra if c not in fieldnames]
    return out[ordered]


class ExcelWorkbookStore:
    """Single-sheet xlsx file."""

    def __init__(self, fieldnames: list[str]) -> None:
        self.fieldnames = list(fieldnames)
        self.path: Path | None = None
        self._df: pd.DataFrame = pd.DataFrame(columns=fieldnames)
        self.dirty = False

    def load(self, path: str | Path) -> None:
        p = Path(path)
        _ensure_excel(p)
        df = pd.read_excel(p).dropna(axis=1, how="all")
        self._df = align_dataframe_columns(df, self.fieldnames)
        self.path = p.resolve()
        self.dirty = False

    def get_dataframe(self) -> pd.DataFrame:
        return self._df.copy()

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self._df = align_dataframe_columns(df, self.fieldnames)
        self.dirty = True

    def get_rows(self) -> list[dict[str, str]]:
        return dataframe_to_rows(self._df, self.fieldnames)

    def set_rows(self, rows: list[dict[str, str]]) -> None:
        if _row_lists_equal(self.get_rows(), rows, self.fieldnames):
            return
        self._df = rows_to_dataframe(rows, self.fieldnames)
        self.dirty = True

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("저장 경로가 없습니다.")
        _ensure_excel(target)
        if target.exists() and not getattr(self, "_bak_done", False):
            bak = target.with_suffix(target.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(target, bak)
            self._bak_done = True
        target.parent.mkdir(parents=True, exist_ok=True)
        self._df.to_excel(target, index=False, engine="openpyxl")
        self.path = target.resolve()
        self.dirty = False
        return self.path


class MultiSheetWorkbookStore:
    """Multi-sheet xlsx (words.xlsx)."""

    def __init__(self, fieldnames: list[str]) -> None:
        self.fieldnames = list(fieldnames)
        self.path: Path | None = None
        self._sheets: dict[str, pd.DataFrame] = {}
        self._sheet_order: list[str] = []
        self.dirty = False

    @property
    def sheet_names(self) -> list[str]:
        return list(self._sheet_order)

    def load(self, path: str | Path) -> None:
        p = Path(path)
        _ensure_excel(p)
        xls = pd.ExcelFile(p)
        self._sheet_order = list(xls.sheet_names)
        self._sheets = {}
        for name in self._sheet_order:
            df = pd.read_excel(p, sheet_name=name)
            if df is None or df.empty:
                self._sheets[name] = pd.DataFrame(columns=self.fieldnames)
            else:
                self._sheets[name] = align_dataframe_columns(
                    df.dropna(axis=1, how="all"),
                    self.fieldnames,
                    drop_extra_columns=True,
                )
        self.path = p.resolve()
        self.dirty = False

    def get_sheet_dataframe(self, sheet_name: str) -> pd.DataFrame:
        return self._sheets.get(sheet_name, pd.DataFrame(columns=self.fieldnames)).copy()

    def set_sheet_dataframe(self, sheet_name: str, df: pd.DataFrame) -> None:
        self._sheets[sheet_name] = align_dataframe_columns(
            df, self.fieldnames, drop_extra_columns=True
        )
        if sheet_name not in self._sheet_order:
            self._sheet_order.append(sheet_name)
        self.dirty = True

    def get_sheet_rows(self, sheet_name: str) -> list[dict[str, str]]:
        return dataframe_to_rows(self._sheets.get(sheet_name), self.fieldnames)

    def set_sheet_rows(self, sheet_name: str, rows: list[dict[str, str]]) -> None:
        current = self.get_sheet_rows(sheet_name)
        if _row_lists_equal(current, rows, self.fieldnames):
            return
        self.set_sheet_dataframe(sheet_name, rows_to_dataframe(rows, self.fieldnames))

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("저장 경로가 없습니다.")
        _ensure_excel(target)
        if target.exists() and not getattr(self, "_bak_done", False):
            bak = target.with_suffix(target.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(target, bak)
            self._bak_done = True
        target.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            for name in self._sheet_order:
                self._sheets[name].to_excel(writer, sheet_name=name, index=False)
        self.path = target.resolve()
        self.dirty = False
        return self.path
