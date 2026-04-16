#!/usr/bin/env python3
"""
SDR Incoming Bridge
==================

Purpose
-------
EmbodMocap's `auto_spectacular_rec_service.py` polls:

  <DATA_ROOT>/_incoming/

and decides whether to run the scene-only pipeline or the human pipeline by
parsing ZIP filename tokens:

  recording_<...>__scene=<SCENE>__type=<scene|human>[__seq=seq0][__cam=A|B].zip

If your upload backend stores ZIPs under another directory structure (e.g.
`<DATA_ROOT>/<SCENE>/<SEQ>/<sessionName>.zip`) and/or renames the file so that
those tokens are missing, EmbodMocap won't pick it up automatically.

This script scans for ZIP files under `DATA_ROOT` (excluding `_incoming/`),
rebuilds the tokenized filename by reading `upload_context.json` inside the ZIP,
and then enqueues it into `_incoming/` via hardlink/symlink/copy.

It keeps a small state file to avoid enqueuing the same source ZIP repeatedly.

No third‑party dependencies (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


_SCENE_ALLOWED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SEQ_ALLOWED = re.compile(r"^seq\d+$")
_TYPE_ALLOWED = {"scene", "human"}

_CAPTURE_TYPE_HUMAN = {"human_in_scene", "humaninscene", "human"}
_CAPTURE_TYPE_SCENE = {"scene_only", "sceneonly", "scene"}


@dataclass(frozen=True)
class _SourceFingerprint:
    size: int
    mtime_ns: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "items": {}}
        items = data.get("items")
        if not isinstance(items, dict):
            data["items"] = {}
        data.setdefault("version", 1)
        return data
    except Exception:
        logging.exception("Failed to load state file: %s", path)
        return {"version": 1, "items": {}}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _fingerprint(path: Path) -> _SourceFingerprint:
    st = path.stat()
    return _SourceFingerprint(size=st.st_size, mtime_ns=st.st_mtime_ns)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _iter_zip_files(
    data_root: Path,
    incoming_dir: Path,
    ignored_dir_names: set[str],
) -> Iterable[Path]:
    incoming_resolved = incoming_dir.resolve()
    for dirpath, dirnames, filenames in os.walk(data_root):
        current = Path(dirpath)

        # Skip `_incoming` subtree.
        try:
            if current.resolve() == incoming_resolved:
                dirnames[:] = []
                continue
        except Exception:
            pass

        # Prune dirs in-place.
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ignored_dir_names and not d.startswith(".")
        ]

        for name in filenames:
            if not name.lower().endswith(".zip"):
                continue
            candidate = current / name
            if _is_under(candidate, incoming_resolved):
                continue
            yield candidate


def _parse_tokenized_zip_name(file_name: str) -> Optional[Dict[str, str]]:
    if not file_name.lower().endswith(".zip"):
        return None
    stem = file_name[:-4]
    if "__scene=" not in stem or "__type=" not in stem:
        return None

    tokens: Dict[str, str] = {}
    parts = stem.split("__")
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        tokens[key] = value

    scene = tokens.get("scene")
    type_token = tokens.get("type")
    if not scene or not type_token:
        return None
    if type_token not in _TYPE_ALLOWED:
        return None
    if not _SCENE_ALLOWED.match(scene):
        return None

    if type_token == "human":
        seq = tokens.get("seq")
        cam = tokens.get("cam")
        if not seq or not cam:
            return None
        if not _SEQ_ALLOWED.match(seq):
            return None
        if cam.upper() not in {"A", "B"}:
            return None
    return tokens


def _read_upload_context_from_zip(zip_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
            candidates = [
                n
                for n in names
                if n == "upload_context.json" or n.endswith("/upload_context.json")
            ]
            if not candidates:
                return None
            preferred = (
                "upload_context.json"
                if "upload_context.json" in candidates
                else candidates[0]
            )
            raw = zf.read(preferred)
        decoded = json.loads(raw.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else None
    except Exception:
        logging.exception("Failed to read upload_context.json from zip: %s", zip_path)
        return None


def _build_tokenized_name_from_context(
    *,
    source_zip_path: Path,
    context: Dict[str, Any],
) -> Optional[str]:
    scene_name = str(context.get("sceneName") or "").strip()
    capture_type = str(context.get("captureType") or "").strip()
    seq_name = str(context.get("seqName") or "").strip()
    cam = str(context.get("cam") or "").strip()

    if not scene_name or not _SCENE_ALLOWED.match(scene_name):
        return None

    capture_type_norm = capture_type.strip().lower()
    if capture_type_norm in _CAPTURE_TYPE_HUMAN:
        type_token = "human"
    elif capture_type_norm in _CAPTURE_TYPE_SCENE or not capture_type_norm:
        type_token = "scene"
    else:
        # Unknown capture type: prefer "scene" (safer) rather than failing.
        type_token = "scene"

    base = source_zip_path.stem
    if not base.startswith("recording_"):
        base = f"recording_{base}"

    parts = [f"{base}__scene={scene_name}", f"type={type_token}"]

    if type_token == "human":
        if not seq_name or not _SEQ_ALLOWED.match(seq_name):
            return None
        cam_norm = cam.strip().upper()
        if cam_norm not in {"A", "B"}:
            return None
        parts.append(f"seq={seq_name}")
        parts.append(f"cam={cam_norm}")

    return "__".join(parts) + ".zip"


def _unique_path(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem = dst.stem
    suffix = dst.suffix
    for i in range(1, 1000):
        candidate = dst.with_name(f"{stem}({i}){suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many duplicates for: {dst.name}")


def _ensure_incoming_entry(
    *,
    src: Path,
    incoming_dir: Path,
    incoming_name: str,
    link_method: str,
    dry_run: bool,
) -> Path:
    incoming_dir.mkdir(parents=True, exist_ok=True)
    dst = incoming_dir / incoming_name
    if dst.exists():
        logging.info("Incoming exists, skip: %s", dst)
        return dst

    dst = _unique_path(dst)
    if dry_run:
        logging.info("DRY-RUN enqueue %s -> %s", src, dst)
        return dst

    method_chain = (
        ["hardlink", "symlink", "copy"]
        if link_method == "auto"
        else [link_method]
    )

    last_error: Optional[BaseException] = None
    for method in method_chain:
        try:
            if method == "hardlink":
                os.link(src, dst)
            elif method == "symlink":
                rel = os.path.relpath(src, start=dst.parent)
                os.symlink(rel, dst)
            elif method == "copy":
                shutil.copy2(src, dst)
            else:
                raise ValueError(f"Unknown link method: {method}")
            logging.info("Enqueued via %s: %s", method, dst)
            return dst
        except Exception as e:
            last_error = e
            logging.debug("Failed %s for %s -> %s: %s", method, src, dst, e)
            try:
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
            except Exception:
                pass
            continue

    raise RuntimeError(f"Failed to create incoming entry: {dst}") from last_error


def _compute_incoming_name(zip_path: Path) -> Optional[str]:
    # If the name already matches token format, keep it.
    if _parse_tokenized_zip_name(zip_path.name) is not None:
        return zip_path.name

    context = _read_upload_context_from_zip(zip_path)
    if context is None:
        return None
    return _build_tokenized_name_from_context(
        source_zip_path=zip_path,
        context=context,
    )


def _run_once(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root).expanduser().resolve()
    incoming_dir = (
        Path(args.incoming_dir).expanduser().resolve()
        if args.incoming_dir
        else data_root / "_incoming"
    )
    state_path = (
        Path(args.state_path).expanduser().resolve()
        if args.state_path
        else data_root / ".sdr_incoming_bridge_state.json"
    )

    ignored = set(args.ignore_dir or [])
    ignored.update({incoming_dir.name, ".staging", "__pycache__"})

    state = _load_state(state_path)
    items: Dict[str, Any] = state.get("items", {})

    enqueued = 0
    skipped = 0
    errors = 0

    for zip_path in _iter_zip_files(data_root, incoming_dir, ignored):
        try:
            fp = _fingerprint(zip_path)
        except FileNotFoundError:
            continue
        except Exception:
            logging.exception("Failed to stat: %s", zip_path)
            errors += 1
            continue

        try:
            age_seconds = time.time() - zip_path.stat().st_mtime
        except Exception:
            age_seconds = 999999.0
        if age_seconds < float(args.min_age_seconds):
            skipped += 1
            continue

        try:
            rel_key = str(zip_path.relative_to(data_root))
        except Exception:
            rel_key = str(zip_path)

        prev = items.get(rel_key)
        if isinstance(prev, dict):
            if prev.get("size") == fp.size and prev.get("mtime_ns") == fp.mtime_ns:
                skipped += 1
                continue

        incoming_name = _compute_incoming_name(zip_path)
        if not incoming_name:
            logging.warning("Skip (cannot determine incoming name): %s", zip_path)
            skipped += 1
            continue

        try:
            dst = _ensure_incoming_entry(
                src=zip_path,
                incoming_dir=incoming_dir,
                incoming_name=incoming_name,
                link_method=args.link_method,
                dry_run=args.dry_run,
            )
            items[rel_key] = {
                "size": fp.size,
                "mtime_ns": fp.mtime_ns,
                "incomingName": dst.name,
                "queuedAt": _utc_now_iso(),
            }
            state["items"] = items
            if not args.dry_run:
                _atomic_write_json(state_path, state)
            enqueued += 1
        except Exception:
            logging.exception("Failed to enqueue: %s", zip_path)
            errors += 1

    logging.info(
        "Scan done. enqueued=%d skipped=%d errors=%d state=%s",
        enqueued,
        skipped,
        errors,
        state_path,
    )
    return 0 if errors == 0 else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge backend ZIP layout into EmbodMocap _incoming token zips.",
    )
    parser.add_argument(
        "--data_root",
        required=True,
        help="Dataset root directory containing `_incoming/` and scene folders.",
    )
    parser.add_argument(
        "--incoming_dir",
        default="",
        help="Override incoming dir. Default: <data_root>/_incoming",
    )
    parser.add_argument(
        "--state_path",
        default="",
        help="Override state path. Default: <data_root>/.sdr_incoming_bridge_state.json",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Poll interval seconds (ignored when --once). Default: 2.0",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scan and exit (cron-friendly).",
    )
    parser.add_argument(
        "--min_age_seconds",
        type=float,
        default=2.0,
        help="Skip files newer than this age. Default: 2.0",
    )
    parser.add_argument(
        "--link_method",
        choices=["auto", "hardlink", "symlink", "copy"],
        default="auto",
        help="How to enqueue into _incoming. Default: auto (hardlink->symlink->copy).",
    )
    parser.add_argument(
        "--ignore_dir",
        action="append",
        default=[],
        help="Ignore directory name (can be repeated).",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Log actions without writing anything.",
    )
    parser.add_argument(
        "--log_level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log verbosity. Default: info",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.once:
        return _run_once(args)

    while True:
        code = _run_once(args)
        if code != 0:
            logging.warning("Loop tick finished with code=%d (will continue)", code)
        time.sleep(max(0.2, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())

