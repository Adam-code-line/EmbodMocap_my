# 可视化说明

**语言切换 / Language:** [中文](visualization_zh.md) | [English](visualization.md)

## 1）通过 `tools/visualize.py` 生成视频可视化

**单 seq 模式**（使用 `--seq_path`）：

```bash
cd embod_mocap
python tools/visualize.py --seq_path /path/to/scene/seq0 --input --processed --optim_cam --downscale 2 --mode overwrite
```

**xlsx 批量模式**（使用 `--xlsx`）：

```bash
cd embod_mocap
python tools/visualize.py --xlsx seq_info.xlsx --data_root /path/to/data --input --processed --optim_cam --downscale 2 --mode overwrite
```

注意：`--seq_path` 和 `--xlsx` 二选一；在 `--xlsx` 模式下，`--data_root` 是必填参数。

### 参数：

- `--seq_path`：单个 seq 路径，例如 `/path/to/scene/seq0`
- `--xlsx`：xlsx 清单路径，默认跳过 `FAILED` 行
- `--data_root`：必填根目录，用于和 xlsx 中的 `scene_folder` 拼接
- `--force_all`：批量模式下也处理标记为 `FAILED` 的行
- `--input`：生成输入双视角拼接视频 `concat_input.mp4`
- `--processed`：生成带 SMPL 叠加的处理结果视频 `concat_processed.mp4`
- `--optim_cam`：生成优化相机视角下的 SMPL 渲染视频 `concat_optimized.mp4`
- `--device`：推理设备，默认 `cuda:0`
- `--downscale`：视频降采样倍率，默认 `2`
- `--mode`：`overwrite` 或 `skip`，控制是否覆盖已有视频
- `--vis_chunk`：SMPL 可视化分块大小，默认 `60`

### 输出：

该工具会在 seq 目录下生成 MP4 视频：
- `concat_input.mp4`：`v1` 和 `v2` 输入帧的左右拼接视频
- `concat_processed.mp4`：带 SMPL 姿态叠加的处理结果视频
- `concat_optimized.mp4`：优化相机视角下的 SMPL 渲染视频

## 2）通过 `visualize_viser.py` 交互式可视化

使用 Viser 在浏览器中交互查看 scene 网格、SMPL 动作和相机轨迹。

**单 scene 模式**（使用 `--scene_path`）：

```bash
cd embod_mocap
python tools/visualize_viser.py --scene_path /path/to/scene --port 8080 --max_frames -1 --stride 2 --mesh_level 1 --scene_mesh simple
```

**多 scene 模式**（使用 `--xlsx`）：

```bash
cd embod_mocap
python tools/visualize_viser.py --xlsx seq_info.xlsx --data_root /path/to/data --port 8080 --max_frames -1 --stride 2 --mesh_level 1 --scene_mesh simple
```

注意：`--scene_path` 和 `--xlsx` 二选一，不能同时使用。

### 参数：

- `--scene_path`：单 scene 文件夹路径（包含 seq* 子文件夹）
- `--xlsx`：xlsx 清单文件路径（多 scene 模式，自动跳过 FAILED 行）
- `--data_root`：可选的根路径前缀，与 xlsx 中的 scene_folder 拼接
- `--port 8080`：指定可视化端口（默认：8080）
- `--max_frames -1`：每个 seq 最大加载帧数；-1 表示加载所有帧（默认：-1）
- `--stride 2`：帧采样步长，例如 2 表示每 2 帧加载一次（默认：1）
- `--mesh_level 1`：SMPL 网格降采样级别 - 0=完整，1=降采样（约 1723 顶点），2=更粗（默认：1）
- `--scene_mesh simple`：scene 网格模式 - `simple`=优先使用 mesh_simplified.ply 并回退到 mesh_raw.ply，`raw`=仅使用 mesh_raw.ply，`no`=禁用 scene 网格（默认：simple）
- `--hq`：启用高质量渲染，包含多光源和阴影

### 使用说明：

- 该脚本依赖 seq 结果（如 `optim_params.npz`）和 scene 网格（优先 `mesh_simplified.ply`，否则回退 `mesh_raw.ply`）。
- 启动后按终端提示在浏览器打开本地地址。
- 使用网页界面可以在不同 scene / seq 间切换并控制播放。
