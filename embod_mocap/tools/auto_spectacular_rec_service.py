"""
Auto-ingest Spectacular Rec zip uploads (scene-only vs human) by filename convention,
organize into datasets/my_capture/ structure, and (optionally) run the pipeline.

Naming convention (see docs/spectacular_rec_upload_naming_zh.md):

  recording_<...>__scene=<SCENE>__type=<scene|human>[__seq=seq0][__cam=A|B][__stereo=1].zip

Workflow:
  - Users upload zips into: DATA_ROOT/_incoming/
  - This service moves/extracts them into:
      DATA_ROOT/<SCENE>/                          (scene raw files)
      DATA_ROOT/<SCENE>/<SEQ>/recording_*.zip     (human recordings; Step4 auto extracts to raw1/raw2)

Notes:
  - Scene mesh preview automation (Step0-2) exists in tools/auto_scene_mesh_service.py.
    This script supersets that concept and can additionally run Step0-15 when human data is ready.
  - Step1/Step5 typically require a separate conda env (spectacularAI==1.50.0).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from embod_mocap.run_stages import (
    raw_files,
)


SCENE_ALLOWED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SEQ_ALLOWED_RE = re.compile(r"^seq\d+$")


@dataclass(frozen=True)
class IncomingZip:
    path: Path
    scene: str
    type: str  # "scene" | "human"
    seq: Optional[str] = None
    cam: Optional[str] = None  # "A"|"B"|"L"|"R"|...
    stereo_bundle: bool = False
    v1_start: Optional[int] = None
    v2_start: Optional[int] = None
    tokens: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SceneStatus:
    name: str
    path: Path
    has_scene_raw: bool
    has_transforms: bool
    has_mesh_raw: bool
    has_mesh_simplified: bool
    seq_dirs: Tuple[Path, ...]


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def age_seconds(path: Path) -> float:
    try:
        st = path.stat()
    except FileNotFoundError:
        return 0.0
    return max(0.0, time.time() - st.st_mtime)


def is_file_stable(path: Path, stable_seconds: float) -> bool:
    return path.is_file() and age_seconds(path) >= stable_seconds


def _safe_extract_zip(zip_file: zipfile.ZipFile, target_dir: Path) -> None:
    target_real = os.path.realpath(str(target_dir))
    for member in zip_file.infolist():
        name = member.filename
        if not name:
            continue
        member_path = os.path.normpath(name)
        destination = os.path.realpath(os.path.join(str(target_dir), member_path))
        if not (destination == target_real or destination.startswith(target_real + os.sep)):
            raise RuntimeError(f"Unsafe path in zip: {name}")
        zip_file.extract(member, str(target_dir))


def _has_raw_payload_dir(dir_path: Path) -> bool:
    return all((dir_path / name).exists() for name in raw_files)


def _find_payload_roots(extract_root: Path) -> List[Path]:
    """Return all directories that directly contain the 5 raw_files."""
    roots: List[Path] = []
    for current_root, _, _ in os.walk(str(extract_root)):
        p = Path(current_root)
        if _has_raw_payload_dir(p):
            roots.append(p)
    roots.sort(key=lambda p: (len(p.relative_to(extract_root).parts), str(p)))
    return roots


def _parse_tokens_from_stem(stem: str) -> Dict[str, str]:
    parts = stem.split("__")
    tokens: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k or not v:
            continue
        tokens[k] = v
    return tokens


def _normalize_type(raw: str) -> str:
    v = raw.strip().lower()
    if v in {"scene", "s"}:
        return "scene"
    if v in {"human", "h", "person", "with_person"}:
        return "human"
    raise ValueError(f"Invalid type={raw!r}, expected scene/human.")


def _normalize_cam(raw: str) -> str:
    v = raw.strip().upper()
    if v in {"A", "B", "L", "R", "1", "2"}:
        return v
    raise ValueError(f"Invalid cam={raw!r}, expected A/B/L/R/1/2.")


def parse_incoming_zip(path: Path) -> IncomingZip:
    if path.suffix.lower() != ".zip":
        raise ValueError("Not a .zip")

    stem = path.stem
    tokens = _parse_tokens_from_stem(stem)
    if "scene" not in tokens:
        raise ValueError("Missing token: scene=...")
    if "type" not in tokens:
        raise ValueError("Missing token: type=scene|human")

    scene = tokens["scene"]
    if not SCENE_ALLOWED_RE.match(scene):
        raise ValueError(f"Invalid scene name {scene!r}. Allowed: letters/digits/._- (no spaces).")

    kind = _normalize_type(tokens["type"])
    seq: Optional[str] = tokens.get("seq")
    cam: Optional[str] = tokens.get("cam")
    stereo_bundle = str(tokens.get("stereo", "")).strip() in {"1", "true", "yes"}

    v1_start = int(tokens["v1_start"]) if "v1_start" in tokens else None
    v2_start = int(tokens["v2_start"]) if "v2_start" in tokens else None

    if kind == "human":
        if not seq:
            raise ValueError("Missing token for human capture: seq=seq0/seq1/...")
        if not SEQ_ALLOWED_RE.match(seq):
            raise ValueError(f"Invalid seq {seq!r}. Expected like seq0/seq1/seq2...")
        if not stereo_bundle:
            if not cam:
                raise ValueError("Missing token for human capture: cam=A|B (or set stereo=1 for bundle).")
            cam = _normalize_cam(cam)
        else:
            cam = _normalize_cam(cam) if cam else None
    else:
        # scene-only: ignore seq/cam if present
        seq = None
        cam = None

    return IncomingZip(
        path=path,
        scene=scene,
        type=kind,
        seq=seq,
        cam=cam,
        stereo_bundle=stereo_bundle,
        v1_start=v1_start,
        v2_start=v2_start,
        tokens=tuple(sorted(tokens.items())),
    )


def _move_into_dir(src: Path, dst_dir: Path, new_name: Optional[str] = None) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / (new_name if new_name is not None else src.name)
    if dst_path.exists():
        # keep existing; avoid accidental overwrite
        raise FileExistsError(f"Destination already exists: {dst_path}")
    shutil.move(str(src), str(dst_path))
    return dst_path


def is_scene_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name
    if name.startswith((".", "_")):
        return False
    return True


def list_scene_dirs(data_root: Path) -> List[Path]:
    if not data_root.exists():
        return []
    return sorted([p for p in data_root.iterdir() if is_scene_dir(p)])


def list_seq_dirs(scene_dir: Path) -> List[Path]:
    if not scene_dir.exists():
        return []
    return sorted([p for p in scene_dir.iterdir() if p.is_dir() and p.name.startswith("seq")])


def build_scene_status(scene_dir: Path) -> SceneStatus:
    return SceneStatus(
        name=scene_dir.name,
        path=scene_dir,
        has_scene_raw=_has_raw_payload_dir(scene_dir),
        has_transforms=(scene_dir / "transforms.json").exists(),
        has_mesh_raw=(scene_dir / "mesh_raw.ply").exists(),
        has_mesh_simplified=(scene_dir / "mesh_simplified.ply").exists(),
        seq_dirs=tuple(list_seq_dirs(scene_dir)),
    )


def is_human_seq(seq_dir: Path) -> bool:
    # Naming convention: filenames contain "__type=human". We also allow extracted dirs/zips to stay.
    for p in seq_dir.iterdir():
        name = p.name.lower()
        if name.startswith("recording_") and "__type=human" in name:
            return True
    # Fallback: if raw1/raw2 already exist with valid payload, treat as human.
    if seq_has_prepared_raw_views(seq_dir):
        return True
    return False


def list_recording_sources(seq_dir: Path) -> List[Path]:
    sources: List[Path] = []
    for p in sorted(seq_dir.iterdir()):
        if not p.name.startswith("recording_"):
            continue
        if p.is_dir():
            if _has_raw_payload_dir(p):
                sources.append(p)
        elif p.is_file() and p.suffix.lower() == ".zip":
            sources.append(p)
    return sources


def seq_has_prepared_raw_views(seq_dir: Path) -> bool:
    return _has_raw_payload_dir(seq_dir / "raw1") and _has_raw_payload_dir(seq_dir / "raw2")


def infer_v_starts_for_seq(seq_dir: Path) -> Tuple[int, int]:
    # Optional override via filename tokens; otherwise default to (0, 0) to allow auto-run.
    v1 = None
    v2 = None
    for p in seq_dir.iterdir():
        if not (p.is_file() and p.name.startswith("recording_") and p.suffix.lower() == ".zip"):
            continue
        try:
            tokens = _parse_tokens_from_stem(p.stem)
        except Exception:
            continue
        if v1 is None and "v1_start" in tokens:
            try:
                v1 = int(tokens["v1_start"])
            except Exception:
                pass
        if v2 is None and "v2_start" in tokens:
            try:
                v2 = int(tokens["v2_start"])
            except Exception:
                pass
        if v1 is not None and v2 is not None:
            break
    return int(v1) if v1 is not None else 0, int(v2) if v2 is not None else 0


def _ensure_seq0(scene_dir: Path) -> Path:
    seq0 = scene_dir / "seq0"
    seq0.mkdir(parents=True, exist_ok=True)
    return seq0


def _move_zip_unique(zip_path: Path, dst_dir: Path, preferred_name: Optional[str] = None) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    name = preferred_name if preferred_name is not None else zip_path.name
    dst = dst_dir / name
    if not dst.exists():
        shutil.move(str(zip_path), str(dst))
        return dst

    stem = dst.stem
    suffix = dst.suffix
    for i in range(1, 1000):
        cand = dst_dir / f"{stem}({i}){suffix}"
        if not cand.exists():
            shutil.move(str(zip_path), str(cand))
            return cand
    raise RuntimeError(f"Too many duplicate names under {dst_dir}: {name}")


def import_scene_zip_to_scene_dir(
    zip_path: Path,
    scene_dir: Path,
    stable_seconds: float,
    mode: str,
) -> bool:
    """Import a single zip containing the scene raw_files into scene_dir."""
    if not is_file_stable(zip_path, stable_seconds):
        return False

    if mode not in {"skip", "overwrite"}:
        raise ValueError(f"Invalid mode={mode!r}")

    if mode == "skip" and _has_raw_payload_dir(scene_dir):
        # Consume the incoming zip to avoid re-processing loops; keep it under seq0/_imports for traceability.
        _ensure_seq0(scene_dir)
        imports_dir = scene_dir / "seq0" / "_imports"
        _move_zip_unique(zip_path, imports_dir)
        log(f"[INGEST] Skip scene zip (already imported), archived -> {scene_dir.name}/seq0/_imports/")
        return True

    tmp_root = Path(tempfile.mkdtemp(prefix="scene_ingest_", dir=str(scene_dir.parent)))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract_zip(zf, tmp_root)
        payload_roots = _find_payload_roots(tmp_root)
        if not payload_roots:
            raise RuntimeError(f"Zip payload missing required files {raw_files}: {zip_path.name}")

        payload_root = payload_roots[0]
        scene_dir.mkdir(parents=True, exist_ok=True)

        if mode == "overwrite":
            # Only clean conflicting raw inputs; keep other computed assets (mesh/transforms) intact.
            for name in raw_files:
                p = scene_dir / name
                if p.is_symlink() or p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)

        # Move everything under payload root into scene root (including raw_files).
        for item in payload_root.iterdir():
            dst = scene_dir / item.name
            if dst.exists():
                if mode == "skip":
                    continue
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    dst.unlink(missing_ok=True)
            shutil.move(str(item), str(dst))

        if not _has_raw_payload_dir(scene_dir):
            raise RuntimeError(f"After import, scene raw inputs still incomplete: {scene_dir}")

        _ensure_seq0(scene_dir)
        imports_dir = scene_dir / "seq0" / "_imports"
        _move_zip_unique(zip_path, imports_dir)
        log(f"[INGEST] Scene zip imported -> {scene_dir.name}/")
        return True
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def import_human_zip_to_seq_dir(
    zip_path: Path,
    scene_dir: Path,
    seq: str,
    stable_seconds: float,
    mode: str,
    stereo_bundle: bool,
) -> bool:
    if not is_file_stable(zip_path, stable_seconds):
        return False

    if mode not in {"skip", "overwrite"}:
        raise ValueError(f"Invalid mode={mode!r}")

    seq_dir = scene_dir / seq
    seq_dir.mkdir(parents=True, exist_ok=True)

    if not stereo_bundle:
        # Just move the zip into seq/ and keep name (must start with recording_ for Step4 auto handling).
        dst_name = zip_path.name
        if not dst_name.startswith("recording_"):
            dst_name = f"recording_{dst_name}"

        dst_path = seq_dir / dst_name
        if dst_path.exists():
            if mode == "skip":
                # Consume duplicate upload into seq/_imports to avoid loops.
                imports_dir = seq_dir / "_imports"
                _move_zip_unique(zip_path, imports_dir, preferred_name=dst_name)
                log(f"[INGEST] Skip human zip (already exists), archived -> {scene_dir.name}/{seq}/_imports/")
                return True
            dst_path.unlink(missing_ok=True)

        shutil.move(str(zip_path), str(dst_path))
        log(f"[INGEST] Human zip moved -> {scene_dir.name}/{seq}/{dst_name}")
        return True

    # Stereo bundle: extract and split into two recording_*/ dirs for Step4.
    tmp_root = Path(tempfile.mkdtemp(prefix="stereo_bundle_", dir=str(seq_dir)))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract_zip(zf, tmp_root)

        payload_roots = _find_payload_roots(tmp_root)
        if len(payload_roots) < 2:
            raise RuntimeError(
                f"stereo=1 but found {len(payload_roots)} payload root(s) with raw inputs under {zip_path.name}."
            )

        # Deterministic: take first two shallowest.
        payload_roots = payload_roots[:2]
        recording_dirs = [seq_dir / f"recording_{zip_path.stem}__cam=A", seq_dir / f"recording_{zip_path.stem}__cam=B"]
        for rec_dir, payload_root in zip(recording_dirs, payload_roots):
            if rec_dir.exists():
                if mode == "skip":
                    continue
                shutil.rmtree(rec_dir, ignore_errors=True)
            rec_dir.mkdir(parents=True, exist_ok=True)
            for item in payload_root.iterdir():
                shutil.move(str(item), str(rec_dir / item.name))
            if not _has_raw_payload_dir(rec_dir):
                raise RuntimeError(f"Bundle split produced incomplete payload dir: {rec_dir}")

        dst_name = zip_path.name
        if not dst_name.startswith("recording_"):
            dst_name = f"recording_{dst_name}"
        dst_zip = seq_dir / dst_name
        if dst_zip.exists():
            if mode == "overwrite":
                dst_zip.unlink(missing_ok=True)
        if not dst_zip.exists():
            shutil.move(str(zip_path), str(dst_zip))
        else:
            # mode=skip and dst exists: consume to _imports.
            imports_dir = seq_dir / "_imports"
            _move_zip_unique(zip_path, imports_dir, preferred_name=dst_name)
        log(f"[INGEST] Stereo bundle imported -> {scene_dir.name}/{seq}/ (2 payload dirs)")
        return True
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def list_incoming_zips(incoming_dir: Path) -> List[Path]:
    if not incoming_dir.exists():
        return []
    return sorted([p for p in incoming_dir.glob("*.zip") if p.is_file()])


def write_seq_info_xlsx(data_root: Path, out_xlsx: Path) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for scene_dir in list_scene_dirs(data_root):
        for seq_dir in list_seq_dirs(scene_dir):
            rows.append(
                {
                    "scene_folder": scene_dir.name,
                    "seq_name": seq_dir.name,
                    "in_door": True,
                    "v1_start": "-",
                    "v2_start": "-",
                    "character": "-",
                    "skills": (),
                    "keyframes": (),
                    "FAILED": "",
                    "note": "",
                    "contacts": (),
                    "optim_scale": False,
                }
            )
    df = pd.DataFrame(rows)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    if out_xlsx.exists():
        out_xlsx.unlink()
    df.to_excel(out_xlsx, index=False)
    log(f"[XLSX] Wrote {out_xlsx} rows={len(df)}")
    return df


def write_human_autorun_xlsx(
    data_root: Path,
    out_xlsx: Path,
    *,
    require_transforms: bool = False,
) -> pd.DataFrame:
    """Write an xlsx including only human sequences that look ready for Step4+ (>=2 sources).

    When require_transforms=True, only include scenes that already have transforms.json (Step1 done).
    """
    rows: List[Dict[str, object]] = []
    for scene_dir in list_scene_dirs(data_root):
        status = build_scene_status(scene_dir)
        # Full pipeline requires scene raw inputs; transforms (Step1) will be auto-run.
        if not status.has_scene_raw:
            continue
        if require_transforms and not status.has_transforms:
            continue
        for seq_dir in list_seq_dirs(scene_dir):
            if not is_human_seq(seq_dir):
                continue
            if not seq_has_prepared_raw_views(seq_dir):
                sources = list_recording_sources(seq_dir)
                if len(sources) < 2:
                    continue
            v1_start, v2_start = infer_v_starts_for_seq(seq_dir)
            rows.append(
                {
                    "scene_folder": scene_dir.name,
                    "seq_name": seq_dir.name,
                    "in_door": True,
                    "v1_start": int(v1_start),
                    "v2_start": int(v2_start),
                    "character": "-",
                    "skills": (),
                    "keyframes": (),
                    "FAILED": "",
                    "note": "auto",
                    "contacts": (),
                    "optim_scale": False,
                }
            )
    df = pd.DataFrame(rows)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    if out_xlsx.exists():
        out_xlsx.unlink()
    df.to_excel(out_xlsx, index=False)
    log(f"[XLSX] Wrote human autorun xlsx: {out_xlsx} rows={len(df)}")
    return df


def write_filtered_xlsx(df: pd.DataFrame, scene_names: Sequence[str], out_xlsx: Path) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    if out_xlsx.exists():
        out_xlsx.unlink()
    if not scene_names or df.empty:
        pd.DataFrame([]).to_excel(out_xlsx, index=False)
        return
    mask = df["scene_folder"].astype(str).isin(list(scene_names))
    out = df.loc[mask].copy()
    out.to_excel(out_xlsx, index=False)


def run_conda(
    conda_exe: str,
    env_name: str,
    argv: Sequence[str],
    cwd: Path,
) -> int:
    cmd = [conda_exe, "run", "-n", env_name, *argv]
    log(f"[CMD] {' '.join(cmd)} (cwd={cwd})")
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), check=False)
        return int(proc.returncode)
    except FileNotFoundError:
        log(f"[ERROR] conda not found: {conda_exe}")
        return 127


def main() -> None:
    code_root = Path(__file__).resolve().parents[1]  # .../embod_mocap
    parser = argparse.ArgumentParser(description="Auto ingest Spectacular Rec zips by naming convention.")
    parser.add_argument("--data_root", required=True, help="DATA_ROOT, e.g. ../datasets/my_capture")
    parser.add_argument("--incoming", default="_incoming", help="Incoming folder under data_root (default: _incoming)")
    parser.add_argument("--config", default="config_fast.yaml", help="Config yaml for run_stages.py")
    parser.add_argument("--conda", default="conda", help="conda executable name/path")
    parser.add_argument("--env_main", default="embodmocap", help="Conda env for most steps (Step2-4, Step6-15)")
    parser.add_argument("--env_sai", default="embodmocap_sai150", help="Conda env for Step1/Step5 (spectacularAI)")
    parser.add_argument("--stable_seconds", type=float, default=10.0, help="Treat files stable after N seconds since last mtime")
    parser.add_argument("--poll_interval", type=float, default=10.0, help="Polling interval seconds")
    parser.add_argument("--xlsx_out", default="seq_info_all.xlsx", help="xlsx index output (overwritten)")
    parser.add_argument("--mode", default="skip", choices=["skip", "overwrite"], help="run_stages.py --mode (and ingest overwrite behavior)")
    parser.add_argument("--force_all", action="store_true", help="Pass --force_all to run_stages.py")
    parser.add_argument("--no_auto_run", action="store_true", help="Only ingest + write xlsx; do not run any pipeline steps")
    parser.add_argument("--skip_scene_steps", action="store_true", help="Do not run scene-only Step1/2 automation")
    parser.add_argument("--skip_human_steps", action="store_true", help="Do not run human Step0-15 automation")
    parser.add_argument("--run_once", action="store_true", help="Run one ingest cycle then exit")
    parser.add_argument("--dry_run", action="store_true", help="Only print planned actions")
    args = parser.parse_args()

    data_root = (code_root / args.data_root).resolve() if not os.path.isabs(args.data_root) else Path(args.data_root).resolve()
    incoming_dir = data_root / args.incoming
    xlsx_out = (code_root / args.xlsx_out).resolve() if not os.path.isabs(args.xlsx_out) else Path(args.xlsx_out).resolve()

    log(f"[START] data_root={data_root}")
    log(f"[START] incoming_dir={incoming_dir}")
    log(f"[START] mode={args.mode} config={args.config}")

    data_root.mkdir(parents=True, exist_ok=True)
    incoming_dir.mkdir(parents=True, exist_ok=True)

    bad_dir = incoming_dir / "_bad"
    bad_dir.mkdir(parents=True, exist_ok=True)

    while True:
        for zip_path in list_incoming_zips(incoming_dir):
            if not is_file_stable(zip_path, args.stable_seconds):
                continue
            try:
                info = parse_incoming_zip(zip_path)
            except Exception as exc:
                log(f"[WARN] Bad incoming name, moving to _bad/: {zip_path.name} ({exc})")
                if not args.dry_run:
                    _move_into_dir(zip_path, bad_dir)
                continue

            scene_dir = data_root / info.scene
            if args.dry_run:
                log(f"[DRY] Would ingest: {zip_path.name} -> scene={info.scene} type={info.type} seq={info.seq} cam={info.cam} stereo={info.stereo_bundle}")
                continue

            try:
                if info.type == "scene":
                    import_scene_zip_to_scene_dir(zip_path, scene_dir, args.stable_seconds, mode=args.mode)
                else:
                    assert info.seq is not None
                    import_human_zip_to_seq_dir(
                        zip_path,
                        scene_dir=scene_dir,
                        seq=info.seq,
                        stable_seconds=args.stable_seconds,
                        mode=args.mode,
                        stereo_bundle=info.stereo_bundle,
                    )
            except Exception as exc:
                log(f"[ERROR] Ingest failed for {zip_path.name}: {exc}")

        if args.dry_run:
            if args.run_once:
                return
            time.sleep(args.poll_interval)
            continue

        df_all = write_seq_info_xlsx(data_root=data_root, out_xlsx=xlsx_out)

        if not args.no_auto_run:
            # 1) Scene-only build: Step1 + Step2 (mesh preview).
            if not args.skip_scene_steps:
                statuses = {p.name: build_scene_status(p) for p in list_scene_dirs(data_root)}
                ready_for_step1 = [
                    s.name for s in statuses.values() if s.has_scene_raw and len(s.seq_dirs) > 0 and not s.has_transforms
                ]
                if ready_for_step1:
                    step1_xlsx = xlsx_out.with_name("seq_info_step1.xlsx")
                    write_filtered_xlsx(df_all, ready_for_step1, step1_xlsx)
                    step1_argv = [
                        "python",
                        "run_stages.py",
                        str(step1_xlsx),
                        "--data_root",
                        str(data_root),
                        "--config",
                        args.config,
                        "--steps",
                        "1",
                        "--mode",
                        args.mode,
                    ]
                    if args.force_all:
                        step1_argv.append("--force_all")
                    run_conda(args.conda, args.env_sai, step1_argv, cwd=code_root)
                else:
                    log("[STEP1] Nothing to do")

                statuses = {p.name: build_scene_status(p) for p in list_scene_dirs(data_root)}
                ready_for_step2 = [
                    s.name
                    for s in statuses.values()
                    if s.has_scene_raw and s.has_transforms and len(s.seq_dirs) > 0 and (not s.has_mesh_raw)
                ]
                if ready_for_step2:
                    step2_xlsx = xlsx_out.with_name("seq_info_step2.xlsx")
                    write_filtered_xlsx(df_all, ready_for_step2, step2_xlsx)
                    step2_argv = [
                        "python",
                        "run_stages.py",
                        str(step2_xlsx),
                        "--data_root",
                        str(data_root),
                        "--config",
                        args.config,
                        "--steps",
                        "2",
                        "--mode",
                        args.mode,
                    ]
                    if args.force_all:
                        step2_argv.append("--force_all")
                    run_conda(args.conda, args.env_main, step2_argv, cwd=code_root)
                else:
                    log("[STEP2] Nothing to do")

            # 2) Human full pipeline: Step2-4 (main), Step5 (sai), Step6-15 (main).
            if not args.skip_human_steps:
                human_xlsx = xlsx_out.with_name("seq_info_human_autorun.xlsx")
                df_human = write_human_autorun_xlsx(data_root=data_root, out_xlsx=human_xlsx, require_transforms=False)
                if df_human.empty:
                    log("[HUMAN] Nothing to do (no ready human sequences).")
                else:
                    step1h_argv = [
                        "python",
                        "run_stages.py",
                        str(human_xlsx),
                        "--data_root",
                        str(data_root),
                        "--config",
                        args.config,
                        "--steps",
                        "1",
                        "--mode",
                        args.mode,
                    ]
                    if args.force_all:
                        step1h_argv.append("--force_all")
                    run_conda(args.conda, args.env_sai, step1h_argv, cwd=code_root)

                    human_ready_xlsx = xlsx_out.with_name("seq_info_human_ready.xlsx")
                    df_human_ready = write_human_autorun_xlsx(
                        data_root=data_root,
                        out_xlsx=human_ready_xlsx,
                        require_transforms=True,
                    )
                    if df_human_ready.empty:
                        log("[HUMAN] Waiting for transforms.json (Step1) to be ready.")
                        # No sequences are ready for Step2+ yet.
                        pass
                    else:
                        step24_argv = [
                            "python",
                            "run_stages.py",
                            str(human_ready_xlsx),
                            "--data_root",
                            str(data_root),
                            "--config",
                            args.config,
                            "--steps",
                            "2-4",
                            "--mode",
                            args.mode,
                        ]
                        if args.force_all:
                            step24_argv.append("--force_all")
                        run_conda(args.conda, args.env_main, step24_argv, cwd=code_root)

                        step5_argv = [
                            "python",
                            "run_stages.py",
                            str(human_ready_xlsx),
                            "--data_root",
                            str(data_root),
                            "--config",
                            args.config,
                            "--steps",
                            "5",
                            "--mode",
                            args.mode,
                        ]
                        if args.force_all:
                            step5_argv.append("--force_all")
                        run_conda(args.conda, args.env_sai, step5_argv, cwd=code_root)

                        step615_argv = [
                            "python",
                            "run_stages.py",
                            str(human_ready_xlsx),
                            "--data_root",
                            str(data_root),
                            "--config",
                            args.config,
                            "--steps",
                            "6-15",
                            "--mode",
                            args.mode,
                        ]
                        if args.force_all:
                            step615_argv.append("--force_all")
                        run_conda(args.conda, args.env_main, step615_argv, cwd=code_root)

        if args.run_once:
            return
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
