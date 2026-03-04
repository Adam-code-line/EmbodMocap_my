# Step Details

**Language / 语言切换:** [English](step_details.md) | [中文](step_details_zh.md)

> Source note: this document consolidates useful operational details from earlier `docs/embod_mocap.md` revisions in git history, then aligns them with the current stage-based pipeline.

## Scope

This page explains what each stage is for, what it usually outputs, and what to annotate in XLSX for stable processing.
Main entrypoint (open-source): `embod_mocap/run_stages.py`

- `standard`: keep/generate fuller RGBD + mask assets
- `fast`: focus on mesh + motion with lighter data generation
- Both modes run the same stage set; differences are mostly parameter/output policy

## Recommended Workflow

1. Generate XLSX template (step `0`) from dataset root.
2. Fill required XLSX fields (`in_door`, `vertical`, etc.).
3. Run scene + pre-processing stages.
4. Inspect preview, then fill synchronization indices (`v1_start`, `v2_start`).
5. Run camera/motion optimization stages.
6. Run contact alignment stage when `contacts` is available.
7. Export processed data (`dump_dataset.py`) for training/evaluation.
8. Run clean mode (`--clean`) when all post-processing is finished.

## Stage-by-stage Details

### Stage 1: Scene Reconstruction

1. `sai`
- Goal: extract keyframes/cameras from scene recording.
- Typical anchor: `transforms.json`.
- Notes: `in_door`/`out_door` policy affects keyframe spacing.

2. `recon_scene`
- Goal: reconstruct scene mesh from RGBD / depth cues.
- Typical outputs: `mesh_raw.ply`, `mesh_simplified.ply`.
- Notes: voxel/depth truncation parameters trade quality vs speed.

3. `rebuild_colmap`
- Goal: rebuild scene COLMAP DB/model used by later registration.
- Typical outputs: `colmap/database.db`, sparse model files.
- Notes: check COLMAP env when registration quality is unstable.

### Stage 2: Sequence Preprocess

4. `get_frames`
- Goal: extract per-view images from raw recordings.
- Typical outputs: `raw1/images`, `raw2/images`.

5. `smooth_camera`
- Goal: smooth camera trajectories from raw capture.
- Typical outputs: smoothed per-view camera files.

6. `slice_views`
- Goal: cut aligned `v1/v2` clips using synchronization indices.
- Typical outputs: `v1/` and `v2/` folders with sliced images/cameras.
- Notes: `v1_start`/`v2_start` must be correct before continuing.

7. `process_smpl`
- Goal: estimate body states (SMPL/pose-related intermediates).
- Typical outputs: view-side `smpl_params.npz` (intermediate files).

8. `colmap_human_cam`
- Goal: register human-view cameras into scene/world frame.
- Typical outputs: `v1/cameras_colmap.npz`, `v2/cameras_colmap.npz`.

### Stage 3: Geometry & Camera Optimization

9. `generate_keyframes`
- Goal: build optimization keyframe set.
- Typical outputs: keyframe index/metadata.

10. `process_depth_mask`
- Goal: generate/refine depth and human masks.
- Typical outputs: `images/`, `depths_refined/`, `masks/` (policy depends on mode).
- Notes: this is the main `standard` vs `fast` completeness gap.

11. `vggt_track`
- Goal: produce tracking constraints for later optimization.
- Typical outputs: tracking metadata.

12. `align_cameras`
- Goal: align SAI/COLMAP camera systems to consistent scale/frame.
- Typical outputs: aligned camera files.

13. `unproj_human`
- Goal: unproject human-view geometry to point clouds.
- Typical outputs: pointcloud files used by camera optimization.

14. `optim_human_cam`
- Goal: optimize human-view camera trajectories.
- Typical outputs: optimized/aligned camera params (intermediate/final).

### Stage 4: Motion + Contact

15. `optim_motion`
- Goal: optimize world-space motion parameters.
- Core output: `optim_params.npz`.
- Notes: this is the key artifact required by visualization and downstream tasks.

16. `align_contact`
- Goal: optional contact-aware global alignment.
- Requires: valid `contacts` in XLSX.
- Typical outputs: `optim_params_aligned.npz`, aligned camera/`kp3d` artifacts.

## XLSX Fields You Should Maintain

- Required: `scene_folder`, `seq_name`, `in_door`, `vertical`, `v1_start`, `v2_start`
- Control: `FAILED`
- Optional but useful: `skills`, `contacts`, `note`

### About `FAILED`

Mark sequence as `FAILED` when data is not usable (e.g., severe depth quality issues, dynamic scene breaks static assumptions, registration repeatedly fails). Failed rows should be skipped by later processing/export.

### About `contacts`

Format example: `[(frame_id, [x, y, z]), ...]`

- empty/invalid `contacts`: stage 16 is skipped
- valid `contacts`: run stage 16 to produce aligned outputs

### About `skills`

`skills` can define downstream motion segments. Exporter can write `plan.json` for each sequence.

## Export Notes (`dump_dataset.py`)

Common outputs per sequence include:

- world motion annotation (`optim_params.npz` or aligned variant)
- camera trajectories (`cameras_v1.ply`, `cameras_v2.ply`)
- optional copied RGBD/mask assets
- `plan.json` (if `skills` are provided)

`--use_aligned` prefers `optim_params_aligned.npz` when available.

## Cleaning Policy (Current)

Use clean mode only after processing and export are done.

- `--clean all`: keep raw safety files only
- `--clean fast`: keep core outputs + lightweight visualization files
- `--clean standard`: keep `fast` + RGBD/mask assets

Dry run first:

```bash
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast --clean_dry_run
```

## Troubleshooting Checklist

- Check sequence `error.txt` first
- Verify COLMAP environment and model files
- Confirm submodules/checkpoints are correctly installed
- Re-run with `--check` before large reruns
