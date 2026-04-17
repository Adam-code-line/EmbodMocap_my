import sys
import os
import shutil
import tempfile
import zipfile
import pandas as pd
import math
import argparse
import sqlite3
from embod_mocap.processor.base import run_cmd
from tqdm import tqdm
import yaml
from embod_mocap.config_paths import PATHS
from easydict import EasyDict


raw_files = ['calibration.json', 'data.jsonl', 'data.mov', 'frames2', 'metadata.json']


def get_colmap_db_counts(db_path: str):
    """
    Return (num_images, num_keypoints, num_descriptors) from a COLMAP sqlite db.
    Raises RuntimeError when the db cannot be opened or tables are missing.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            num_images = int(conn.execute("select count(*) from images").fetchone()[0])
            num_keypoints = int(conn.execute("select count(*) from keypoints").fetchone()[0])
            num_descriptors = int(conn.execute("select count(*) from descriptors").fetchone()[0])
        finally:
            conn.close()
        return num_images, num_keypoints, num_descriptors
    except Exception as exc:
        raise RuntimeError(f"Failed to read COLMAP database stats from {db_path}: {exc}") from exc


def get_colmap_db_image_names(db_path: str):
    """
    Return a set of image names stored in COLMAP database `images` table.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("select name from images").fetchall()
        finally:
            conn.close()
        return {str(r[0]) for r in rows}
    except Exception as exc:
        raise RuntimeError(f"Failed to read COLMAP database image names from {db_path}: {exc}") from exc


def read_non_empty_lines(txt_path: str):
    lines = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
    return lines


def read_colmap_images_txt_image_names(images_txt_path: str):
    """
    Parse COLMAP text model `images.txt` and return the unique image_name list.

    COLMAP format alternates:
      - image header line: IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME
      - points2D line
    """
    names = []
    seen = set()
    with open(images_txt_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                int(parts[0])
                int(parts[8])
            except Exception:
                continue
            name = str(parts[9])
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def get_bool_from_excel(row, column, default=False):
    """Read a boolean value from an Excel row with a default fallback.
    
    Args:
        row: pandas row object
        column: column name
        default: fallback value
    
    Returns:
        bool: TRUE/true/1.0 -> True; otherwise or empty -> False
    """
    value = row.get(column, default)
    if value is None or pd.isna(value):
        return default
    return str(value).upper() in ['TRUE', '1.0']


def get_start_frame_from_excel(row, column, default=-1):
    """Parse start frame index from Excel cells.

    Accepts integers, float-like values (e.g. 0.0), and strings.
    Returns default for empty/nan/'-' style placeholders.
    """
    value = row.get(column, default)
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()
    if text == '' or text == '-':
        return default

    try:
        parsed = int(float(text))
    except Exception as exc:
        raise ValueError(
            f"Invalid {column} value '{value}'. Please use integer frame index like 0, 15, 128."
        ) from exc

    return parsed


def get_process_flags(seq_path, anchor_files, mode):
    """Get processing flags for v1 and v2 based on mode and existing files"""
    proc_v1 = mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[0]))
    proc_v2 = mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[1]))
    return proc_v1, proc_v2


def is_non_empty_dir(path):
    """Return True only when path exists, is a directory, and has at least one non-hidden entry."""
    if not os.path.isdir(path):
        return False
    return any(not name.startswith('.') for name in os.listdir(path))


def count_non_hidden_files(path, suffix=None):
    if not os.path.isdir(path):
        return 0
    count = 0
    for name in os.listdir(path):
        if name.startswith('.'):
            continue
        if suffix is not None and not name.lower().endswith(suffix):
            continue
        count += 1
    return count

def check_slice_views_completion(seq_path, anchor_files, return_details=False):
    """Check if slice_views outputs exist (nested structure)"""
    issues = []

    # Structure is now: {'v1': [...], 'v2': [...]}
    for view_name, file_list in anchor_files.items():
        view_path = os.path.join(seq_path, view_name)

        # First check if view directory exists
        if not os.path.exists(view_path):
            if return_details:
                issues.append(f"{view_name} missing: {', '.join(file_list)}")
            else:
                return False
            continue

        for file_name in file_list:
            file_path = os.path.join(view_path, file_name)

            if file_name in ['images']:
                if not os.path.exists(file_path):
                    if return_details:
                        issues.append(f"{view_name}/{file_name} folder missing")
                    else:
                        return False
                elif os.path.isdir(file_path):
                    actual_count = len([f for f in os.listdir(file_path) if not f.startswith('.')])
                    if actual_count == 0:
                        if return_details:
                            issues.append(f"{view_name}/{file_name} is empty")
                        else:
                            return False
                else:
                    if return_details:
                        issues.append(f"{view_name}/{file_name} is not a directory")
                    else:
                        return False
            else:
                # For files, just check existence
                if not os.path.exists(file_path):
                    if return_details:
                        issues.append(f"{view_name}/{file_name} missing")
                    else:
                        return False

    if return_details:
        return len(issues) == 0, issues
    else:
        return len(issues) == 0

def _safe_extract_zip(zip_file, target_dir):
    """Extract zip members while preventing path traversal."""
    target_real = os.path.realpath(target_dir)
    for member in zip_file.infolist():
        member_name = member.filename
        if not member_name:
            continue
        member_path = os.path.normpath(member_name)
        destination = os.path.realpath(os.path.join(target_dir, member_path))
        if not (destination == target_real or destination.startswith(target_real + os.sep)):
            raise RuntimeError(f"Unsafe path in zip: {member_name}")
        zip_file.extract(member, target_dir)

def _missing_raw_inputs(raw_dir):
    return [name for name in raw_files if not os.path.exists(os.path.join(raw_dir, name))]

def _find_recording_payload_root(extract_root):
    """Find the directory that contains expected recording payload files."""
    candidates = []
    for current_root, _, _ in os.walk(extract_root):
        if not _missing_raw_inputs(current_root):
            candidates.append(current_root)

    if not candidates:
        return None

    # Prefer shallower candidate roots (zip root or first nested folder).
    candidates.sort(key=lambda p: len(os.path.relpath(p, extract_root).split(os.sep)))
    return candidates[0]

def extract_recording_zip_to_raw(zip_path, raw_dir):
    """Extract one recording_*.zip into raw1/raw2 style directory."""
    if os.path.exists(raw_dir):
        return

    parent_dir = os.path.dirname(raw_dir)
    temp_extract_root = tempfile.mkdtemp(prefix="recording_unzip_", dir=parent_dir)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            _safe_extract_zip(zip_file, temp_extract_root)

        payload_root = _find_recording_payload_root(temp_extract_root)
        if payload_root is None:
            raise RuntimeError(
                f"Zip payload missing required files {raw_files}: {zip_path}"
            )

        os.makedirs(raw_dir, exist_ok=False)
        for name in os.listdir(payload_root):
            src = os.path.join(payload_root, name)
            dst = os.path.join(raw_dir, name)
            shutil.move(src, dst)

        missing = _missing_raw_inputs(raw_dir)
        if missing:
            raise RuntimeError(
                f"After extracting {os.path.basename(zip_path)}, {raw_dir} is missing: {missing}"
            )
    finally:
        shutil.rmtree(temp_extract_root, ignore_errors=True)

def ensure_raw_input_ready(raw_dir):
    if not os.path.exists(raw_dir):
        raise FileNotFoundError(f"{raw_dir} not found")
    if not os.path.isdir(raw_dir):
        raise NotADirectoryError(f"{raw_dir} exists but is not a directory")

    missing = _missing_raw_inputs(raw_dir)
    if missing:
        raise FileNotFoundError(
            f"{raw_dir} missing required inputs: {missing}"
        )

def clean_raw_files(raw_path, dry_run=False, dry_run_deleted_paths=None):
    """Clean non-raw files from raw directory"""
    if os.path.exists(raw_path):
        for file_or_folder in os.listdir(raw_path):
            if file_or_folder not in raw_files:
                path = os.path.join(raw_path, file_or_folder)
                if dry_run:
                    print(f"[DRY-RUN] Would remove raw cache: {path}")
                    if dry_run_deleted_paths is not None:
                        dry_run_deleted_paths.append(path)
                else:
                    rm_file_or_folder(path)

def clean_cache_paths(base_path, paths):
    """Clean multiple cache paths if they exist"""
    for path in paths:
        full_path = os.path.join(base_path, path)
        if os.path.exists(full_path):
            rm_file_or_folder(full_path)

def build_command_with_flags(base_cmd, **flags):
    """Build command with conditional flags"""
    cmd = base_cmd
    for flag_name, value in flags.items():
        if isinstance(value, bool):
            if value:
                cmd += f" --{flag_name}"
        elif value is not None:
            cmd += f" --{flag_name} {value}"
    return cmd

def pick_profile_params(step_params, in_door):
    """Select in_door/out_door param block for a step."""
    return step_params.in_door if in_door else step_params.out_door

def check_steps_completion(xlsx_path, config, steps, data_root=None, force_all=False):
    """Check completion status of specified steps based on anchor files"""
    if not os.path.exists(xlsx_path):
        print(f"Error: {xlsx_path} not found")
        return
    
    # 读取 Excel 文件，支持多个 sheet
    xl = pd.ExcelFile(xlsx_path)
    if len(xl.sheet_names) > 1:
        print(f"Reading {len(xl.sheet_names)} sheets from {xlsx_path}")
        dfs = []
        for sheet_name in xl.sheet_names:
            df_sheet = pd.read_excel(xlsx_path, sheet_name=sheet_name)
            dfs.append(df_sheet)
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_excel(xlsx_path)
    
    results = {}
    config_step = {i + 1: step_cfg for i, step_cfg in enumerate(config.steps.values())}
    anchor_files = {i: cfg.anchors for i, cfg in config_step.items()}
    
    # Get unique scene folders and combine with data_root
    scene_folders = set()
    xlsx_failed_map = {}  # scene_folder_rel -> set(seq_name)
    scene_folder_map = {}  # 映射：完整路径 -> 相对路径
    for idx, row in df.iterrows():
        scene_folder_rel = str(row['scene_folder'])
        seq_name = str(row.get('seq_name', ''))
        if data_root:
            scene_folder = os.path.join(data_root, scene_folder_rel)
        else:
            scene_folder = scene_folder_rel
        scene_folders.add(scene_folder)
        scene_folder_map[scene_folder] = scene_folder_rel
        if seq_name and get_bool_from_excel(row, "FAILED"):
            if scene_folder_rel not in xlsx_failed_map:
                xlsx_failed_map[scene_folder_rel] = set()
            xlsx_failed_map[scene_folder_rel].add(seq_name)
    
    for step in steps:
        results[step] = {}
        
        if step == 1:
            # Step 1: sai - scene level
            for scene_folder in scene_folders:
                anchor_path = os.path.join(scene_folder, anchor_files[1][0])
                results[step][scene_folder] = os.path.exists(anchor_path)
                
        elif step == 2:
            # Step 2: recon_scene - scene level
            for scene_folder in scene_folders:
                anchor_path = os.path.join(scene_folder, anchor_files[2][0])
                results[step][scene_folder] = os.path.exists(anchor_path)
                
        elif step == 3:
            # Step 3: rebuild_colmap - scene level
            for scene_folder in scene_folders:
                anchor_path = os.path.join(scene_folder, anchor_files[3][0])
                results[step][scene_folder] = os.path.exists(anchor_path)
                
        elif step == 4:
            # Step 4: get_frames - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                seq_name = str(row['seq_name'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"  # 使用相对路径作为 key
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = is_non_empty_dir(os.path.join(seq_path, anchor_files[4][0]))
                v2_exists = is_non_empty_dir(os.path.join(seq_path, anchor_files[4][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 5:
            # Step 5: smooth_camera - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                seq_name = str(row['seq_name'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[5][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[5][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 6:
            # Step 6: slice_views - sequence level (nested structure)
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                seq_name = str(row['seq_name'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                is_complete, issues = check_slice_views_completion(seq_path, anchor_files[6], return_details=True)
                if is_complete:
                    results[step][seq_key] = True
                else:
                    results[step][seq_key] = issues
                
        elif step == 7:
            # Step 7: process_smpl - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[7][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[7][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 8:
            # Step 8: colmap_human_cam - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[8][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[8][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 9:
            # Step 9: generate_keyframes - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                anchor_path = os.path.join(seq_path, anchor_files[9][0])
                results[step][seq_key] = os.path.exists(anchor_path)

        elif step == 10:
            # Step 10: process_depth_mask - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue

                def _non_empty_dir(path):
                    if not os.path.isdir(path):
                        return False
                    return any(not f.startswith('.') for f in os.listdir(path))

                # Depth + mask outputs are both required for step 11 (vggt_track).
                # Keep compatibility with older configs that only listed depth anchors.
                depth_v1 = os.path.join(seq_path, "v1/depths_keyframe_refined")
                depth_v2 = os.path.join(seq_path, "v2/depths_keyframe_refined")
                mask_v1 = os.path.join(seq_path, "v1/masks_keyframe")
                mask_v2 = os.path.join(seq_path, "v2/masks_keyframe")
                results[step][seq_key] = (
                    _non_empty_dir(depth_v1)
                    and _non_empty_dir(depth_v2)
                    and _non_empty_dir(mask_v1)
                    and _non_empty_dir(mask_v2)
                )

        elif step == 11:
            # Step 11: vggt_track - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                anchor_path = os.path.join(seq_path, anchor_files[11][0])
                results[step][seq_key] = os.path.exists(anchor_path)
                
        elif step == 12:
            # Step 12: align_cameras - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[12][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[12][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 13:
            # Step 13: unproj_human - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[13][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[13][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 14:
            # Step 14: optim_human_cam - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                v1_exists = os.path.exists(os.path.join(seq_path, anchor_files[14][0]))
                v2_exists = os.path.exists(os.path.join(seq_path, anchor_files[14][1]))
                results[step][seq_key] = v1_exists and v2_exists
                
        elif step == 15:
            # Step 15: optim_motion - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                anchor_path = os.path.join(seq_path, anchor_files[15][0])
                results[step][seq_key] = os.path.exists(anchor_path)
                
        elif step == 16:
            # Step 16: align_contact - sequence level
            for idx, row in df.iterrows():
                scene_folder_rel = str(row['scene_folder'])
                if data_root:
                    scene_folder = os.path.join(data_root, scene_folder_rel)
                else:
                    scene_folder = scene_folder_rel
                seq_name = str(row['seq_name'])
                seq_path = os.path.join(scene_folder, seq_name)
                seq_key = f"{scene_folder_rel}/{seq_name}"
                
                if get_bool_from_excel(row, "FAILED") and not force_all:
                    results[step][seq_key] = "FAILED"
                    continue
                
                anchor_path = os.path.join(seq_path, anchor_files[16][0])
                results[step][seq_key] = os.path.exists(anchor_path)
        else:
            print(f"Warning: Unknown step {step}")
            continue
    
    # Reorganize results by scene
    scene_results = {}
    for step in steps:
        if step not in results:
            continue
        for path, status in results[step].items():
            if step in [1, 2, 3]:  # scene level
                scene_folder = path
                seq_name = None
            else:  # sequence level
                parts = path.split('/')
                scene_folder = '/'.join(parts[:-1])  # everything except last part
                seq_name = parts[-1]  # last part is seq_name
            
            if scene_folder not in scene_results:
                scene_results[scene_folder] = {}
            if seq_name not in scene_results[scene_folder]:
                scene_results[scene_folder][seq_name] = {}
            
            scene_results[scene_folder][seq_name][step] = status
    
    # Print results by scene
    print("\n=== Step Completion Check ===")
    total_scene_count = len(scene_results)
    total_seq_count = 0
    total_seq_success = 0
    total_seq_failed = 0
    total_seq_incomplete = 0
    total_xlsx_failed = 0
    total_xlsx_failed_success = 0

    for scene_folder in sorted(scene_results.keys()):
        # Check scene-level steps
        scene_unfinished = []
        scene_steps_to_check = [s for s in steps if s in [1, 2, 3]]
        
        if None in scene_results[scene_folder] and scene_steps_to_check:
            for step in sorted(scene_steps_to_check):
                if step in scene_results[scene_folder][None]:
                    if not scene_results[scene_folder][None][step]:
                        scene_unfinished.append(step)
        
        # Print scene status inline
        if scene_steps_to_check:
            if scene_unfinished:
                print(f"\nScene: {scene_folder} (unfinished: {','.join(map(str, scene_unfinished))})")
            else:
                print(f"\nScene: {scene_folder} (scene steps completed)")
        else:
            print(f"\nScene: {scene_folder}")
        
        # Check sequence-level steps
        seq_names = [k for k in scene_results[scene_folder].keys() if k is not None]
        if not seq_names:
            print("  No sequences found")
            continue
            
        # Sort sequences numerically (seq0, seq1, seq2, ..., seq10, seq11)
        def seq_sort_key(seq_name):
            if seq_name.startswith('seq'):
                try:
                    return int(seq_name[3:])
                except ValueError:
                    return float('inf')
            return seq_name
        
        # Check all sequences first to determine overall status
        incomplete_seqs = []
        failed_seqs = []
        completed_xlsx_failed = []
        
        for seq_name in sorted(seq_names, key=seq_sort_key):
            total_seq_count += 1
            seq_unfinished = []
            seq_failed = False
            seq_details = {}  # Store detailed issues for special steps
            xlsx_failed = seq_name in xlsx_failed_map.get(scene_folder, set())
            if xlsx_failed:
                total_xlsx_failed += 1
            
            for step in sorted([s for s in steps if s >= 4]):
                if step in scene_results[scene_folder][seq_name]:
                    status = scene_results[scene_folder][seq_name][step]
                    if status == "FAILED":
                        seq_failed = True
                        break
                    elif status is True:
                        # Step completed
                        continue
                    elif isinstance(status, list):
                        # Step 7 (slice_views) with detailed issues
                        seq_unfinished.append(step)
                        seq_details[step] = status
                    elif not status:
                        seq_unfinished.append(step)
            
            if seq_failed:
                failed_seqs.append((seq_name, xlsx_failed))
                total_seq_failed += 1
            elif seq_unfinished:
                incomplete_seqs.append((seq_name, seq_unfinished, seq_details, xlsx_failed))
                total_seq_incomplete += 1
            elif xlsx_failed:
                completed_xlsx_failed.append(seq_name)
                total_seq_success += 1
                total_xlsx_failed_success += 1
            else:
                total_seq_success += 1
        
        # Print results based on overall status
        if not failed_seqs and not incomplete_seqs:
            # All sequences completed
            seq_steps = [s for s in steps if s >= 4]
            if seq_steps:
                print("  All sequences completed")
                if completed_xlsx_failed:
                    checked_list = ",".join(sorted(completed_xlsx_failed, key=seq_sort_key))
                    print(f"  XLSX FAILED (checked): {checked_list}")
        else:
            for seq_name in sorted(completed_xlsx_failed, key=seq_sort_key):
                print(f"  {seq_name}: completed (xlsx FAILED)")
            # Print only failed and incomplete sequences
            for seq_name, xlsx_failed in failed_seqs:
                if xlsx_failed:
                    print(f"  {seq_name}: FAILED (xlsx marked)")
                else:
                    print(f"  {seq_name}: FAILED")
            for seq_name, unfinished_steps, details, xlsx_failed in incomplete_seqs:
                failed_tag = " (xlsx FAILED)" if xlsx_failed else ""
                if 7 in details and details[7]:
                    # Special handling for slice_views (step 7) with detailed issues
                    print(f"  {seq_name} unfinished steps: {','.join(map(str, unfinished_steps))}{failed_tag}")
                    for issue in details[7]:
                        print(f"    - {issue}")
                else:
                    print(f"  {seq_name} unfinished steps: {','.join(map(str, unfinished_steps))}{failed_tag}")

    print("\n=== Check Summary ===")
    print(f"Scenes total: {total_scene_count}")
    print(f"Seq total: {total_seq_count}")
    print(f"Seq success: {total_seq_success}")
    print(f"Seq failed: {total_seq_failed}")
    print(f"Seq unfinished: {total_seq_incomplete}")
    print(f"Seq xlsx FAILED marked: {total_xlsx_failed}")
    print(f"Seq xlsx FAILED but success: {total_xlsx_failed_success}")
    
    return results
def auto_generate_xlsx(data_root, out_xlsx='seq_info.xlsx'):
    # generate seq_info.xlsx, which contains scene_folder, seq_name, in_door, v1_start, v2_start
    
    if os.path.exists(out_xlsx):
        print(f"Error: {out_xlsx} already exists. Please remove it first or use a different name.")
        sys.exit(1)
    
    rows = []
    for scene in sorted(os.listdir(data_root)):
        if str(scene).startswith((".", "_")):
            continue
        scene_path = os.path.join(data_root, scene)
        if not os.path.isdir(scene_path):
            continue
        for seq in sorted(os.listdir(scene_path)):
            if not seq.startswith('seq'):
                continue
            seq_path = os.path.join(scene_path, seq)
            if not os.path.isdir(seq_path):
                continue
            rows.append({'scene_folder': scene, 'seq_name': seq, 'in_door': True, 'v1_start': '-', 'v2_start': '-', 'character': '-', 'skills': (), 'keyframes': (), 'FAILED': '',	'note': '', 'skills': (), 'contacts': (), 'optim_scale': False})
            # skills: list of list, [[start_frame, end_frame, skill_name], ...], e.g. [[0, 100, 'walk'], [100, 200, 'sit'], ...]
            # keyframes: list of list, [keyframe1, keyframe2]
    df = pd.DataFrame(rows)
    df.to_excel(out_xlsx, index=False)
    print(f"Auto-generated {out_xlsx} with {len(df)} rows.")

def rm_file_or_folder(path):
    if not os.path.exists(path):
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

def clean_data(data_root, xlsx_path=None, mode='all', dry_run=False):
    """
    Clean data based on mode. Only processes sequences listed in xlsx.
    
    Modes:
    - all: Keep only raw1/raw2 plus the 5 safe scene-level files
    - fast: Keep 'all' + scene mesh + core outputs (optim_params.npz, optim_params_aligned.npz, plan.json)
      + lightweight visualization files (v1/v2 cameras.ply, cameras_aligned.ply, seq kp3d.ply)
    - standard: Keep 'fast' + RGB + Depth + Mask (v1/v2 images, depths_refined, masks)
    
    CRITICAL: 
    - raw_files are never deleted: calibration.json, data.jsonl, data.mov, frames2, metadata.json
    - Only clean scene/seq pairs listed in xlsx
    """
    if not xlsx_path:
        print("ERROR: --clean requires --xlsx to determine which sequences to clean")
        sys.exit(1)
    
    dry_run_deleted_paths = [] if dry_run else None

    processed_seqs = {}  # {(scene, seq): row_data}
    if os.path.exists(xlsx_path):
        xl = pd.ExcelFile(xlsx_path)
        dfs = []
        for sheet_name in xl.sheet_names:
            df_sheet = pd.read_excel(xlsx_path, sheet_name=sheet_name)
            dfs.append(df_sheet)
        df = pd.concat(dfs, ignore_index=True)
        
        for _, row in df.iterrows():
            scene_folder = row['scene_folder']
            seq_name = row['seq_name']
            processed_seqs[(scene_folder, seq_name)] = row
        
        print(f"Found {len(processed_seqs)} sequences in {xlsx_path}")
    else:
        print(f"ERROR: xlsx file not found: {xlsx_path}")
        sys.exit(1)
    
    scenes_in_xlsx = sorted(set(scene for scene, seq in processed_seqs.keys()))
    matched_scene_count = 0
    
    for scene in scenes_in_xlsx:
        scene_path = os.path.join(data_root, scene)
        if not os.path.isdir(scene_path):
            print(f"Skip scene from xlsx (path not found): {scene_path}")
            continue
        matched_scene_count += 1
        
        action_tag = "[DRY-RUN] " if dry_run else ""
        print(f"{action_tag}Cleaning scene: {scene} (mode: {mode})")
        
        if mode == 'all':
            KEEP_SCENE = raw_files
        elif mode == 'fast':
            KEEP_SCENE = raw_files + ['mesh_raw.ply', 'mesh_simplified.ply', 'error.txt']
        elif mode == 'standard':
            KEEP_SCENE = raw_files + ['mesh_raw.ply', 'mesh_simplified.ply', 'error.txt']
        
        for item in os.listdir(scene_path):
            item_path = os.path.join(scene_path, item)
            
            if item.startswith('seq'):
                continue
            
            if item in KEEP_SCENE:
                continue
            
            if dry_run:
                print(f"  [DRY-RUN] Would remove scene file: {item_path}")
                dry_run_deleted_paths.append(item_path)
            else:
                print(f"  Removing scene file: {item}")
                rm_file_or_folder(item_path)

        seqs_in_scene = sorted(set(seq for scene_name, seq in processed_seqs.keys() if scene_name == scene))
        for seq in seqs_in_scene:
            seq_path = os.path.join(scene_path, seq)
            if not os.path.isdir(seq_path):
                print(f"  Skip seq from xlsx (path not found): {seq_path}")
                continue
            print(f"  {action_tag}Cleaning seq: {seq}")
            
            if mode == 'all':
                KEEP = ['raw1', 'raw2']
            elif mode == 'fast':
                KEEP = [
                    'raw1', 'raw2', 'v1', 'v2',
                    'optim_params.npz', 'optim_params_aligned.npz', 'plan.json',
                    'kp3d.ply', 'kp3d_aligned.ply'
                ]
            elif mode == 'standard':
                KEEP = [
                    'raw1', 'raw2', 'v1', 'v2',
                    'optim_params.npz', 'optim_params_aligned.npz', 'plan.json',
                    'kp3d.ply', 'kp3d_aligned.ply'
                ]
            
            for file_or_folder in os.listdir(seq_path):
                if file_or_folder not in KEEP:
                    path = os.path.join(seq_path, file_or_folder)
                    if dry_run:
                        print(f"    [DRY-RUN] Would remove: {path}")
                        dry_run_deleted_paths.append(path)
                    else:
                        print(f"    Removing: {file_or_folder}")
                        rm_file_or_folder(path)
            
            for raw_dir in ['raw1', 'raw2']:
                raw_path = os.path.join(seq_path, raw_dir)
                if os.path.exists(raw_path):
                    clean_raw_files(raw_path, dry_run=dry_run, dry_run_deleted_paths=dry_run_deleted_paths)
            
            if mode == 'standard':
                for v_dir in ['v1', 'v2']:
                    v_path = os.path.join(seq_path, v_dir)
                    if not os.path.exists(v_path):
                        continue
                    
                    KEEP_IN_V = ['images', 'depths_refined', 'masks', 'cameras.ply', 'cameras_aligned.ply']
                    
                    for item in os.listdir(v_path):
                        if item not in KEEP_IN_V:
                            item_path = os.path.join(v_path, item)
                            if dry_run:
                                print(f"    [DRY-RUN] Would remove {item_path}")
                                dry_run_deleted_paths.append(item_path)
                            else:
                                print(f"    Removing {v_dir}/{item}")
                                rm_file_or_folder(item_path)

            if mode == 'fast':
                for v_dir in ['v1', 'v2']:
                    v_path = os.path.join(seq_path, v_dir)
                    if not os.path.exists(v_path):
                        continue

                    KEEP_IN_V_FAST = ['cameras.ply', 'cameras_aligned.ply']

                    for item in os.listdir(v_path):
                        if item not in KEEP_IN_V_FAST:
                            item_path = os.path.join(v_path, item)
                            if dry_run:
                                print(f"    [DRY-RUN] Would remove {item_path}")
                                dry_run_deleted_paths.append(item_path)
                            else:
                                print(f"    Removing {v_dir}/{item}")
                                rm_file_or_folder(item_path)

    if dry_run:
        unique_paths = sorted(set(dry_run_deleted_paths))
        print("\n[DRY-RUN] ===== Theoretical Deletion List =====")
        if unique_paths:
            for p in unique_paths:
                print(f"[DRY-RUN] {p}")
        else:
            print("[DRY-RUN] No files/folders would be removed.")
        print(f"[DRY-RUN] Total paths that would be removed: {len(unique_paths)}")
    if matched_scene_count == 0:
        print(f"Warning: No valid scene paths matched under data_root={data_root}. Check xlsx scene_folder values.")

def full_steps(xlsx_path, data_root, config, steps):
    if 0 in steps:
        if not data_root:
            print('Please specify --data_root for auto-generating xlsx')
            sys.exit(1)
        auto_generate_xlsx(data_root, out_xlsx=xlsx_path)

    xl = pd.ExcelFile(xlsx_path)
    if len(xl.sheet_names) > 1:
        print(f"Found {len(xl.sheet_names)} sheets in {xlsx_path}: {xl.sheet_names}")
        dfs = []
        for sheet_name in xl.sheet_names:
            df_sheet = pd.read_excel(xlsx_path, sheet_name=sheet_name)
            print(f"  Sheet '{sheet_name}': {len(df_sheet)} rows")
            dfs.append(df_sheet)
        df = pd.concat(dfs, ignore_index=True)
        print(f"Total rows: {len(df)}")
    else:
        df = pd.read_excel(xlsx_path)
        print(f"Single sheet: {len(df)} rows")
    
    scene_folders = set()
    in_door_flags = dict()

    for idx, row in df.iterrows():
        scene_folder_rel = str(row['scene_folder'])
        if data_root:
            scene_folder = os.path.join(data_root, scene_folder_rel)
        else:
            scene_folder = scene_folder_rel
        scene_folders.add(scene_folder)
        in_door_flags[scene_folder] = get_bool_from_excel(row, 'in_door', False)

    config_step = {i + 1: step_cfg for i, step_cfg in enumerate(config.steps.values())}
    anchor_files = {i: cfg.anchors for i, cfg in config_step.items()}

    # S1: step1, step2, step3, build scene
    # S2: step4, step5, step6, step7, preprocess each sequence
    # S3: step8, step9, step10, step11, step12, calibrate and optimize human view cameras
    # S4: step13, optimize motion
    for scene_folder in tqdm(scene_folders,):
        recon_params = pick_profile_params(config_step[2], in_door_flags[scene_folder])
        sai_params = pick_profile_params(config_step[1], in_door_flags[scene_folder])
        depth_trunc = recon_params.depth_trunc
        voxel_size = recon_params.voxel_size
        sdf_trunc = recon_params.sdf_trunc
        key_frame_dist = sai_params.key_frame_dist
        vggt_refine = recon_params.vggt_refine
        ################# reconstruct scene #################
        ################ step 1: run SAI to get the scene #################
        if 1 in steps:
            if args.mode == 'overwrite' or not os.path.exists(os.path.join(scene_folder, anchor_files[1][0])):
                print(f"\n==== Step 1, Processing scene for {scene_folder} ====")
                run_cmd(f"source processor/sai.sh {scene_folder} {key_frame_dist}")
            else:
                print(f"Skip SAI for {scene_folder}")

        ################ step 2: reconstruct scene with volume #################
        if 2 in steps:
            if args.mode == 'overwrite' or not os.path.exists(os.path.join(scene_folder, anchor_files[2][0])):
                print(f"\n==== Step 2, Reconstruct scene for {scene_folder} ====")
                cmd = build_command_with_flags(
                    f"python processor/unproj_scene.py {scene_folder}",
                    depth_trunc=depth_trunc,
                    voxel_size=voxel_size,
                    sdf_trunc=sdf_trunc,
                    correct_convention=True,
                    depth_refine=True,
                    vggt_refine=vggt_refine,
                )
                run_cmd(cmd)
            else:
                print(f"Skip reconstruction for {scene_folder}")

        ################ step 3: rebuild colmap for the scene #################
        if 3 in steps:
            db_path = os.path.join(scene_folder, 'colmap', 'database.db')
            if args.mode == 'overwrite' or not os.path.exists(os.path.join(scene_folder, anchor_files[3][0])):
                print(f"\n==== Step 3, Rebuilding colmap for {scene_folder} ====")
                run_cmd(f"source processor/rebuild_colmap.sh {scene_folder}")
                if not os.path.exists(db_path):
                    raise RuntimeError(
                        f"Step 3 failed: {db_path} was not generated. "
                        "Please check rebuild_colmap.sh logs above (common causes: sparse model image names do not match scene/images, or COLMAP command failure)."
                    )
            else:
                print(f"Skip rebuilding colmap for {scene_folder}")

            num_images, num_keypoints, num_descriptors = get_colmap_db_counts(db_path)
            if num_images == 0 or num_keypoints == 0 or num_descriptors == 0:
                raise RuntimeError(
                    f"Step 3 failed: {db_path} looks empty "
                    f"(images={num_images}, keypoints={num_keypoints}, descriptors={num_descriptors}). "
                    "Please check rebuild_colmap.sh logs above, verify scene/images is populated, "
                    "then rerun Step 3 with --mode overwrite."
                )

            # Validate db names match the scene sparse model.
            expected_names = []
            image_list_path = os.path.join(scene_folder, "colmap", "image-list.txt")
            sparse_images_txt = os.path.join(scene_folder, "colmap", "sparse", "0", "images.txt")
            if os.path.exists(image_list_path):
                expected_names = read_non_empty_lines(image_list_path)
            elif os.path.exists(sparse_images_txt):
                expected_names = read_colmap_images_txt_image_names(sparse_images_txt)

            if expected_names:
                db_names = get_colmap_db_image_names(db_path)
                missing = [n for n in expected_names if n not in db_names]
                if missing:
                    sample = missing[:8]
                    raise RuntimeError(
                        "Step 3 failed: scene COLMAP database is incomplete (sparse model/database mismatch). "
                        f"Missing {len(missing)}/{len(expected_names)} sparse images in database images table. "
                        f"Example missing: {sample}. "
                        "This usually means rebuild_colmap.sh (colmap feature_extractor/matcher) failed early or was interrupted, "
                        "or Step 3/Step 8 ran concurrently and Step 8 copied a half-built database. "
                        "Please inspect Step 3 logs (search for feature_extractor/exhaustive_matcher errors), "
                        "ensure scene automation is locked/serialized, then rerun Step 3 with --mode overwrite."
                    )
                if num_keypoints < len(expected_names) or num_descriptors < len(expected_names):
                    raise RuntimeError(
                        "Step 3 failed: scene COLMAP database has too few extracted features. "
                        f"sparse_images={len(expected_names)}, images={num_images}, keypoints_rows={num_keypoints}, descriptors_rows={num_descriptors}. "
                        "Please inspect rebuild_colmap.sh logs above and rerun Step 3 with --mode overwrite."
                    )

            clean_cache_paths(scene_folder, [
                'colmap/dense/stereo/depth_maps',
                'colmap/dense/stereo/normal_maps'
            ])

    for idx, row in tqdm(df.iterrows()):
        scene_folder_rel = str(row['scene_folder'])
        seq_name = str(row['seq_name'])
        
        if data_root:
            scene_folder = os.path.join(data_root, scene_folder_rel)
        else:
            scene_folder = scene_folder_rel

        if get_bool_from_excel(row, "FAILED") and not args.force_all:
            print(f"Skip {scene_folder} {seq_name}, because it is marked as failed")
            continue

        seq_path = os.path.join(scene_folder, seq_name)
        vertical = True
        optim_scale = get_bool_from_excel(row, 'optim_scale', False)

        try:
            ################ step 4: preprocess frames from each sequence in raw1 and raw2 #################
            if 4 in steps:
                print(f"\n==== Step 4, Get frames from videos for {scene_folder} {seq_name}")

                raw1_path = os.path.join(scene_folder, seq_name, 'raw1')
                raw2_path = os.path.join(scene_folder, seq_name, 'raw2')

                # Guard against a common data-shape issue where raw1/raw2 are files
                # (often renamed zip archives) instead of directories.
                if os.path.exists(raw1_path) and not os.path.isdir(raw1_path):
                    raise NotADirectoryError(
                        f"{raw1_path} exists but is not a directory. "
                        "Please extract recording zip into raw1/ first."
                    )
                if os.path.exists(raw2_path) and not os.path.isdir(raw2_path):
                    raise NotADirectoryError(
                        f"{raw2_path} exists but is not a directory. "
                        "Please extract recording zip into raw2/ first."
                    )

                seq_dir = os.path.join(scene_folder, seq_name)
                missing_targets = []
                if not os.path.exists(raw1_path):
                    missing_targets.append(("raw1", raw1_path))
                if not os.path.exists(raw2_path):
                    missing_targets.append(("raw2", raw2_path))

                if missing_targets:
                    exist_items = sorted(os.listdir(seq_dir))
                    recording_dirs = [
                        name for name in exist_items
                        if name.startswith('recording_') and os.path.isdir(os.path.join(seq_dir, name))
                    ]
                    recording_zips = [
                        name for name in exist_items
                        if name.startswith('recording_') and name.lower().endswith('.zip') and os.path.isfile(os.path.join(seq_dir, name))
                    ]

                    selected_sources = []
                    need_count = len(missing_targets)

                    for source_name in recording_dirs:
                        selected_sources.append(("dir", source_name))
                        if len(selected_sources) >= need_count:
                            break

                    if len(selected_sources) < need_count:
                        if args.auto_extract_zip:
                            for source_name in recording_zips:
                                selected_sources.append(("zip", source_name))
                                if len(selected_sources) >= need_count:
                                    break
                        elif recording_zips:
                            raise RuntimeError(
                                f"Found zip inputs in {seq_dir}: {recording_zips}. "
                                "Zip auto-extraction is disabled (--no_auto_extract_zip). "
                                "Please extract them into raw1/ and raw2/ before Step 4."
                            )

                    if len(selected_sources) < need_count:
                        raise RuntimeError(
                            f"Cannot infer raw inputs in {seq_dir}. "
                            f"Need {need_count} source(s), but found dirs={recording_dirs}, zips={recording_zips}."
                        )

                    for (target_name, target_path), (source_kind, source_name) in zip(missing_targets, selected_sources):
                        source_path = os.path.join(seq_dir, source_name)
                        if source_kind == "dir":
                            print(f"[Step4] Using directory {source_name} -> {target_name}/")
                            os.rename(source_path, target_path)
                        else:
                            print(f"[Step4] Auto-extracting {source_name} -> {target_name}/")
                            extract_recording_zip_to_raw(source_path, target_path)

                ensure_raw_input_ready(raw1_path)
                ensure_raw_input_ready(raw2_path)
                
                vertical_flag = 1 if vertical else 0
                raw1_frames_dir = os.path.join(seq_path, anchor_files[4][0])
                raw2_frames_dir = os.path.join(seq_path, anchor_files[4][1])

                if args.mode == 'overwrite' or not is_non_empty_dir(raw1_frames_dir):
                    run_cmd(f"source processor/get_frames.sh {seq_path} raw1 {config_step[4].down_scale} {vertical_flag}")
                else:
                    print(f"Skip getting raw1 frames for {scene_folder} {seq_name}")

                if args.mode == 'overwrite' or not is_non_empty_dir(raw2_frames_dir):
                    run_cmd(f"source processor/get_frames.sh {seq_path} raw2 {config_step[4].down_scale} {vertical_flag}")
                else:
                    print(f"Skip getting raw2 frames for {scene_folder} {seq_name}")

            ################ step 5: smooth camera with spectacular AI #################
            if 5 in steps:
                print(f"\n==== Step 5, Smoothing camera for {scene_folder} {seq_name} ====")
                proc_v1, proc_v2 = get_process_flags(seq_path, anchor_files[5], args.mode)
                if proc_v1 or proc_v2:
                    smooth_fallback_kfd = getattr(config_step[5], "fallback_key_frame_distance", None)
                    smooth_min_frames = getattr(config_step[5], "min_fallback_frames", None)
                    smooth_try_mono = getattr(config_step[5], "fallback_try_mono", None)
                    # cmd = f"python processor/smooth_camera.py {seq_path} --proc_v1 {proc_v1} --proc_v2 {proc_v2} --log_file {args.log_file}"
                    cmd = build_command_with_flags(
                        f"python processor/smooth_camera.py {seq_path}",
                        proc_v1=proc_v1,
                        proc_v2=proc_v2,
                        log_file=args.log_file,
                        fallback_key_frame_distance=smooth_fallback_kfd,
                        min_fallback_frames=smooth_min_frames,
                        fallback_try_mono=smooth_try_mono,
                    )
                    run_cmd(cmd)
                else:
                    print(f"Skip smoothing camera for {scene_folder} {seq_name}")

            # need to watch the two views to check the start frame ids of the two views, update the xlsx file
            ################ step 6: slice views #################
            if 6 in steps:
                print(f"\n==== Step 6, Slicing views for {scene_folder} {seq_name} ====")
                v1_start = get_start_frame_from_excel(row, 'v1_start', default=-1)
                v2_start = get_start_frame_from_excel(row, 'v2_start', default=-1)
                if v1_start == -1 or v2_start == -1:
                    print(f"v1_start or v2_start is not set for {scene_folder} {seq_name}, skipping")
                    continue

                # For slice_views, run if any file is missing (fast operation)
                slice_completed = args.mode != 'overwrite' and check_slice_views_completion(seq_path, anchor_files[6])
                if not slice_completed:
                    cmd = build_command_with_flags(
                        f"python processor/slice_views.py {seq_path}",
                        v1_start=str(v1_start),
                        v2_start=str(v2_start),
                        vertical=vertical,
                        jpeg_quality=config_step[6].jpeg_quality,
                    )
                    run_cmd(cmd)

                    # Validate outputs immediately so failures are surfaced at Step 6
                    # instead of being deferred to Step 8.
                    is_complete, issues = check_slice_views_completion(
                        seq_path,
                        anchor_files[6],
                        return_details=True,
                    )
                    if not is_complete:
                        raise RuntimeError(
                            f"Step 6 outputs incomplete for {seq_path}: {issues}. "
                            "Likely causes: Step 4 raw images missing/empty, invalid v1_start/v2_start, "
                            "or Step 5 camera frame_ids are duplicated/non-increasing. "
                            "Please rerun --steps 4,6 with --mode overwrite and verify raw1/images + raw2/images are non-empty."
                        )

                else:
                    print(f"Skip slicing views for {scene_folder} {seq_name}")

            ################ step 7: process SMPL params only #################
            if 7 in steps:
                print(f"\n==== Step 7, Processing SMPL params for {scene_folder} {seq_name} ====")
                cmd = build_command_with_flags(
                    f"python processor/process_smpl.py {seq_path}",
                    device=args.device,
                    mode=args.mode,
                )
                run_cmd(cmd)
            ######## from now, the raw1 and raw2 are no more needed, we can clean the cache data ########

            ################ step 8: calibrate human view cameras #################
            if 8 in steps:
                print(f"\n==== Step 8, use colmap to calibrate human view cameras for {scene_folder} {seq_name} ====")
                db_path = os.path.join(scene_folder, 'colmap', 'database.db')
                assert os.path.exists(db_path), f"colmap database not found in {scene_folder}/colmap, please run step 2 first, check the LD_LIBRARY_PATH problem in QAs.md !!!"
                num_images, num_keypoints, num_descriptors = get_colmap_db_counts(db_path)
                if num_images == 0 or num_keypoints == 0 or num_descriptors == 0:
                    raise RuntimeError(
                        f"Step 8 input invalid: scene COLMAP database is empty: {db_path} "
                        f"(images={num_images}, keypoints={num_keypoints}, descriptors={num_descriptors}). "
                        "This usually means Step 3 rebuild_colmap failed silently or was skipped after scene/images changed. "
                        "Please rerun scene-level Step 3 with --mode overwrite, then rerun Step 8."
                    )

                # Guard against a common Step3 partial-build state:
                # sparse model has many images, but database contains only a few (or only v1/v2 images after Step8 feature_extractor).
                expected_names = []
                image_list_path = os.path.join(scene_folder, "colmap", "image-list.txt")
                sparse_images_txt = os.path.join(scene_folder, "colmap", "sparse", "0", "images.txt")
                if os.path.exists(image_list_path):
                    expected_names = read_non_empty_lines(image_list_path)
                elif os.path.exists(sparse_images_txt):
                    expected_names = read_colmap_images_txt_image_names(sparse_images_txt)
                if expected_names:
                    db_names = get_colmap_db_image_names(db_path)
                    missing = [n for n in expected_names if n not in db_names]
                    if missing:
                        sample = missing[:8]
                        raise RuntimeError(
                            "Step 8 input invalid: scene COLMAP sparse model/database mismatch. "
                            f"Scene db images table is missing {len(missing)}/{len(expected_names)} sparse images. "
                            f"Example missing: {sample}. "
                            "Please rerun scene-level Step 3 with --mode overwrite (and stop concurrent scene jobs), "
                            "then rerun Step 8."
                        )

                proc_v1, proc_v2 = get_process_flags(seq_path, anchor_files[8], args.mode)
                min_step8_frames = 3
                if proc_v1:
                    v1_images_dir = os.path.join(seq_path, "v1", "images")
                    v1_frame_count = count_non_hidden_files(v1_images_dir, suffix='.jpg')
                    if v1_frame_count < min_step8_frames:
                        raise FileNotFoundError(
                            f"Step 8 input invalid: {v1_images_dir} has {v1_frame_count} jpg frames (< {min_step8_frames}). "
                            "Step 8 depends on Step 6 (slice_views) outputs with enough overlap. "
                            "Please rerun Step 5/6 (try smaller smooth fallback key_frame_distance, e.g. 0.03-0.05) "
                            "and verify v1_start/v2_start so v1/images and v2/images are long enough."
                        )

                if proc_v2:
                    v2_images_dir = os.path.join(seq_path, "v2", "images")
                    v2_frame_count = count_non_hidden_files(v2_images_dir, suffix='.jpg')
                    if v2_frame_count < min_step8_frames:
                        raise FileNotFoundError(
                            f"Step 8 input invalid: {v2_images_dir} has {v2_frame_count} jpg frames (< {min_step8_frames}). "
                            "Step 8 depends on Step 6 (slice_views) outputs with enough overlap. "
                            "Please rerun Step 5/6 (try smaller smooth fallback key_frame_distance, e.g. 0.03-0.05) "
                            "and verify v1_start/v2_start so v1/images and v2/images are long enough."
                        )

                if proc_v1 or proc_v2:
                    cmd = build_command_with_flags(
                        f"python processor/colmap_human_cam.py {seq_path}",
                        colmap_num=config_step[8].colmap_num,
                        min_valid_ratio=config_step[8].min_valid_ratio,
                        proc_v1=proc_v1,
                        proc_v2=proc_v2,
                        log_file=args.log_file,
                        vertical=vertical,
                        keyframe_mask=True,
                    )
                    run_cmd(cmd)

                    missing_step8_outputs = []
                    if proc_v1 and not os.path.exists(os.path.join(seq_path, anchor_files[8][0])):
                        missing_step8_outputs.append(anchor_files[8][0])
                    if proc_v2 and not os.path.exists(os.path.join(seq_path, anchor_files[8][1])):
                        missing_step8_outputs.append(anchor_files[8][1])

                    if missing_step8_outputs:
                        raise RuntimeError(
                            f"Step 8 failed for {seq_path}; missing outputs: {missing_step8_outputs}. "
                            "Common causes: scene colmap model/database mismatch, too few sliced frames, "
                            "or COLMAP image_registrator failure in processor/regist_seq.sh. "
                            "Please inspect Step 8 logs above, rerun scene-level Step 1 and Step 3 with --mode overwrite, "
                            "then rerun Step 5-8."
                        )
                else:
                    print(f"Skip colmap register human cam for {scene_folder} {seq_name}")

            ################ step 9: generate keyframes from colmap tracks #################
            if 9 in steps:
                print(f"\n==== Step 9, Generate keyframes for {scene_folder} {seq_name} ====")
                if args.mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[9][0])):
                    cmd = build_command_with_flags(
                        f"python processor/generate_keyframes.py {seq_path}",
                        min_tracks=config_step[9].min_tracks,
                        num_keyframes=config_step[9].num_keyframes,
                        min_keyframes=config_step[9].min_keyframes,
                    )
                    run_cmd(cmd)
                else:
                    print(f"Skip generate keyframes for {scene_folder} {seq_name}")

            ################ step 10: depth refine + mask + filter points2D #################
            if 10 in steps:
                print(f"\n==== Step 10, Process depth & mask for {scene_folder} {seq_name} ====")
                lang_sam_cfg = config_step[10].lang_sam
                lang_sam_sam_type = lang_sam_cfg.sam_type or PATHS.lang_sam_sam_type
                lang_sam_sam_ckpt = lang_sam_cfg.sam_ckpt_path or PATHS.lang_sam_sam_ckpt
                gdino_model_ckpt = lang_sam_cfg.get('gdino_model_ckpt_path') or PATHS.get('gdino_model_ckpt')
                gdino_processor_ckpt = lang_sam_cfg.get('gdino_processor_ckpt_path') or PATHS.get('gdino_processor_ckpt')
                use_vggt = config_step[14].vggt_track
                use_unproj = config_step[14].get('chamfer', False)
                use_p2p = config_step[14].get('p2p', False)
                cmd = build_command_with_flags(
                    f"python processor/process_depth_mask.py {seq_path}",
                    device=args.device,
                    need_all_depth_mask=config_step[10].get('need_all_depth_mask', False),
                    depth_refine_chunk_size=config_step[10].depth_refine_chunk_size,
                    depth_refine_max_size=config_step[10].depth_refine_max_size,
                    lang_sam_chunk_size=config_step[10].lang_sam_chunk_size,
                    lang_sam_sam_type=lang_sam_sam_type,
                    lang_sam_sam_ckpt_path=lang_sam_sam_ckpt,
                    gdino_model_ckpt_path=gdino_model_ckpt,
                    gdino_processor_ckpt_path=gdino_processor_ckpt,
                    use_vggt=use_vggt,
                    use_unproj=use_unproj,
                    use_p2p=use_p2p,
                    mode=args.mode,
                )
                run_cmd(cmd)

            ################ step 11: use vggt to track human view cameras #################
            if 11 in steps:
                if config_step[14].vggt_track:
                    if args.mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[11][0])):
                        print(f"\n==== Step 11, use vggt to track human view cameras for {scene_folder} {seq_name} ====")
                        cmd = build_command_with_flags(
                            f"python processor/vggt_track.py {seq_path}",
                            device=args.device,
                            log_file=args.log_file,
                            vggt_track_samples=config_step[11].vggt_track_samples,
                            use_keyframe_depths=True,
                            use_keyframe_masks=True,
                        )
                        run_cmd(cmd)
                else:
                    print(f"Skip vggt_track for {scene_folder} {seq_name}")

            ################ step 12: align SAI cameras to COLMAP scale #################
            if 12 in steps:
                print(f"\n==== Step 12, Align SAI cameras to COLMAP scale for {scene_folder} {seq_name} ====")
                if args.mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[12][0])) or not os.path.exists(os.path.join(seq_path, anchor_files[12][1])):
                    cmd = build_command_with_flags(
                        f"python processor/align_cameras.py {seq_path}",
                        z_rot_only=config_step[14].z_rot_only,
                        fix_scale=not optim_scale
                    )
                    run_cmd(cmd)
                else:
                    print(f"Skip align cameras for {scene_folder} {seq_name}")

            ################ step 13: unproject scene for human views #################
            if 13 in steps:
                print(f"\n==== Step 13, unproject scene for human views for {scene_folder} {seq_name} ====")
                if config_step[14].chamfer:
                    unproj_params = pick_profile_params(config_step[13], in_door_flags[scene_folder])
                    depth_trunc = unproj_params.depth_trunc
                    stride = unproj_params.stride
                    proc_v1, proc_v2 = get_process_flags(seq_path, anchor_files[13], args.mode)
                    if proc_v1 or proc_v2:
                        cmd = build_command_with_flags(
                            f"python processor/unproj_human.py {seq_path}",
                            device=args.device,
                            depth_trunc=depth_trunc,
                            stride=stride,
                            proc_v1=proc_v1,
                            proc_v2=proc_v2,
                            use_keyframe_depths=True,
                            use_keyframe_masks=True,
                        )
                        run_cmd(cmd)
                    else:
                        print(f"Skip unproj human for {scene_folder} {seq_name}")
                else:
                    print(f"Skip unproj human for {scene_folder} {seq_name}")
            
            ################ step 14: optimize and calibrate human view cameras to the scene #################
            if 14 in steps:
                if args.mode == 'overwrite' or not os.path.exists(os.path.join(seq_path, anchor_files[14][0])) or not os.path.exists(os.path.join(seq_path, anchor_files[14][1])):
                    print(f"\n==== Step 14, optimize human view cameras for {scene_folder} {seq_name} ====")
                    cmd = build_command_with_flags(
                        f"python processor/optim_human_cam.py {seq_path}",
                        device=args.device,
                        chamfer=config_step[14].chamfer,
                        dba=config_step[14].dba,
                        p2p=config_step[14].p2p,
                        vggt_track=config_step[14].vggt_track,
                        z_rot_only=config_step[14].z_rot_only,
                        use_keyframe_depths=True,
                        use_keyframe_masks=True,
                    )
                    run_cmd(cmd)
                else:
                    print(f"Skip optimize human view cameras")

            ################ step 15: optimize world space smpl motion #################
            if 15 in steps:
                print(f"\n==== Step 15, optimize world space motion for {scene_folder} {seq_name} ====")

                optim_anchors = anchor_files[15]
                optim_missing = not os.path.exists(os.path.join(seq_path, optim_anchors[0]))
                if len(optim_anchors) > 1:
                    optim_missing = optim_missing or not os.path.exists(os.path.join(seq_path, optim_anchors[1]))
                if args.mode == 'overwrite' or optim_missing:
                    cmd = build_command_with_flags(
                        f"python processor/optim_motion.py {seq_path}",
                        device=args.device,
                        gender="neutral",
                        post_smooth=config_step[15].post_smooth,
                        optim_kp3d=config_step[15].optim_kp3d,
                        pcscale=config_step[15].pcscale,
                        reproj=config_step[15].reproj,
                        smooth=config_step[15].smooth,
                        use_kp3d=config_step[15].use_kp3d,
                        use_prior=config_step[15].use_prior
                    )
                    run_cmd(cmd)
                else:
                    print(f"Skip step 15, {seq_path}/optim_params.npz already exists")
                
            ################ step 16: contact-based alignment optimization #################
            if 16 in steps:
                print(f"\n==== Step 16, contact-based alignment for {scene_folder} {seq_name} ====")
                align_anchors = anchor_files[16]
                align_missing = not os.path.exists(os.path.join(seq_path, align_anchors[0]))
                if len(align_anchors) > 1:
                    align_missing = align_missing or not os.path.exists(os.path.join(seq_path, align_anchors[1]))
                if args.mode == 'overwrite' or align_missing:
                    contacts_str = str(row.get('contacts', ''))
                    if contacts_str == '' or contacts_str == 'nan':
                        print(f"No contacts found for {scene_folder} {seq_name}, skipping alignment")
                        continue
                    
                    cmd = f"python processor/align_contact.py {seq_path} --xlsx_path {args.xlsx} --device {args.device} --loss_threshold {config_step[16].loss_threshold}"
                    if args.log_file:
                        cmd += f" --log_file {args.log_file}"
                    run_cmd(cmd)

                else:
                    print(f"Skip step 16, contact alignment already done for {seq_path}")

        except Exception as e:
            print(f"Error processing {scene_folder}: {e}")
            with open(os.path.join(scene_folder, 'error.txt'), 'a') as f:
                f.write(f"{scene_folder} {seq_name} {e}\n")
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('xlsx', nargs='?', default=None, help='')
    parser.add_argument('--config', type=str, default='config_fast.yaml', help='config file')
    parser.add_argument('--steps', type=str, default='0')
    parser.add_argument('--data_root', type=str, default=None, help='')
    parser.add_argument('--clean', type=str, 
                        choices=['standard', 'fast', 'all'], 
                        help='Clean mode: '
                             'standard (keep full RGBD dataset), '
                             'fast (keep only motion+scene), '
                             'all (remove all results, keep only raw files)')
    parser.add_argument('--device', type=str, default='cuda', help='device')
    parser.add_argument('--mode', type=str, default='skip', choices=['overwrite', 'skip'], help='overwrite or skip the existing sequences')
    parser.add_argument('--log_file', type=str, default=None, help='log file')
    parser.add_argument('--check', action='store_true', help='check completion status of specified steps')
    parser.add_argument('--clean_dry_run', action='store_true', help='preview clean actions without deleting files')
    parser.add_argument('--force_all', action='store_true', help='Force process all sequences including those marked as FAILED')
    parser.add_argument('--auto_extract_zip', dest='auto_extract_zip', action='store_true',
                        help='Automatically extract recording_*.zip into raw1/raw2 when needed (default: enabled)')
    parser.add_argument('--no_auto_extract_zip', dest='auto_extract_zip', action='store_false',
                        help='Disable auto extraction of recording_*.zip and require prepared raw1/raw2')
    parser.set_defaults(auto_extract_zip=True)
    # Help short-circuit: always show help and exit, regardless of other args.
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    
    if args.clean:
        if not args.data_root:
            print('Please specify --data_root for cleaning')
            sys.exit(1)
        if not args.xlsx:
            print('Please specify --xlsx for cleaning (only listed scene/seq will be cleaned)')
            sys.exit(1)
        if args.clean_dry_run:
            print('[DRY-RUN] Clean preview mode enabled. No files will be deleted.')
        
        if args.clean == 'standard':
            clean_data(args.data_root, xlsx_path=args.xlsx, mode='standard', dry_run=args.clean_dry_run)
        elif args.clean == 'fast':
            clean_data(args.data_root, xlsx_path=args.xlsx, mode='fast', dry_run=args.clean_dry_run)
        elif args.clean == 'all':
            clean_data(args.data_root, xlsx_path=args.xlsx, mode='all', dry_run=args.clean_dry_run)
        sys.exit(0)
    
    if args.log_file and not os.path.exists(args.log_file):
        with open(args.log_file, 'w') as f:
            f.write('')

    if args.xlsx is None or str(args.xlsx).strip() == "":
        parser.print_help()
        print("\n[ERROR] Missing required positional argument: xlsx (path to seq_info_*.xlsx).")
        print("[HINT] If you used an env var like $XLSX_ONE, make sure it is exported in the current shell:")
        print("       echo \"$XLSX_ONE\"; ls -lah \"$XLSX_ONE\"")
        sys.exit(1)
    if not os.path.exists(args.xlsx):
        raise FileNotFoundError(
            f"xlsx not found: {args.xlsx}. "
            "If you used an env var like $XLSX_ONE, make sure it is set and points to an existing file."
        )
    arg_steps = args.steps.split(',')
    steps = []
    for s in arg_steps:
        if s.isdigit():
            steps.append(int(s))
        elif '-' in s:
            start, end = s.split('-')
            steps.extend(range(int(start), int(end) + 1))
        else:
            raise ValueError(f"Invalid stage: {s}")
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    config = EasyDict(config)
    
    if args.check:
        check_steps_completion(args.xlsx, config, steps, data_root=args.data_root, force_all=args.force_all)
    else:
        full_steps(args.xlsx, args.data_root, config=config, steps=steps)
