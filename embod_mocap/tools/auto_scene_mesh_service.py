"""
自动化：监控 DATA_ROOT，将新上传的 scene/zip 规范化后跑 Step0/1/2，供 Viser 选择预览。

你将得到：
  1) 自动生成/覆盖 Step0 总表 xlsx（默认：seq_info_all.xlsx）
  2) 对新增/未完成的 scene 自动跑 Step1（sai）+ Step2（recon_scene）
  3) 可选：将 seq 下 recording_*.zip 自动解压为 raw1/raw2（保留原 zip）
  4) 可选：将 data_root 根目录下的 zip 作为“scene 包”导入为一个 scene 目录

部署建议：
  - 本脚本作为后台服务跑（systemd --user 最方便）
  - Viser 预览服务用 tools/preview_scene_meshes_viser.py 单独起一个服务

注意：
  - Step1 需要 spectacularAI/sai-cli 环境，通常在 conda env: embodmocap_sai150
  - Step2 需要主环境，通常在 conda env: embodmocap
  - 本脚本只做 Step0/1/2 的自动化；更后续的人体流程不在这里跑
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from auto_service_utils import SceneLock, run_logged

from embod_mocap.run_stages import (
    ensure_raw_input_ready,
    extract_recording_zip_to_raw,
    raw_files,
    _find_recording_payload_root,  # type: ignore
)


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


def list_scene_dirs(data_root: Path) -> List[Path]:
    if not data_root.exists():
        return []
    scene_dirs: List[Path] = []
    for p in sorted(data_root.iterdir()):
        if p.name.startswith((".", "_")):
            continue
        if p.is_dir():
            scene_dirs.append(p)
    return scene_dirs


def list_seq_dirs(scene_dir: Path) -> List[Path]:
    seqs: List[Path] = []
    if not scene_dir.exists():
        return seqs
    for p in sorted(scene_dir.iterdir()):
        if p.is_dir() and p.name.startswith("seq"):
            seqs.append(p)
    return seqs


def ensure_seq0(scene_dir: Path) -> Path:
    seq_dirs = list_seq_dirs(scene_dir)
    if seq_dirs:
        return seq_dirs[0]
    seq0 = scene_dir / "seq0"
    seq0.mkdir(parents=True, exist_ok=True)
    return seq0


def age_seconds(path: Path) -> float:
    try:
        st = path.stat()
    except FileNotFoundError:
        return 0.0
    return max(0.0, time.time() - st.st_mtime)


def is_file_stable(path: Path, stable_seconds: float) -> bool:
    if not path.exists():
        return False
    if not path.is_file():
        return False
    return age_seconds(path) >= stable_seconds


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


def _top_level_dir_if_single(extract_root: Path) -> Optional[Path]:
    entries = [p for p in extract_root.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return None


def import_scene_zip(
    zip_path: Path,
    data_root: Path,
    stable_seconds: float,
    keep_zip_under_seq: bool = True,
) -> Optional[Path]:
    """
    Import a zip placed directly under data_root into a scene folder.

    Supported zip layouts:
      A) zip contains a single top-level folder: <scene_name>/...
      B) zip root directly contains raw_files (calibration.json, data.mov, ...)
      C) zip contains nested folder; we locate the payload root that has raw_files.

    Returns the created scene directory path, or None when not imported.
    """
    if not is_file_stable(zip_path, stable_seconds):
        return None

    scene_name_guess = zip_path.stem
    tmp_root = Path(tempfile.mkdtemp(prefix="scene_zip_", dir=str(data_root)))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract_zip(zf, tmp_root)

        single = _top_level_dir_if_single(tmp_root)
        payload_root = _find_recording_payload_root(str(tmp_root))
        payload_root_path = Path(payload_root) if payload_root is not None else None

        if single is not None:
            scene_name_guess = single.name
        if payload_root_path is not None and payload_root_path.name.startswith(("scene_", "recording_")):
            scene_name_guess = payload_root_path.name

        scene_dir = data_root / scene_name_guess
        if scene_dir.exists() and any(scene_dir.iterdir()):
            log(f"[IMPORT] Skip {zip_path.name}: target scene already exists and is non-empty: {scene_dir}")
            return None

        scene_dir.mkdir(parents=True, exist_ok=True)

        if payload_root_path is not None:
            for item in payload_root_path.iterdir():
                shutil.move(str(item), str(scene_dir / item.name))
        elif single is not None and (data_root / single.name) == scene_dir:
            for item in single.iterdir():
                shutil.move(str(item), str(scene_dir / item.name))
        else:
            for item in tmp_root.iterdir():
                if item.name.startswith("."):
                    continue
                shutil.move(str(item), str(scene_dir / item.name))

        seq0 = ensure_seq0(scene_dir)
        if keep_zip_under_seq:
            imports_dir = seq0 / "_imports"
            imports_dir.mkdir(parents=True, exist_ok=True)
            dst_zip = imports_dir / zip_path.name
            if not dst_zip.exists():
                shutil.move(str(zip_path), str(dst_zip))
            else:
                zip_path.unlink(missing_ok=True)

        log(f"[IMPORT] Imported {zip_path.name} -> {scene_dir.name}/")
        return scene_dir
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def has_scene_raw_files(scene_dir: Path) -> bool:
    return all((scene_dir / name).exists() for name in raw_files)


def ensure_scene_raw_from_zip(scene_dir: Path, stable_seconds: float) -> bool:
    """
    If scene root raw_files are missing, try to extract a scene-level zip under scene_dir
    into a hidden folder and symlink required raw_files into the scene root.
    """
    if has_scene_raw_files(scene_dir):
        return True

    candidates = sorted(
        [p for p in scene_dir.glob("*.zip") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return False

    scene_raw_dir = scene_dir / "_scene_raw"
    if scene_raw_dir.exists() and all((scene_raw_dir / name).exists() for name in raw_files):
        pass
    else:
        scene_raw_dir.mkdir(parents=True, exist_ok=True)
        for zip_path in candidates:
            if not is_file_stable(zip_path, stable_seconds):
                continue
            tmp_root = Path(tempfile.mkdtemp(prefix="scene_raw_", dir=str(scene_dir)))
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    _safe_extract_zip(zf, tmp_root)
                payload_root = _find_recording_payload_root(str(tmp_root))
                if payload_root is None:
                    continue
                payload_root_path = Path(payload_root)
                for item in payload_root_path.iterdir():
                    shutil.move(str(item), str(scene_raw_dir / item.name))
                break
            finally:
                shutil.rmtree(tmp_root, ignore_errors=True)

    if not all((scene_raw_dir / name).exists() for name in raw_files):
        return False

    for name in raw_files:
        dst = scene_dir / name
        src = scene_raw_dir / name
        if dst.exists():
            continue
        try:
            os.symlink(src, dst, target_is_directory=src.is_dir())
        except Exception:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    return has_scene_raw_files(scene_dir)


def ensure_seq_raw_inputs(seq_dir: Path, stable_seconds: float, auto_extract_zip: bool) -> None:
    raw1 = seq_dir / "raw1"
    raw2 = seq_dir / "raw2"

    if raw1.exists() and not raw1.is_dir():
        raise NotADirectoryError(f"{raw1} exists but is not a directory")
    if raw2.exists() and not raw2.is_dir():
        raise NotADirectoryError(f"{raw2} exists but is not a directory")

    missing: List[Tuple[str, Path]] = []
    if not raw1.exists():
        missing.append(("raw1", raw1))
    if not raw2.exists():
        missing.append(("raw2", raw2))

    if not missing:
        ensure_raw_input_ready(str(raw1))
        ensure_raw_input_ready(str(raw2))
        return

    exist_items = sorted(p.name for p in seq_dir.iterdir() if not p.name.startswith("."))
    recording_dirs = [
        name for name in exist_items if name.startswith("recording_") and (seq_dir / name).is_dir()
    ]
    recording_zips = [
        name
        for name in exist_items
        if name.startswith("recording_") and name.lower().endswith(".zip") and (seq_dir / name).is_file()
    ]

    selected_sources: List[Tuple[str, str]] = []
    for source_name in recording_dirs:
        selected_sources.append(("dir", source_name))
        if len(selected_sources) >= len(missing):
            break

    if len(selected_sources) < len(missing):
        if not auto_extract_zip:
            return
        for source_name in recording_zips:
            source_path = seq_dir / source_name
            if not is_file_stable(source_path, stable_seconds):
                continue
            selected_sources.append(("zip", source_name))
            if len(selected_sources) >= len(missing):
                break

    if len(selected_sources) < len(missing):
        return

    for (target_name, target_path), (source_kind, source_name) in zip(missing, selected_sources):
        source_path = seq_dir / source_name
        if source_kind == "dir":
            log(f"[SEQ] Rename {source_name} -> {target_name}/ under {seq_dir}")
            source_path.rename(target_path)
        else:
            log(f"[SEQ] Extract {source_name} -> {target_name}/ under {seq_dir}")
            extract_recording_zip_to_raw(str(source_path), str(target_path))

    ensure_raw_input_ready(str(raw1))
    ensure_raw_input_ready(str(raw2))


def build_scene_status(scene_dir: Path) -> SceneStatus:
    seq_dirs = tuple(list_seq_dirs(scene_dir))
    return SceneStatus(
        name=scene_dir.name,
        path=scene_dir,
        has_scene_raw=has_scene_raw_files(scene_dir),
        has_transforms=(scene_dir / "transforms.json").exists(),
        has_mesh_raw=(scene_dir / "mesh_raw.ply").exists(),
        has_mesh_simplified=(scene_dir / "mesh_simplified.ply").exists(),
        seq_dirs=seq_dirs,
    )


def write_seq_info_xlsx(data_root: Path, out_xlsx: Path, ensure_seq0_flag: bool) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for scene_dir in list_scene_dirs(data_root):
        if ensure_seq0_flag:
            ensure_seq0(scene_dir)
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


def write_filtered_xlsx(df: pd.DataFrame, scene_names: Sequence[str], out_xlsx: Path) -> None:
    if out_xlsx.exists():
        out_xlsx.unlink()
    if not scene_names:
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
    log_path: Optional[Path] = None,
) -> int:
    cmd = [conda_exe, "run", "-n", env_name, *argv]
    log(f"[CMD] {' '.join(cmd)} (cwd={cwd})")
    try:
        if log_path is not None:
            return run_logged(cmd, cwd=cwd, log_path=log_path)
        proc = subprocess.run(cmd, cwd=str(cwd), check=False)
        return int(proc.returncode)
    except FileNotFoundError:
        log(f"[ERROR] conda not found: {conda_exe}")
        return 127


def _cycle_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _log_file(log_root: Path, scene: str, cycle_id: str, tag: str) -> Path:
    safe_scene = scene.strip().replace(os.sep, "_")
    safe_tag = tag.strip().replace(os.sep, "_")
    return log_root / safe_scene / f"{cycle_id}__{safe_tag}.log"


def main() -> None:
    code_root = Path(__file__).resolve().parents[1]  # .../embod_mocap
    parser = argparse.ArgumentParser(description="Auto ingest + Step0/1/2 builder service for scene mesh preview.")
    parser.add_argument("--data_root", required=True, help="DATA_ROOT, e.g. ../datasets/my_capture")
    parser.add_argument("--config", default="config_fast.yaml", help="Config yaml for run_stages.py")
    parser.add_argument("--xlsx_out", default="seq_info_all.xlsx", help="Step0 output xlsx (will be overwritten)")
    parser.add_argument("--poll_interval", type=float, default=30.0, help="Polling interval seconds")
    parser.add_argument("--stable_seconds", type=float, default=10.0, help="Treat files stable after N seconds since last mtime")
    parser.add_argument("--conda", default="conda", help="conda executable name/path")
    parser.add_argument("--env_step1", default="embodmocap_sai150", help="Conda env for Step1")
    parser.add_argument("--env_step2", default="embodmocap", help="Conda env for Step2")
    parser.add_argument("--mode", default="skip", choices=["skip", "overwrite"], help="run_stages.py --mode")
    parser.add_argument("--force_all", action="store_true", help="Pass --force_all to run_stages.py")
    parser.add_argument(
        "--lock_dir",
        default="_locks",
        help="Scene lock directory (default: DATA_ROOT/_locks). Use absolute path to override.",
    )
    parser.add_argument("--lock_wait_seconds", type=float, default=0.0, help="Wait up to N seconds for a scene lock (default: 0 = skip when busy)")
    parser.add_argument("--lock_poll_seconds", type=float, default=2.0, help="Lock polling interval while waiting")
    parser.add_argument(
        "--lock_stale_seconds",
        type=float,
        default=0.0,
        help="Auto-break stale locks older than N seconds (default: 0 = disabled). Only breaks when pid is gone on the same host.",
    )
    parser.add_argument(
        "--log_dir",
        default="_logs/auto_scene_mesh_service",
        help="Persistent log root (default: DATA_ROOT/_logs/auto_scene_mesh_service). Use absolute path to override.",
    )
    parser.add_argument("--run_once", action="store_true", help="Run one scan/build cycle then exit")
    parser.add_argument("--ensure_seq0", action="store_true", help="Create seq0 for scenes with no seq* dirs")
    parser.add_argument(
        "--auto_import_scene_zips",
        action="store_true",
        help="Import *.zip placed directly under data_root as a new scene directory",
    )
    parser.add_argument(
        "--auto_extract_seq_zips",
        action="store_true",
        help="Auto-extract seq/recording_*.zip into raw1/raw2 when missing (zip kept)",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Only print planned actions (do not move/extract/run steps)",
    )
    args = parser.parse_args()

    data_root = (code_root / args.data_root).resolve() if not os.path.isabs(args.data_root) else Path(args.data_root).resolve()
    xlsx_out = (code_root / args.xlsx_out).resolve() if not os.path.isabs(args.xlsx_out) else Path(args.xlsx_out).resolve()
    cfg_path = args.config
    lock_root = (data_root / args.lock_dir).resolve() if not os.path.isabs(args.lock_dir) else Path(args.lock_dir).resolve()
    log_root = (data_root / args.log_dir).resolve() if not os.path.isabs(args.log_dir) else Path(args.log_dir).resolve()
    lock_stale_seconds = args.lock_stale_seconds if args.lock_stale_seconds and args.lock_stale_seconds > 0 else None

    log(f"[START] data_root={data_root}")
    log(f"[START] code_root={code_root}")
    log(f"[START] lock_root={lock_root} wait={args.lock_wait_seconds}s stale={lock_stale_seconds}")
    log(f"[START] log_root={log_root}")

    data_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    lock_root.mkdir(parents=True, exist_ok=True)

    while True:
        if args.auto_import_scene_zips:
            for zip_path in sorted(data_root.glob("*.zip")):
                if args.dry_run:
                    if is_file_stable(zip_path, args.stable_seconds):
                        log(f"[DRY] Would import scene zip: {zip_path.name}")
                    continue
                import_scene_zip(
                    zip_path=zip_path,
                    data_root=data_root,
                    stable_seconds=args.stable_seconds,
                    keep_zip_under_seq=True,
                )

        scene_dirs = list_scene_dirs(data_root)

        statuses: Dict[str, SceneStatus] = {}
        for scene_dir in scene_dirs:
            if args.ensure_seq0 and not list_seq_dirs(scene_dir):
                if args.dry_run:
                    log(f"[DRY] Would create {scene_dir.name}/seq0")
                else:
                    ensure_seq0(scene_dir)

            if not has_scene_raw_files(scene_dir):
                if args.dry_run:
                    log(f"[DRY] Would try to fill scene raw_files from zip under: {scene_dir.name}/")
                else:
                    ensure_scene_raw_from_zip(scene_dir, stable_seconds=args.stable_seconds)

            if args.auto_extract_seq_zips:
                for seq_dir in list_seq_dirs(scene_dir):
                    if args.dry_run:
                        log(f"[DRY] Would ensure raw1/raw2 under {scene_dir.name}/{seq_dir.name}")
                        continue
                    try:
                        ensure_seq_raw_inputs(
                            seq_dir=seq_dir,
                            stable_seconds=args.stable_seconds,
                            auto_extract_zip=True,
                        )
                    except Exception as exc:
                        log(f"[WARN] Seq import failed: {scene_dir.name}/{seq_dir.name}: {exc}")

            statuses[scene_dir.name] = build_scene_status(scene_dir)

        if args.dry_run:
            log(f"[DRY] Would write xlsx: {xlsx_out}")
            if args.run_once:
                return
            time.sleep(args.poll_interval)
            continue

        df = write_seq_info_xlsx(data_root=data_root, out_xlsx=xlsx_out, ensure_seq0_flag=args.ensure_seq0)

        cycle_id = _cycle_id()

        def _acquire_scene_lock(scene_name: str) -> Optional[SceneLock]:
            lock = SceneLock(
                lock_root=lock_root,
                scene=scene_name,
                holder="auto_scene_mesh_service",
                stale_seconds=lock_stale_seconds,
            )
            ok = lock.acquire(wait_seconds=args.lock_wait_seconds, poll_seconds=args.lock_poll_seconds)
            if not ok:
                meta = lock.read_meta_text().strip()
                log(f"[LOCK] Skip {scene_name}: busy. meta={meta or '<missing>'}")
                return None
            return lock

        did_work = False
        for scene_name in sorted(statuses.keys()):
            status = statuses[scene_name]
            if not status.has_scene_raw or len(status.seq_dirs) == 0:
                continue

            need_step1 = not status.has_transforms
            need_step2 = status.has_transforms and (not status.has_mesh_raw)
            if not (need_step1 or need_step2):
                continue

            did_work = True
            lock = _acquire_scene_lock(scene_name)
            if lock is None:
                continue
            try:
                if need_step1:
                    step1_xlsx = xlsx_out.with_name(f"seq_info_step1__{scene_name}.xlsx")
                    write_filtered_xlsx(df, [scene_name], step1_xlsx)
                    step1_argv = [
                        "python",
                        "run_stages.py",
                        str(step1_xlsx),
                        "--data_root",
                        str(data_root),
                        "--config",
                        cfg_path,
                        "--steps",
                        "1",
                        "--mode",
                        args.mode,
                    ]
                    if args.force_all:
                        step1_argv.append("--force_all")
                    rc = run_conda(
                        args.conda,
                        args.env_step1,
                        step1_argv,
                        cwd=code_root,
                        log_path=_log_file(log_root, scene_name, cycle_id, "step1"),
                    )
                    if rc != 0:
                        log(f"[STEP1] {scene_name} returned rc={rc}")

                # Refresh after Step1: transforms.json may appear now.
                scene_dir = data_root / scene_name
                status = build_scene_status(scene_dir)
                if status.has_scene_raw and status.has_transforms and len(status.seq_dirs) > 0 and (not status.has_mesh_raw):
                    step2_xlsx = xlsx_out.with_name(f"seq_info_step2__{scene_name}.xlsx")
                    write_filtered_xlsx(df, [scene_name], step2_xlsx)
                    step2_argv = [
                        "python",
                        "run_stages.py",
                        str(step2_xlsx),
                        "--data_root",
                        str(data_root),
                        "--config",
                        cfg_path,
                        "--steps",
                        "2",
                        "--mode",
                        args.mode,
                    ]
                    if args.force_all:
                        step2_argv.append("--force_all")
                    rc = run_conda(
                        args.conda,
                        args.env_step2,
                        step2_argv,
                        cwd=code_root,
                        log_path=_log_file(log_root, scene_name, cycle_id, "step2"),
                    )
                    if rc != 0:
                        log(f"[STEP2] {scene_name} returned rc={rc}")
            finally:
                lock.release()

        if not did_work:
            log("[AUTO] Nothing to do")

        if args.run_once:
            return

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
