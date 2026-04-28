"""
SVG( make-me-a-hanzi 형식 )를 Playwright/Chromium으로 사전 렌더링해 PNG 시퀀스로 저장한다.

출력:
- resource/hanzi_frames/{codepoint}/0000.png ...
- resource/hanzi_frames/{codepoint}/meta.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
import sys

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.paths import get_repo_root


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      width: {size}px;
      height: {size}px;
      background: transparent;
      overflow: hidden;
    }}
    #root {{
      width: {size}px;
      height: {size}px;
    }}
    svg {{
      width: {size}px;
      height: {size}px;
      display: block;
    }}
  </style>
</head>
<body>
  <div id="root">{svg}</div>
</body>
</html>
"""


async def _render_one_svg(
    page,
    svg_path: Path,
    out_dir: Path,
    *,
    size: int,
    fps: int,
    oversample: float = 1.0,
    active_stroke_color: str = "#35A4FF",
    done_stroke_color: str = "#8A93A0",
    fill_color: str = "#5F6773",
    show_guide: bool = False,
) -> None:
    svg_text = svg_path.read_text(encoding="utf-8")
    html = HTML_TEMPLATE.format(size=size, svg=svg_text)
    await page.set_content(html, wait_until="load")
    await page.evaluate(
        """
        (opts) => {
          // SVG 내부 keyframes 색상 치환:
          // - 진행 중 획(blue 계열) -> active_stroke_color
          // - 완료 획(black 계열) -> done_stroke_color
          document.querySelectorAll("style").forEach((el) => {
            const src = String(el.textContent || "");
            let replaced = src;
            replaced = replaced.replace(/stroke\\s*:\\s*blue\\s*;/gi, `stroke: ${opts.activeStrokeColor};`);
            replaced = replaced.replace(/stroke\\s*:\\s*#00f(?:f)?\\s*;/gi, `stroke: ${opts.activeStrokeColor};`);
            replaced = replaced.replace(/stroke\\s*:\\s*black\\s*;/gi, `stroke: ${opts.doneStrokeColor};`);
            replaced = replaced.replace(/stroke\\s*:\\s*#000(?:000)?\\s*;/gi, `stroke: ${opts.doneStrokeColor};`);
            if (replaced !== src) {
              el.textContent = replaced;
            }
          });

          const styleId = "lvpd-hanzi-render-style";
          const old = document.getElementById(styleId);
          if (old) old.remove();
          const st = document.createElement("style");
          st.id = styleId;
          st.textContent = `
            path[id^="make-me-a-hanzi-animation-"] {
              stroke: ${opts.activeStrokeColor} !important;
              fill: none !important;
            }
            path:not([id^="make-me-a-hanzi-animation-"]) {
              fill: ${opts.fillColor} !important;
            }
          `;
          document.head.appendChild(st);
          if (!opts.showGuide) {
            document.querySelectorAll("line").forEach((el) => {
              el.style.display = "none";
            });
          }
        }
        """,
        {
            "activeStrokeColor": active_stroke_color,
            "doneStrokeColor": done_stroke_color,
            "fillColor": fill_color,
            "showGuide": bool(show_guide),
        },
    )
    await page.evaluate(
        """
        () => {
          const anims = document.getAnimations();
          for (const a of anims) {
            try { a.pause(); } catch (_) {}
          }
        }
        """
    )
    total_ms = await page.evaluate(
        """
        () => {
          const anims = document.getAnimations();
          if (!anims || anims.length === 0) return 0;
          let m = 0;
          for (const a of anims) {
            const t = a.effect?.getComputedTiming?.();
            if (!t) continue;
            const end = (Number(t.delay || 0) + Number(t.endDelay || 0) + Number(t.activeDuration || 0));
            if (Number.isFinite(end)) m = Math.max(m, end);
          }
          return Math.max(0, m);
        }
        """
    )
    if total_ms <= 0:
        total_ms = 1200
    total_ms = float(total_ms) / max(0.1, float(oversample))

    out_dir.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(round((total_ms / 1000.0) * fps)))
    frames: list[str] = []

    for i in range(frame_count):
        t_ms = (i / max(1, frame_count - 1)) * total_ms
        await page.evaluate(
            """
            (t) => {
              const anims = document.getAnimations();
              for (const a of anims) {
                try { a.currentTime = t; } catch (_) {}
              }
            }
            """,
            t_ms,
        )
        name = f"{i:04d}.png"
        p = out_dir / name
        await page.screenshot(path=str(p), omit_background=True)
        frames.append(name)

    meta = {
        "codepoint": int(svg_path.stem),
        "fps": int(fps),
        "frame_count": int(frame_count),
        "duration_sec": round(frame_count / float(fps), 6),
        "frames": frames,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def _amain(args) -> None:
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError:
        print("[error] playwright 모듈이 없습니다.")
        print("설치: pip install playwright")
        print("브라우저 설치: python -m playwright install chromium")
        return

    repo = get_repo_root()
    svg_dir = repo / "resource" / "svgs"
    out_root = repo / "resource" / "hanzi_frames"
    words_csv = repo / "resource" / "csv" / "words.csv"
    out_root.mkdir(parents=True, exist_ok=True)

    if args.codepoints:
        targets = [svg_dir / f"{int(cp)}.svg" for cp in args.codepoints]
    elif args.all_svgs:
        targets = sorted(svg_dir.glob("*.svg"))
    else:
        cps = _collect_codepoints_from_words_csv(words_csv)
        targets = [svg_dir / f"{cp}.svg" for cp in sorted(cps)]
    targets = [p for p in targets if p.exists()]
    if not targets:
        print("렌더할 SVG가 없습니다.")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": args.size, "height": args.size})
        for svg_path in targets:
            code = svg_path.stem
            out_dir = out_root / code
            await _render_one_svg(
                page,
                svg_path,
                out_dir,
                size=args.size,
                fps=args.fps,
                oversample=args.speed,
                active_stroke_color=args.active_stroke_color,
                done_stroke_color=args.done_stroke_color,
                fill_color=args.fill_color,
                show_guide=args.show_guide,
            )
            print(f"[ok] {svg_path.name} -> {out_dir}")
        await browser.close()


def _collect_codepoints_from_words_csv(words_csv_path: Path) -> set[int]:
    out: set[int] = set()
    if not words_csv_path.exists():
        print(f"[warn] words.csv 없음: {words_csv_path}")
        return out
    try:
        with open(words_csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                word = str(row.get("word") or "").strip()
                if not word:
                    continue
                for ch in word:
                    if ch.strip():
                        out.add(ord(ch))
    except Exception as ex:
        print(f"[warn] words.csv 파싱 실패: {ex}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="SVG를 PNG 시퀀스로 사전 렌더링")
    ap.add_argument("--fps", type=int, default=30, help="출력 FPS")
    ap.add_argument("--size", type=int, default=768, help="출력 프레임 해상도(정사각)")
    ap.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="애니메이션 시간 배율(>1 빠르게, <1 느리게).",
    )
    ap.add_argument(
        "--codepoints",
        nargs="*",
        help="특정 codepoint만 렌더(예: --codepoints 11904 20013)",
    )
    ap.add_argument(
        "--all-svgs",
        action="store_true",
        help="words.csv 추출 대신 resource/svgs 전체를 렌더",
    )
    ap.add_argument(
        "--active-stroke-color",
        type=str,
        default="#35A4FF",
        help="진행 중 획 색상 (CSS color). 기본: #35A4FF",
    )
    ap.add_argument(
        "--done-stroke-color",
        type=str,
        default="#8A93A0",
        help="완료 획 색상 (CSS color). 기본: #8A93A0",
    )
    ap.add_argument(
        "--fill-color",
        type=str,
        default="#5F6773",
        help="한자 채움 색상 (CSS color). 기본: #5F6773",
    )
    ap.add_argument(
        "--show-guide",
        action="store_true",
        help="십자/대각선 가이드 라인 표시",
    )
    args = ap.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()

