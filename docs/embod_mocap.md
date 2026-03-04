# EmbodMocap Main Pipeline (Entrypoint Renamable)

**Language / 语言切换:** [English](embod_mocap.md) | [中文](embod_mocap_zh.md)

The current unified entrypoint is `embod_mocap/run_stages.py`.  
If you rename the entry script in the open-source repo, update the command snippets in this doc accordingly.

## Quick Start

Run inside `embod_mocap/`:

```bash
cd embod_mocap

# 1) auto-generate xlsx
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 0

# 2) fill basic fields first (in_door / vertical / FAILED ...)

# 3) run scene + early preprocess first
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 1-5 --mode overwrite
```

Then manually inspect two views to determine synchronization, and fill `v1_start` / `v2_start` in xlsx.

```bash
# optional preview helper
python processor/visualize.py /path/to/scene/seq0 --input --processed --downscale 2 --mode overwrite

# 4) continue remaining pipeline after alignment is filled
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 6-16 --mode overwrite

# fast mode counterpart (same staged workflow)
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config_fast.yaml --steps 1-5 --mode overwrite
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config_fast.yaml --steps 6-16 --mode overwrite
```

## Standard vs Fast

Both modes run steps 1-16; the key difference is output completeness:
- `fast`: optimized for mesh + motion tasks and quicker iteration.
- `standard`: keeps/generates fuller RGBD + mask assets for data/model training.

Detailed stage+config explanation: [English](step_details.md) | [中文](step_details_zh.md).

## Step Overview (1-16)

### Stage 1: Scene Reconstruction (Steps 1-3)

1) `sai`: keyframes/cameras
2) `recon_scene`: scene mesh reconstruction (`mesh_raw.ply`, `mesh_simplified.ply`)
3) `rebuild_colmap`: scene COLMAP DB

### Stage 2: Sequence Preprocess (Steps 4-7)

4) `get_frames`: extract frames from raw
5) `smooth_camera`: camera smoothing
6) `slice_views`: split v1/v2 views (requires filled `v1_start`/`v2_start`)
7) `process_smpl`: estimate SMPL sequence

### Stage 3: Human-view Camera Calibration (Steps 8-12)

8) `colmap_human_cam`: human-view COLMAP cameras
9) `generate_keyframes`: keyframe generation
10) `process_depth_mask`: depth/mask generation/refinement
11) `vggt_track`: VGGT tracking cues
12) `align_cameras`: camera/scale alignment

### Stage 4: Motion & Contact (Steps 13-16)

13) `unproj_human`: human unprojection point cloud
14) `optim_human_cam`: optimize human-view cameras
15) `optim_motion`: world-space motion optimization (`optim_params.npz`)
16) `align_contact`: contact alignment (requires valid `contacts`)

## XLSX Fields (minimum)

- `scene_folder`, `seq_name`
- `in_door`, `vertical`
- `v1_start`, `v2_start`
- `FAILED`
- `contacts` (for step16 only)
- `skills` (used by dump/export planning)

### About `contacts` (Step 16)

Step 16 runs only when `contacts` is valid. Empty or `nan` contacts will be skipped.

## Cleaning

Supported: `--clean standard|fast|all` (+ requires `xlsx` and `data_root`).

```bash
# dry run first
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast --clean_dry_run

# execute clean
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast
```

Current semantics:
- `all`: keep only raw safety files
- `fast`: keep core outputs + lightweight visualization assets
- `standard`: keep everything in `fast` plus `images/depths_refined/masks`

## Visualization

```bash
# batch visualization from xlsx
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps vis --config config.yaml

# single-sequence visualization
python processor/visualize.py /path/to/scene/seq0 --input --optim_cam --downscale 2 --mode overwrite
```

## Completion Check

```bash
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 1-16 --check --config config.yaml
```
