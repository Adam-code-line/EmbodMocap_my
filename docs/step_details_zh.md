# 步骤详解

**语言切换 / Language:** [中文](step_details_zh.md) | [English](step_details.md)

> 说明：本文从 git 历史中的旧版 `docs/embod_mocap.md` 提取了仍然有价值的流程细节（如 FAILED、同步标注、contacts/skills、导出说明），并对齐到当前分阶段主流程。

## 文档范围

本文解释每个步骤的目标、常见产物，以及 XLSX 中需要维护的关键字段。
主入口（开源版）为：`embod_mocap/run_stages.py`

- `standard`：保留/生成更完整的 RGBD + mask 数据资产
- `fast`：更偏向 mesh + motion，减少非必要数据生成
- 两种模式步骤集合一致，差异主要是参数和输出保留策略

## 推荐工作流

1. 用步骤 `0` 从数据根目录自动生成 XLSX。
2. 先填必填字段（如 `in_door`、`vertical`）。
3. 先跑场景重建和序列预处理。
4. 看预览后补齐 `v1_start`、`v2_start`。
5. 再跑相机与运动优化阶段。
6. 若有 `contacts`，再跑接触对齐步骤。
7. 用 `dump_dataset.py` 导出训练/评估数据。
8. 全部处理结束后再执行 `--clean`。

## 分阶段步骤详解

### Stage 1：场景重建

1. `sai`
- 目标：从场景录制中提取关键帧与相机。
- 常见锚点：`transforms.json`。
- 备注：`in_door`/`out_door` 会影响关键帧稀疏策略。

2. `recon_scene`
- 目标：基于深度线索重建场景网格。
- 常见产物：`mesh_raw.ply`、`mesh_simplified.ply`。
- 备注：体素和深度截断参数影响质量与速度平衡。

3. `rebuild_colmap`
- 目标：重建后续配准需要的 COLMAP 数据库/模型。
- 常见产物：`colmap/database.db` 和稀疏模型。
- 备注：如果配准不稳，优先排查 COLMAP 环境。

### Stage 2：序列预处理

4. `get_frames`
- 目标：从原始双视角视频提取图像帧。
- 常见产物：`raw1/images`、`raw2/images`。

5. `smooth_camera`
- 目标：平滑原始相机轨迹。
- 常见产物：视角相机平滑结果。

6. `slice_views`
- 目标：按同步索引切出对齐的 `v1/v2` 片段。
- 常见产物：`v1/`、`v2/` 目录及对应切片数据。
- 备注：继续后续步骤前必须确保 `v1_start/v2_start` 正确。

7. `process_smpl`
- 目标：生成人体状态中间结果（SMPL/姿态相关）。
- 常见产物：视角侧 `smpl_params.npz`（中间文件）。

8. `colmap_human_cam`
- 目标：把人体视角相机注册到场景世界坐标。
- 常见产物：`v1/cameras_colmap.npz`、`v2/cameras_colmap.npz`。

### Stage 3：几何与相机优化

9. `generate_keyframes`
- 目标：生成后续优化所需关键帧集合。
- 常见产物：关键帧索引/元数据。

10. `process_depth_mask`
- 目标：生成/细化深度与人体掩码。
- 常见产物：`images/`、`depths_refined/`、`masks/`（保留策略由模式控制）。
- 备注：这里是 `standard` 与 `fast` 的主要差异来源。

11. `vggt_track`
- 目标：生成优化阶段使用的跟踪约束。
- 常见产物：跟踪中间信息。

12. `align_cameras`
- 目标：把 SAI / COLMAP 相机统一到一致尺度和坐标。
- 常见产物：对齐后的相机文件。

13. `unproj_human`
- 目标：反投影人体视角几何点云。
- 常见产物：用于后续优化的点云文件。

14. `optim_human_cam`
- 目标：优化人体视角相机轨迹。
- 常见产物：优化/对齐后的相机参数（中间或最终）。

### Stage 4：运动与接触对齐

15. `optim_motion`
- 目标：优化世界坐标下的人体运动参数。
- 核心产物：`optim_params.npz`。
- 备注：这是可视化和下游任务最关键的文件。

16. `align_contact`
- 目标：基于接触点做可选全局对齐。
- 依赖：XLSX 中 `contacts` 有效。
- 常见产物：`optim_params_aligned.npz` 及对齐后的相机/`kp3d` 文件。

## XLSX 关键字段

- 必填：`scene_folder`、`seq_name`、`in_door`、`vertical`、`v1_start`、`v2_start`
- 控制字段：`FAILED`
- 推荐字段：`skills`、`contacts`、`note`

### 关于 `FAILED`

当序列不可用时应标记 `FAILED`（例如深度质量很差、动态物体过多导致静态假设失效、配准反复失败）。后续处理/导出应跳过这些序列。

### 关于 `contacts`

格式示例：`[(frame_id, [x, y, z]), ...]`

- 为空或无效：跳过第 16 步
- 有效：可跑第 16 步生成对齐结果

### 关于 `skills`

`skills` 可用于下游动作段定义；导出时可以生成每序列的 `plan.json`。

## 导出说明（`dump_dataset.py`）

常见序列级导出包括：

- 世界系运动参数（`optim_params.npz` 或 aligned 版本）
- 相机轨迹（`cameras_v1.ply`、`cameras_v2.ply`）
- 可选 RGBD/mask 资产
- `plan.json`（当 `skills` 存在时）

`--use_aligned` 会优先读取 `optim_params_aligned.npz`（若存在）。

## 清理策略（当前）

建议在处理和导出都完成后再清理。

- `--clean all`：仅保留 raw 安全文件
- `--clean fast`：保留核心结果 + 轻量可视化文件
- `--clean standard`：在 `fast` 基础上额外保留 RGBD/mask 资产

先 dry run 预览：

```bash
python run_stages.py seq_info.xlsx --data_root /path/to/data --clean fast --clean_dry_run
```

## 排障清单

- 先看序列下 `error.txt`
- 检查 COLMAP 环境与模型文件
- 确认 submodule 与 checkpoints 是否完整
- 大规模补跑前先用 `--check` 看完成度
