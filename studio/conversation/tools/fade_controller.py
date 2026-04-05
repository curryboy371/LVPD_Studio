"""채널별 알파 페이드 상태만 담당 (Drawer와 분리)."""

from __future__ import annotations


class FadeController:
    """fade_on / fade_off / tick / alpha — 채널 문자열 키 기준."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, float | int]] = {}

    def fade_on(self, channel: str, sec: float = 0.0) -> None:
        self._start_fade(channel, target_alpha=255, sec=sec)

    def fade_off(self, channel: str, sec: float = 0.0) -> None:
        self._start_fade(channel, target_alpha=0, sec=sec)

    def fade_all_off(self, channels: list[str], sec: float = 0.0) -> None:
        for ch in channels:
            self.fade_off(ch, sec)

    def tick(self, dt_sec: float) -> None:
        dt = max(0.0, float(dt_sec))
        if dt <= 0.0 or not self._states:
            return
        for st in self._states.values():
            sec = float(st.get("sec", 0.0) or 0.0)
            if sec <= 1e-6:
                continue
            elapsed = float(st.get("elapsed", 0.0) or 0.0) + dt
            frm = int(st.get("from", 0) or 0)
            to = int(st.get("to", 0) or 0)
            t = max(0.0, min(1.0, elapsed / sec))
            st["alpha"] = int(frm + (to - frm) * t)
            if t >= 1.0:
                st["alpha"] = to
                st["from"] = to
                st["to"] = to
                st["elapsed"] = 0.0
                st["sec"] = 0.0
            else:
                st["elapsed"] = elapsed

    def alpha(self, channel: str) -> int:
        st = self._states.get(channel)
        if st is None:
            return 0
        return max(0, min(255, int(st.get("alpha", 0) or 0)))

    def _start_fade(self, channel: str, *, target_alpha: int, sec: float) -> None:
        key = str(channel or "").strip()
        if not key:
            return
        st = self._states.get(key)
        cur = int(st.get("alpha", 0) or 0) if st is not None else 0
        to = max(0, min(255, int(target_alpha)))
        duration = max(0.0, float(sec))
        if duration <= 1e-6:
            self._states[key] = {
                "alpha": to,
                "from": to,
                "to": to,
                "elapsed": 0.0,
                "sec": 0.0,
            }
            return
        self._states[key] = {
            "alpha": cur,
            "from": cur,
            "to": to,
            "elapsed": 0.0,
            "sec": duration,
        }
