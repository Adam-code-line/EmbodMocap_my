# 可视化说明（run_stages / processor/visualize.py）

**语言切换 / Language:** [中文](visualization_zh.md) | [English](visualization.md)

## 1）通过 `run_stages.py` 批量可视化

```bash
cd embod_mocap
python run_stages.py seq_info.xlsx --data_root /path/to/data --steps vis --config config.yaml
```

该方式会按 xlsx 中序列逐个执行可视化。

## 2）通过 `processor/visualize.py` 单序列可视化

`input_folder` 是必填位置参数：

```bash
cd embod_mocap
python processor/visualize.py /path/to/scene/seq0 --input --optim_cam --downscale 2 --mode overwrite
```

## 3）通过 `visualize_viser.py` 交互式可视化

使用 Viser 在浏览器中交互查看场景网格、SMPL 动作和相机轨迹：

```bash
cd embod_mocap
python visualize_viser.py /path/to/scene/seq0
```

常用参数：

- `--port 8080`：指定可视化端口
- `--max-frames 300`：限制加载帧数
- `--stride 5`：按步长抽帧，加速预览

说明：

- 该脚本依赖序列结果（如 `optim_params.npz`）和场景网格（优先 `mesh_simplified.ply`，否则回退 `mesh_raw.ply`）。
- 启动后按终端提示在浏览器打开本地地址。

## 4）常用模式

- `--input`：输入视频拼接
- `--processed`：处理中间结果拼接
- `--optim_cam`：相机视角叠加人体（`concat_optimized*.mp4`）
- `--align_contact`：查看 step16 对齐后结果

## 5）常用参数

- `--downscale 2`
- `--mode overwrite|skip`
- `--device cuda:0`
- `--vis_chunk 60`

## 6）典型输出

- `concat_input.mp4`
- `concat_processed.mp4`
- `concat_optimized.mp4`
- `kp3d.ply`

## 7）排查建议

- 缺少 `mesh_simplified.ply`：相关流程会回退使用 `mesh_raw.ply`。
- 缺少 `optim_params.npz`：`--optim_cam` 无法执行。
- 显存不足：增大 `--downscale`，减小 chunk 参数。
