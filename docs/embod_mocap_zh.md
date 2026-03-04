# EmbodMocap 主流程（入口脚本可重命名）

**语言切换 / Language:** [中文](embod_mocap_zh.md) | [English](embod_mocap.md)

本项目当前统一入口为：`embod_mocap/run_stages.py`。  
如在开源仓库中重命名入口脚本，请同步替换本文档命令中的脚本名。

## 快速开始

建议在 `embod_mocap/` 目录执行：

```bash
cd embod_mocap

# 1) 先自动生成 xlsx（步骤0）
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 0

# 2) 先填写基础字段（in_door / vertical / FAILED 等）

# 3) 先跑场景与前半预处理
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 1-5 --mode overwrite
```

然后需要人工看双视角画面做同步，回填 xlsx 的 `v1_start` / `v2_start`。

```bash
# 可选：预览辅助
python processor/visualize.py /path/to/scene/seq0 --input --processed --downscale 2 --mode overwrite

# 4) 对齐索引填写后，再继续后续流程
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config.yaml --steps 6-16 --mode overwrite

# fast 模式对应同样的分段流程
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config_fast.yaml --steps 1-5 --mode overwrite
python run_stages.py seq_info.xlsx --data_root /path/to/data --config config_fast.yaml --steps 6-16 --mode overwrite
```

## Standard / Fast 模式

两者都跑 1-16 主流程，核心差异在输出资产完整度：
- `fast`：更适合只关心 mesh + motion 的具身任务，迭代更快。
- `standard`：更适合需要完整 RGBD + mask 资产的训练场景。

步骤与配置详细解释见：[English](step_details.md) | [中文](step_details_zh.md)。

## 步骤总览（1-16）

### Stage 1：场景重建（Steps 1-3）

- 1 `sai`：场景关键帧与相机初始化
- 2 `recon_scene`：场景重建（`mesh_raw.ply` 与 `mesh_simplified.ply`）
- 3 `rebuild_colmap`：场景 COLMAP 数据库

### Stage 2：序列预处理（Steps 4-7）

- 4 `get_frames`：从 raw 数据提帧
- 5 `smooth_camera`：平滑相机轨迹
- 6 `slice_views`：切分 v1/v2 视角（依赖已填写 `v1_start`/`v2_start`）
- 7 `process_smpl`：人体 SMPL 估计

### Stage 3：人体视角相机标定（Steps 8-12）

- 8 `colmap_human_cam`：人体视角 COLMAP 相机
- 9 `generate_keyframes`：生成关键帧
- 10 `process_depth_mask`：深度与掩码生成/细化
- 11 `vggt_track`：VGGT 跟踪约束
- 12 `align_cameras`：相机与尺度对齐

### Stage 4：运动与接触对齐（Steps 13-16）

- 13 `unproj_human`：人体反投影点云
- 14 `optim_human_cam`：人体视角相机优化
- 15 `optim_motion`：世界坐标运动优化（`optim_params.npz`）
- 16 `align_contact`：接触对齐（需要有效 `contacts`）

## XLSX 关键字段

- `scene_folder`, `seq_name`
- `in_door`, `vertical`
- `v1_start`, `v2_start`
- `FAILED`
- `contacts`（仅 step16 用）
- `skills`（导出 `plan.json` 时使用）

### contacts（Step16）

只有当 `contacts` 有效时才执行 step16。若为空或 `nan`，该步骤自动跳过。

## 清理（--clean）

当前支持：`--clean standard|fast|all`，并要求提供 `xlsx + data_root`。

```bash
# 先预览理论删除列表（不真正删除）
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast --clean_dry_run

# 真正执行
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast
```

当前语义：
- `all`：只保留 raw 安全文件
- `fast`：保留核心结果 + 轻量可视化产物
- `standard`：在 `fast` 基础上额外保留 `images/depths_refined/masks`

## 可视化

```bash
# 按 xlsx 批量可视化
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps vis --config config.yaml

# 单序列可视化
python processor/visualize.py /path/to/scene/seq0 --input --optim_cam --downscale 2 --mode overwrite
```

## 完成检查

```bash
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps 1-16 --check --config config.yaml
```
