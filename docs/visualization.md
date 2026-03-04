# Visualization Guide (Pipeline Entrypoint / processor/visualize.py)

**Language / 语言切换:** [English](visualization.md) | [中文](visualization_zh.md)

Current pipeline entry script name is `run_stages.py`. If renamed in open-source packaging, update commands accordingly.

## 1) Batch Visualization via `run_stages.py`

```bash
cd embod_mocap
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps vis --config config.yaml
```

This runs per-sequence visualization using xlsx entries.

## 2) Single-Sequence Visualization via `processor/visualize.py`

`input_folder` is a required positional argument.

```bash
cd embod_mocap
python processor/visualize.py /path/to/scene/seq0 --input --optim_cam --downscale 2 --mode overwrite
```

## 3) Interactive Visualization via `visualize_viser.py`

Use Viser for interactive 3D browsing of scene mesh, SMPL motion, and cameras.

```bash
cd embod_mocap
python visualize_viser.py /path/to/scene/seq0
```

Useful options:

- `--port 8080`: set web UI port
- `--max-frames 300`: limit loaded frame count
- `--stride 5`: subsample frames for faster preview

Notes:

- This script expects sequence-level outputs such as `optim_params.npz` and scene mesh (`mesh_simplified.ply` or `mesh_raw.ply`).
- Open your browser to the printed local URL after startup.

## 4) Common Modes

- `--input`: input view concat
- `--processed`: processed view concat
- `--optim_cam`: camera-view overlay (`concat_optimized*.mp4`)
- `--align_contact`: visualize step16 aligned outputs

## 5) Useful Options

- `--downscale 2`
- `--mode overwrite|skip`
- `--device cuda:0`
- `--vis_chunk 60`

## 6) Outputs (typical)

- `concat_input.mp4`
- `concat_processed.mp4`
- `concat_optimized.mp4`
- `kp3d.ply`

## 7) Troubleshooting

- Missing `mesh_simplified.ply`: script will fallback to `mesh_raw.ply` in related paths.
- Missing `optim_params.npz`: `--optim_cam` cannot run.
- OOM: increase `--downscale`, reduce chunk sizes.
