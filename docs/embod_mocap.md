# EmbodMocap Main Pipeline

**Language / 语言切换:** [English](embod_mocap.md) | [中文](embod_mocap_zh.md)

The unified entrypoint is `embod_mocap/run_stages.py`.

## Quick Start

### Demo with Sample Data

We provide a demo dataset to help you get started quickly. Download it from our data release and try:

```bash
cd embod_mocap

# Run the demo with provided sample data
python run_stages.py ../datasets/release_demo.xlsx --data_root ../datasets/dataset_demo --config config.yaml --steps 1-15 --mode overwrite
```

The demo includes pre-filled synchronization indices (`v1_start`/`v2_start`), so you can run the full pipeline directly.

### From Scratch

```bash

# 1) auto-generate xlsx (will fail if file already exists)
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 0

# 2) fill basic fields first (in_door / vertical / FAILED ...)

# 3) run scene + early preprocess first
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 1-5 --mode overwrite
```

Then manually inspect two views to determine synchronization, and fill `v1_start` / `v2_start` in the XLSX file.

```bash
# 4) continue the main pipeline
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 6-15 --mode overwrite

# 5) optional final step: run contact alignment only if `contacts` is labeled
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 16 --mode overwrite

# fast mode counterpart change the config file to config_fast.yaml
```

### Multi-GPU Processing

For faster processing with multiple GPUs, use `run_stages_mp.py`:

```bash
# Use multiple GPUs (e.g., GPU 0, 1, 2)
python run_stages_mp.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 1-15 --mode overwrite --gpu_ids 0,1,2
```

`run_stages_mp.py` supports all the same parameters as `run_stages.py`, plus:

- `--gpu_ids`: specify GPU IDs (e.g., `0,1,2`). Multi-GPU mode auto-enabled when count > 1
- `--worker_poll_interval`: worker queue poll interval in seconds (default: 1.0)
- `--max_retries`: max retries per task (default: 1)

The multi-GPU version automatically distributes sequences across available GPUs for parallel processing.

## Standard vs Fast

Both modes share the same step definitions. The main difference between `standard` and `fast` is output completeness:

- `fast`: optimized for mesh + motion tasks and quicker iteration.
- `standard`: keeps/generates fuller RGBD + mask assets for data/model training.

## Step Overview (1-16)

<details>
<summary><strong>Show all 16 steps</strong></summary>

### Stage 1: Scene Reconstruction

**Step 1: `sai`**

- Goal: extract keyframes and cameras from scene recording.
- Output: `transforms.json`.
- Note: `in_door`/`out_door` policy affects keyframe spacing.

**Step 2: `recon_scene`**

- Goal: reconstruct scene mesh from RGBD/depth cues.
- Output: `mesh_raw.ply`, `mesh_simplified.ply`.
- Note: voxel/depth truncation parameters trade quality vs speed.

**Step 3: `rebuild_colmap`**

- Goal: rebuild scene COLMAP database and model for later registration.
- Output: `colmap/database.db`, sparse model files.
- Note: check COLMAP environment when registration quality is unstable.

### Stage 2: Sequence Preprocess

**Step 4: `get_frames`**

- Goal: extract per-view images from raw recordings.
- Output: `raw1/images`, `raw2/images`.

**Step 5: `smooth_camera`**

- Goal: smooth camera trajectories from raw capture.
- Output: smoothed per-view camera files.

**Step 6: `slice_views`**

- Goal: cut aligned `v1/v2` clips using synchronization indices.
- Output: `v1/` and `v2/` folders with sliced images/cameras.
- Note: `v1_start`/`v2_start` must be correct before continuing.

**Step 7: `process_smpl`**

- Goal: estimate body states (SMPL/pose-related intermediates).
- Output: view-side `smpl_params.npz` (intermediate files).

**Step 8: `colmap_human_cam`**

- Goal: register human-view cameras into scene/world frame.
- Output: `v1/cameras_colmap.npz`, `v2/cameras_colmap.npz`.

### Stage 3: Geometry & Camera Optimization

**Step 9: `generate_keyframes`**

- Goal: build optimization keyframe set.
- Output: keyframe index/metadata.

**Step 10: `process_depth_mask`**

- Goal: generate/refine depth and human masks.
- Output: `images/`, `depths_refined/`, `masks/` (policy depends on mode).
- Note: this is the main `standard` vs `fast` completeness gap.

**Step 11: `vggt_track`**

- Goal: produce tracking constraints for later optimization.
- Output: tracking metadata.

**Step 12: `align_cameras`**

- Goal: align SAI/COLMAP camera systems to consistent scale/frame.
- Output: aligned camera files.

**Step 13: `unproj_human`**

- Goal: unproject human-view geometry to point clouds.
- Output: pointcloud files used by camera optimization.

**Step 14: `optim_human_cam`**

- Goal: optimize human-view camera trajectories.
- Output: optimized/aligned camera params (intermediate/final).

### Stage 4: Motion + Contact

**Step 15: `optim_motion`**

- Goal: optimize world-space motion parameters.
- Core output: `optim_params.npz`.
- Notes: this is the key artifact required by visualization and downstream tasks.

**Step 16: `align_contact`**

- Goal: optional contact-aware global alignment.
- Requires: valid `contacts` in XLSX.
- Typical outputs: `optim_params_aligned.npz`, aligned camera/`kp3d` artifacts.


</details>

## XLSX Fields (minimum)

- `scene_folder`, `seq_name`
- `in_door`, `vertical`
- `v1_start`, `v2_start`
- `FAILED`
- `contacts` (for step16 only)
- `skills` (used when exporting `plan.json`)

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
- `fast`: raw files + motion + scene mesh
- `standard`: keep everything in `fast` plus `images/depths_refined/masks`

## Completion Check

Check which steps have been completed for each sequence in the xlsx:

```bash
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 1-15 --check --config config.yaml
```

This will scan all sequences and report the completion status of each step without running any processing. Useful for tracking progress across multiple scenes.
