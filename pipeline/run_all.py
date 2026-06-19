"""Full-run orchestrator — all 203 languages x all chapters, resumable + thermal-safe.

Phase-batched for the single GPU (Qwen and NLLB can't co-reside in VRAM):

  1) --phase nllb    (NLLB-3.3B loaded)  -> body for ALL langs + SEO for Tier-2
  2) --phase qwen    (Qwen loaded in LM Studio) -> SEO for Tier-1
  3) --phase assemble (no GPU)           -> merge caches + English skeleton -> final BCP-47 JSON

Resume: every unit's result is cached on disk (pipeline/work/{body,seo}/{bcp47}/<file>);
an already-cached unit is skipped, so stop/restart anytime and it continues where it left off.

Thermal safety: polls nvidia-smi between chapters; pauses at --max-temp, resumes under
--resume-temp; optional periodic fixed break.

Examples:
  # small smoke test first:
  python pipeline/run_all.py --phase nllb --langs spa_Latn,cym_Latn --limit-chapters 2
  python pipeline/run_all.py --phase assemble --langs spa_Latn,cym_Latn --limit-chapters 2
  # full run:
  python pipeline/run_all.py --phase nllb     # (NLLB loaded; Qwen unloaded)
  python pipeline/run_all.py --phase qwen     # (Qwen loaded in LM Studio)
  python pipeline/run_all.py --phase assemble
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import config
import fields

REPO = Path(__file__).resolve().parents[1]
EN_ROOT = REPO / "content-source" / "en"
WORK = Path(__file__).resolve().parent / "work"


@dataclass
class Unit:
    book: str        # e.g. "Isaiah" (dir name, mirrors content-source/en)
    file: str        # e.g. "isaiah_14.json"
    en: dict         # parsed English chapter


def gpu_temp() -> int | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=15,
        ).decode().strip().splitlines()
        return int(out[0])
    except Exception:
        return None


def thermal_guard(max_temp: int, resume_temp: int, poll: int) -> None:
    t = gpu_temp()
    if t is None or t < max_temp:
        return
    print(f"  [thermal] GPU {t}°C >= {max_temp}°C — cooling down...", flush=True)
    while True:
        time.sleep(poll)
        t = gpu_temp()
        if t is None or t <= resume_temp:
            print(f"  [thermal] GPU {t}°C — resuming.", flush=True)
            return


def load_units(limit: int | None) -> list[Unit]:
    units: list[Unit] = []
    for book in sorted(p for p in EN_ROOT.iterdir() if p.is_dir() and p.name != "articles"):
        jdir = book / "json"
        if not jdir.is_dir():
            continue
        for f in sorted(jdir.glob("*.json")):
            units.append(Unit(book.name, f.name, json.loads(f.read_text(encoding="utf-8"))))
    units.sort(key=lambda u: (u.book, u.file))
    return units[:limit] if limit else units


def resolve_langs(arg: str | None) -> list[str]:
    if not arg:
        return config.all_flores_codes()
    codes = [c.strip() for c in arg.split(",") if c.strip()]
    for c in codes:
        if c not in config.FLORES_TO_BCP47:
            raise SystemExit(f"Unknown FLORES code {c!r}")
    return codes


class Progress:
    def __init__(self, total: int, phase: str, heartbeat: int) -> None:
        self.total, self.phase, self.heartbeat = total, phase, heartbeat
        self.done = self.skipped = 0
        self.t0 = self.last_beat = time.perf_counter()

    def tick(self, label: str, was_cached: bool) -> None:
        self.done += 1
        if was_cached:
            self.skipped += 1
        now = time.perf_counter()
        if now - self.last_beat >= self.heartbeat or self.done == self.total:
            self.last_beat = now
            elapsed = now - self.t0
            worked = self.done - self.skipped
            rate = worked / elapsed if worked else 0
            remaining = self.total - self.done
            eta = (remaining / rate) if rate else 0
            temp = gpu_temp()
            print(f"  [{self.phase}] {self.done}/{self.total} "
                  f"({self.skipped} cached) | {label} | "
                  f"GPU {temp}°C | {rate*60:.1f}/min | ETA {eta/3600:.1f}h", flush=True)
            self._persist(elapsed, eta)

    def _persist(self, elapsed: float, eta: float) -> None:
        (WORK / f"progress_{self.phase}.json").write_text(json.dumps({
            "phase": self.phase, "done": self.done, "total": self.total,
            "skipped_cached": self.skipped, "elapsed_s": round(elapsed),
            "eta_s": round(eta), "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")


def _cache(kind: str, bcp: str, file: str) -> Path:
    return WORK / kind / bcp / file


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def run_nllb(args, units, langs) -> None:
    import coordinator
    from nllb_engine import NLLBEngine
    print(f"Loading NLLB ({args.nllb_model} on {args.nllb_device})...", flush=True)
    t0 = time.perf_counter()
    nllb = NLLBEngine(model_id=args.nllb_model, device=args.nllb_device)
    print(f"  loaded in {time.perf_counter()-t0:.1f}s", flush=True)

    prog = Progress(len(langs) * len(units), "nllb", args.heartbeat_secs)
    for li, flores in enumerate(langs):
        bcp, nllb_seo = config.bcp47(flores), config.seo_engine(flores) == "nllb"
        for ci, u in enumerate(units):
            thermal_guard(args.max_temp, args.resume_temp, args.temp_poll)
            cached = True
            bc = _cache("body", bcp, u.file)
            if not bc.exists():
                _write_json(bc, {"content": coordinator.translate_body(u.en, flores, nllb)})
                cached = False
            if nllb_seo:  # Tier-2 + demoted Tier-1 (config.SEO_VIA_NLLB)
                sc = _cache("seo", bcp, u.file)
                if not sc.exists():
                    _write_json(sc, coordinator.translate_seo_nllb(u.en, flores, nllb))
                    cached = False
            prog.tick(f"{bcp}/{u.file}", cached)
            if args.break_every and (ci + 1) % args.break_every == 0 and args.break_secs:
                time.sleep(args.break_secs)


def run_qwen(args, units, langs) -> None:
    import client
    if args.qwen_model:
        config.MODEL_ID = args.qwen_model
    qwen_langs = [f for f in langs if config.seo_engine(f) == "qwen"]
    print(f"Qwen SEO phase: {len(qwen_langs)} languages (model {config.MODEL_ID})", flush=True)
    prog = Progress(len(qwen_langs) * len(units), "qwen", args.heartbeat_secs)
    for flores in qwen_langs:
        bcp, name = config.bcp47(flores), config.language_name(flores)
        for ci, u in enumerate(units):
            thermal_guard(args.max_temp, args.resume_temp, args.temp_poll)
            cached = True
            sc = _cache("seo", bcp, u.file)
            if not sc.exists():
                seo, _ = client.translate_seo(u.en, name, verbose=False)
                _write_json(sc, seo)
                cached = False
            prog.tick(f"{bcp}/{u.file}", cached)
            if args.break_every and (ci + 1) % args.break_every == 0 and args.break_secs:
                time.sleep(args.break_secs)


def run_assemble(args, units, langs) -> None:
    import validate
    out_root = (REPO / args.out_root) if not Path(args.out_root).is_absolute() else Path(args.out_root)
    assembled = incomplete = tag_fail = 0
    for flores in langs:
        bcp = config.bcp47(flores)
        for u in units:
            bc, sc = _cache("body", bcp, u.file), _cache("seo", bcp, u.file)
            if not (bc.exists() and sc.exists()):
                incomplete += 1
                continue
            body = json.loads(bc.read_text(encoding="utf-8"))["content"]
            seo = json.loads(sc.read_text(encoding="utf-8"))
            out_obj = fields.reinsert(u.en, {"content": body, **seo})
            dest = out_root / bcp / u.book / "json" / u.file
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            et, _ = validate._profile(u.en.get("content", ""))
            ot, _ = validate._profile(out_obj.get("content", ""))
            if et != ot:
                tag_fail += 1
                print(f"  [tag mismatch] {bcp}/{u.file}", flush=True)
            assembled += 1
    print(f"\nAssembled {assembled} files -> {out_root}", flush=True)
    print(f"  incomplete (missing body or seo cache): {incomplete}", flush=True)
    print(f"  HTML tag mismatches: {tag_fail}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Resumable, thermal-safe full translation run.")
    ap.add_argument("--phase", required=True, choices=["nllb", "qwen", "assemble"])
    ap.add_argument("--langs", help="Comma FLORES codes (default: all 203)")
    ap.add_argument("--limit-chapters", type=int, help="Only the first N chapters (testing)")
    ap.add_argument("--chapter", help="Only this chapter, e.g. isaiah_14 (testing)")
    ap.add_argument("--max-temp", type=int, default=80, help="Pause at/above this GPU °C")
    ap.add_argument("--resume-temp", type=int, default=65, help="Resume under this GPU °C")
    ap.add_argument("--temp-poll", type=int, default=10, help="Cooldown poll seconds")
    ap.add_argument("--break-every", type=int, default=0, help="Fixed break every N chapters")
    ap.add_argument("--break-secs", type=int, default=0, help="Fixed break duration (s)")
    ap.add_argument("--heartbeat-secs", type=int, default=30)
    ap.add_argument("--nllb-model", default="facebook/nllb-200-3.3B")
    ap.add_argument("--nllb-device", default="cuda")
    ap.add_argument("--qwen-model", help="Override Qwen MODEL_ID")
    ap.add_argument("--out-root", default="content-source", help="Assemble output root")
    args = ap.parse_args()

    cols = config.bcp47_collisions()
    if cols:
        raise SystemExit(f"BCP-47 collisions in mapping: {cols}")

    WORK.mkdir(parents=True, exist_ok=True)
    units = load_units(None if args.chapter else args.limit_chapters)
    if args.chapter:
        stem = args.chapter.replace(".json", "")
        units = [u for u in units if u.file.replace(".json", "") == stem]
        if not units:
            raise SystemExit(f"Chapter {args.chapter!r} not found under content-source/en/**/json/")
    langs = resolve_langs(args.langs)
    print(f"Phase: {args.phase} | langs: {len(langs)} | chapters: {len(units)}", flush=True)

    if args.phase == "nllb":
        run_nllb(args, units, langs)
    elif args.phase == "qwen":
        run_qwen(args, units, langs)
    else:
        run_assemble(args, units, langs)


if __name__ == "__main__":
    main()
