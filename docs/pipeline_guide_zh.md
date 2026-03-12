# EmbodMocap 主流程技术指南

> 文档性质：面向开发者的流水线技术手册，覆盖依赖库说明、各步骤常见问题、输出质量评判方法。
> 最后更新：2026-03-12

---

## 一、主流程依赖库全景

### 1.1 按功能分类

| 功能域 | 库/模块 | 版本 | 作用 |
|--------|---------|------|------|
| **深度学习框架** | torch / torchvision | 2.4.0+cu121 | 所有神经网络推理与优化 |
| **Attention 加速** | xformers | 0.0.27.post2 | DINOv2 nested tensors（Step 10 必需） |
| **3D 视觉** | pytorch3d | 0.7.8 | Chamfer Distance 损失（Step 14） |
| **相机标定/SfM** | spectacularAI | 1.35.0 | Step 1 关键帧与相机位姿估计 |
| **SfM 点云** | COLMAP（系统） | 3.7 | Step 2/3/8 稀疏重建 |
| **人体检测** | ultralytics（YOLOv8） | 8.4.x | Step 7 人体 bbox 检测 |
| **人体关键点** | mmpose（ViTPose 0.24.0） | 0.24.0 | Step 7 2D 关键点检测 |
| **mmcv 后端** | mmcv | 1.7.2 | mmpose 依赖（无 CUDA ops） |
| **3D 姿态估计** | VIMO（内部封装） | — | Step 7 SMPL 参数初始估计 |
| **分割** | SAM2 | 1.0 | Step 7/10 人体掩码生成 |
| **语言引导分割** | lang_sam（submodule） | — | Step 10 "person" 提示分割 |
| **深度精化** | lingbot_depth（submodule） | — | Step 10 DINOv2-based 深度图优化 |
| **视觉跟踪** | VGGT（内置） | — | Step 11 跨帧特征点追踪 |
| **3D 场景处理** | open3d | — | 点云 IO、网格操作、可视化 |
| **图像处理** | opencv-python (cv2) | — | 帧读写、掩码处理、resize |
| **数值计算** | numpy | 2.4.3 | 矩阵运算、存储（.npz） |
| **旋转工具** | scipy.spatial.transform | — | 旋转矩阵/四元数/AA 互转、Slerp |
| **时序平滑** | scipy.ndimage | — | gaussian_filter1d 平滑关键点序列 |
| **渲染变换** | t3drender | 1.0 | rot6d/rotmat/aa 互转（Step 14/15） |
| **网格处理** | trimesh | — | 网格加载与操作（Step 11） |
| **SMPL 模型** | smplx / 内置 SMPL | — | 正向运动学，生成关节点与 mesh |
| **可视化** | viser | 0.2.x | 交互式 3D 可视化（工具脚本） |
| **数据读写** | openpyxl | — | 读写 .xlsx 序列配置 |

### 1.2 按步骤的核心依赖

| 步骤 | 名称 | 核心依赖 |
|------|------|---------|
| 1 | sai | `spectacularAI` |
| 2 | recon_scene | COLMAP（系统命令）、`open3d` |
| 3 | rebuild_colmap | COLMAP |
| 4 | get_frames | `ffmpeg`（系统命令）|
| 5 | smooth_camera | `numpy`、`scipy` |
| 6 | slice_views | `numpy`、`openpyxl` |
| 7 | process_smpl | `torch`、`mmcv`、`mmpose (ViTPose)`、`ultralytics`、`SAM2`、`lang_sam`、`smplx`、VIMO checkpoint |
| 8 | colmap_human_cam | COLMAP、`cv2`、`numpy`、`open3d`、`scipy` |
| 9 | generate_keyframes | `numpy`、`json` |
| 10 | process_depth_mask | `torch`、`xformers`、`lingbot_depth`、`SAM2`、`lang_sam`、`cv2`、`PIL` |
| 11 | vggt_track | `torch`、VGGT（内置）、`trimesh`、`cv2` |
| 12 | align_cameras | `numpy` |
| 13 | unproj_human | `torch`、`open3d`、`cv2`、`numpy` |
| 14 | optim_human_cam | `torch`、`pytorch3d`、`open3d`、`t3drender`、`cv2` |
| 15 | optim_motion | `torch`、`scipy`、`t3drender`、SMPL 模型文件 |
| 16 | align_contact | `numpy`、`pytorch3d`（需 contacts 字段） |

---

## 二、各步骤常见问题与排查

### Step 1 — sai（SpectacularAI 关键帧提取）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `ModuleNotFoundError: spectacularAI` | 包名大小写错误或未安装 | `pip install spectacularAI==1.35.0`（注意大写 AI） |
| 输出 `transforms.json` 关键帧数极少（<10） | 视频运动太小、光照差 | 检查视频质量；尝试调整 SAI 配置参数 |
| 运行卡死 | SAI 在处理高分辨率长视频 | 属正常现象，等待即可；可先用短视频验证 |

**验证 Step 1 成功**：`{seq}/transforms.json` 存在，`frames` 数组非空，每帧含 `transform_matrix`（4×4）和 `file_path`。

---

### Step 2 — recon_scene（COLMAP 场景重建）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `libcudart.so.12: cannot open shared object file` | COLMAP apt 版找不到 conda CUDA 库 | `export LD_LIBRARY_PATH=/home/wubin/miniconda3/envs/embodmocap/lib/:$LD_LIBRARY_PATH` |
| COLMAP 极慢（数小时） | apt 版无 CUDA 加速，全 CPU 运行 | 正常现象；可考虑升级 GPU 版 COLMAP |
| `mesh_raw.ply` 点很稀疏 | COLMAP 无 CUDA，匹配对数不够 | 属 CPU 版局限；多数场景仍可跑通后续步骤 |
| COLMAP exhaustive matching OOM | 图片太多 | 在 config.yaml 中调小 `colmap_num_images` 或改用 vocab_tree_matching |

**验证 Step 2 成功**：`{seq}/mesh_raw.ply` 与 `mesh_simplified.ply` 存在，用 `open3d` 或 MeshLab 打开确认点云覆盖场景主要区域。

---

### Step 3 — rebuild_colmap（重建 COLMAP 数据库）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `database.db` 生成失败 | COLMAP 命令路径问题 | 确认 `/usr/bin/colmap` 存在；检查 LD_LIBRARY_PATH |
| 稀疏模型点太少 | vocab_tree 文件路径错误 | 检查 `checkpoints/vocab_tree_flickr100K_words32K.bin` 是否存在 |

---

### Step 4 — get_frames（视频提帧）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `ffmpeg: command not found` | 系统未安装 ffmpeg | `sudo apt install -y ffmpeg` |
| 提帧数量与预期不符 | fps 参数错误 | 检查 `--v1_fps` / `--v2_fps` 参数是否与录制帧率一致 |

---

### Step 5 — smooth_camera（相机轨迹平滑）

基本无特殊问题，纯 numpy 计算，偶有数值异常：

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| 平滑后轨迹有跳变 | 相机原始轨迹中含异常帧 | 检查 SAI 输出，过滤异常帧 |

---

### Step 6 — slice_views（视角切片）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| 报错"v1_start not found" | xlsx 中未填写 `v1_start`/`v2_start` | **手动打开 xlsx 填写**，这是流程中唯一需要人工介入的步骤 |
| 切片后图像数量为 0 | start 帧超出范围 | 核对视频总帧数与填写的起始帧 |

> ⚠️ **Step 6 前必须手动填写 xlsx**，否则后续所有步骤均无法正确切片。

---

### Step 7 — process_smpl（SMPL 参数估计）

这是最容易出问题的步骤，依赖最多。

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `ImportError: cannot import name 'parallel' from 'mmcv'` | 装了 mmcv 2.x | 卸载后改装 mmcv 1.7.2（源码编译） |
| `mmcv version X does not match maximum Y` | ViTPose 版本上限检查 | Patch `thirdparty/ViTPose/mmpose/__init__.py`：`mmcv_maximum_version = "99.0.0"` |
| `ValueError: setting an array element with a sequence` at `topdown_heatmap_base_head.py:71` | numpy>=1.24 兼容问题 | Patch：`float(np.array(...).reshape(-1)[0])` |
| `AttributeError: module 'numpy' has no attribute 'bool'` | chumpy 使用废弃 API | `pip install git+https://github.com/mattloper/chumpy` |
| SMPL 文件缺失（`SMPL_NEUTRAL.pkl` not found） | body_models 未就位 | 检查 `body_models/smpl/` 目录完整性 |
| `smpl_params.npz` 生成但 body_pose 全为零 | 人体检测失败（YOLO 无检测框） | 检查图像质量；确认人体在画面中可见 |
| VIMO checkpoint 加载失败 | checkpoint 路径错误 | 检查 `config_paths.py` 中 `vimo_checkpoint` 路径 |
| 推理速度极慢（GPU 利用率低） | batch size 过小或显存泄漏 | 正常现象；长序列耗时较长 |

**验证 Step 7 成功**：`v1/smpl_params.npz` 与 `v2/smpl_params.npz` 存在，加载后 `body_pose` shape 为 `(N, 23, 3)` 或 `(N, 69)`，N 与帧数一致，且数值不全为零。

---

### Step 8 — colmap_human_cam（COLMAP 人体相机标定）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `cameras_colmap.npz` 中 `valid_ids` 为空 | COLMAP 稀疏点不足，无帧被标定 | Step 2/3 重建质量差；考虑增加图像质量或换更好的 COLMAP |
| `points3D.npz` 点很少 | 掩码过滤太严格或相机参数错误 | 检查 `calibration.json` 中的内参是否正确 |

---

### Step 9 — generate_keyframes（关键帧生成）

通常无问题，纯计算，输出 `keyframes.json`。

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `keyframes.json` 中 `vggt` 数组为空 | points2D.npz 为空（Step 8 失败） | 修复 Step 8 后重跑 |

---

### Step 10 — process_depth_mask（深度精化 + 掩码生成）

耗时最长的步骤，依赖 xformers。

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `AssertionError: xFormers is required for using nested tensors` | xformers 未安装 | `pip install xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121` |
| `masks_keyframe/` 目录为空 | Step 10 提前退出（显存不足或断言失败） | 检查日志；确认 xformers 安装正确 |
| 深度图精化效果差（噪点多） | lingbot_depth checkpoint 缺失 | 检查 `checkpoints/lingbot_depth_vitl14.pt`（1.28 GB）是否存在 |
| SAM2 分割将背景误判为人 | lang_sam "person" 提示在复杂场景失效 | 属模型局限，检查输出掩码是否覆盖人体区域 |
| 显存 OOM | batch size 过大 | 检查 config_fast.yaml 中的 batch 参数，适当减小 |

**验证 Step 10 成功**：`v1/masks_keyframe/` 中有与关键帧对应的 PNG 文件；`v1/depths_keyframe_refined/` 同样有对应文件。用图像查看器打开掩码确认白色区域覆盖人体。

---

### Step 11 — vggt_track（VGGT 视觉追踪）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `FileNotFoundError: .../masks_keyframe/v1_0000.png` | Step 10 未跑完 | 先确保 Step 10 成功，masks_keyframe/ 非空 |
| VGGT checkpoint 加载失败 | `checkpoints/vggt.pt` 缺失或损坏 | 重新下载 checkpoint |
| `vggt_tracks.npz` 中轨迹数量为 0 | 关键帧太少或图像重叠度不够 | 检查 `keyframes.json` 中 `vggt` 列表长度 |
| 追踪结果漂移 | 场景缺乏纹理特征 | 属正常局限，尝试增加关键帧数量 |

**验证 Step 11 成功**：`vggt_tracks.npz` 存在，包含 `track_v1`、`track_v2`、`frame_ids` 字段，轨迹数量（第一维）> 0。

---

### Step 12 — align_cameras（SAI-COLMAP 相机对齐）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `cameras_sai_transformed.npz` 旋转矩阵含 NaN | SVD 对齐失败（对应点不足） | 检查 Step 8 输出的有效相机数量 |
| 对齐误差极大（>1m） | COLMAP 与 SAI 坐标系不兼容 | 检查视频是否包含足够重叠场景 |

---

### Step 13 — unproj_human（人体点云反投影）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `pointcloud.ply` 为空 | 掩码全黑或深度图全零 | 检查 Step 10 输出质量 |
| 点云在世界坐标中位置异常（离场景很远） | 相机内参错误 | 检查 `calibration.json` 中焦距/主点参数 |

---

### Step 14 — optim_human_cam（相机-人体联合优化）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `ImportError: pytorch3d` | pytorch3d 未安装 | 按 CLAUDE.md 安装清华镜像 conda 包 |
| Chamfer loss 不收敛（一直很大） | 点云初始位置与相机估计偏差太大 | 检查 Step 12/13 输出；调小学习率 |
| `cameras.npz` 中 R 矩阵行列式≠1 | 优化过拟合导致旋转矩阵退化 | 减少优化迭代次数；增加正则项 |
| CUDA OOM | 点云太大 + batch 太大 | 在 config.yaml 中调小 `max_points` |

**验证 Step 14 成功**：`v1/cameras.npz` 和 `v2/cameras.npz` 存在，R shape 为 `(N, 3, 3)`，T shape 为 `(N, 3)`，K shape 为 `(N, 3, 3)`，且 R 矩阵行列式接近 1.0（`np.linalg.det(R)` ≈ 1）。

---

### Step 15 — optim_motion（SMPL 运动优化）

| 问题现象 | 原因 | 解决方法 |
|----------|------|---------|
| `optim_params.npz` 中 `optim_total_loss` 极大（>1000） | 优化未收敛 | 检查 Step 14 相机质量；视频遮挡太严重 |
| 优化后人体穿透场景 | 场景网格精度不足 | 提升 COLMAP 重建质量；调整穿透损失权重 |
| SMPL `transl` 全为零 | 相机参数中 T 异常 | 检查 Step 14 输出 T 值是否在合理范围内 |
| 运动抖动严重 | 时序平滑权重太小 | 调整 config 中 smooth loss 权重 |
| SMPL 身体比例畸形（过高或过矮） | betas 优化发散 | 固定 betas 参数，只优化 pose |

---

## 三、主流程输出质量评判

### 3.1 核心输出文件

主流程（Steps 1–15）产生以下核心输出，评判重点落在这些文件：

```
{seq}/
├── mesh_raw.ply / mesh_simplified.ply   # 场景网格（Step 2）
├── v1/smpl_params.npz                   # 初始 SMPL 参数（Step 7）
├── v2/smpl_params.npz
├── v1/cameras.npz                       # 优化后相机（Step 14）
├── v2/cameras.npz
└── optim_params.npz                     # 最终优化结果（Step 15，核心）
```

### 3.2 定量指标

#### 场景网格（Step 2）

| 指标 | 合格范围 | 检查方式 |
|------|----------|---------|
| 点云密度 | 点数 > 1000（室内场景） | `open3d.io.read_point_cloud` → `len(pcd.points)` |
| 覆盖范围 | bbox 对角线长度合理（1–10m 室内） | `pcd.get_axis_aligned_bounding_box()` |
| 平面平整度 | 地板区域点法向一致 | open3d 法向量估计后检查方差 |

#### 相机参数（Step 14）

| 指标 | 合格范围 | 检查方式 |
|------|----------|---------|
| 旋转矩阵合法性 | det(R) ∈ [0.99, 1.01] | `np.linalg.det(cameras['R'])` |
| 平移尺度 | T 在 0.1m–10m 范围内（室内） | `np.abs(cameras['T']).mean()` |
| 有效相机数 | > 总帧数的 80% | `cameras['R'].shape[0]` vs 图像总数 |
| 重投影误差 | 应 < 10 像素（肉眼难感知） | 用 `K @ R @ X + T` 重投影关键点对比 |

#### 最终 SMPL 参数（Step 15，`optim_params.npz`）

```python
import numpy as np
data = np.load('optim_params.npz', allow_pickle=True)
# 正确的 optim_params.npz 应包含：
print(list(data.keys()))
# 期望：['global_orient', 'body_pose', 'betas', 'transl',
#        'keypoints3d', 'keypoints3d_conf', 'K1', 'K2',
#        'R1', 'R2', 'T1', 'T2', 'bbox_xyxy1', 'bbox_xyxy2',
#        'optim_total_loss']
print('body_pose shape:', data['body_pose'].shape)  # (T, 23, 3) 或 (T, 69)
print('total loss:', data['optim_total_loss'])       # 应 < 100 为合格
```

| 字段 | 期望 shape | 合格范围 |
|------|-----------|---------|
| `global_orient` | `(T, 3)` 或 `(T, 1, 3)` | 范数在 [-π, π] 内 |
| `body_pose` | `(T, 23, 3)` 或 `(T, 69)` | 数值不全为零；关节角 < π |
| `betas` | `(T, 10)` 或 `(10,)` | 绝对值 < 5（人体形状合理） |
| `transl` | `(T, 3)` | 不全为零；量纲为米 |
| `keypoints3d` | `(T, 17, 3)` | 人体各关节点在空间中合理分布 |
| `optim_total_loss` | 标量 | < 100（越小越好） |

### 3.3 定性评判（可视化）

#### 推荐：Viser 交互式可视化

```bash
conda activate embodmocap
python tools/visualize_viser.py \
  --scene_path ../datasets/dataset_demo/0618_capture/0618livingroom1 \
  --port 8080 --stride 2 --mesh_level 1 --scene_mesh simple
# 浏览器打开 http://localhost:8080
```

**视觉检查清单：**

| 检查项 | 合格表现 | 常见问题 |
|--------|----------|---------|
| 人体与场景对齐 | 人体站在地板上，脚不漂浮 | 漂浮：Step 14 优化未收敛 |
| 人体运动轨迹 | 运动连续，无瞬移 | 瞬移：Step 7 SMPL 初始化失败 |
| 人体形态 | 躯干/四肢比例正常 | 变形：betas 异常 |
| 场景网格完整性 | 墙/地板区域有点覆盖 | 空洞：COLMAP 重建质量差 |
| 双视角一致性 | v1/v2 的人体轨迹在同一空间 | 分离：Step 12 相机对齐失败 |
| 肢体不穿透 | 手脚不插入地板/墙壁 | 穿透：缺少接触约束（Step 16） |

#### 备选：视频渲染

```bash
python tools/visualize.py {seq_path} \
  --input --optim_cam --downscale 2 --mode overwrite
# 对比输入视频与 overlay 渲染，看人体投影是否与实际位置吻合
```

---

## 四、如何判断主流程正确输出了数据

### 4.1 快速检查脚本

```bash
# 使用内置检查命令
cd /home/wubin/EmbodMocap_dev/embod_mocap
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --steps 1-15 --check --config config_fast.yaml
```

该命令只检查文件是否存在，不验证内容质量。

### 4.2 逐步骤验证脚本

```python
#!/usr/bin/env python3
"""主流程输出完整性检查脚本"""
import numpy as np
import os, json

SEQ = "/home/wubin/EmbodMocap_dev/datasets/dataset_demo/0618_capture/0618livingroom1/seq0"

def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    return cond

print("=== Step 1: transforms.json ===")
tf_path = f"{SEQ}/transforms.json"
if os.path.exists(tf_path):
    tf = json.load(open(tf_path))
    check("frames 非空", len(tf.get("frames", [])) > 0,
          f"{len(tf.get('frames', []))} frames")
else:
    check("transforms.json 存在", False)

print("\n=== Step 7: smpl_params.npz ===")
for v in ["v1", "v2"]:
    p = f"{SEQ}/{v}/smpl_params.npz"
    if os.path.exists(p):
        d = np.load(p, allow_pickle=True)
        T = d['body_pose'].shape[0]
        nonzero = not np.allclose(d['body_pose'], 0)
        check(f"{v} body_pose 非零", nonzero, f"T={T}")
    else:
        check(f"{v}/smpl_params.npz 存在", False)

print("\n=== Step 10: masks_keyframe ===")
for v in ["v1", "v2"]:
    mask_dir = f"{SEQ}/{v}/masks_keyframe"
    n = len(os.listdir(mask_dir)) if os.path.isdir(mask_dir) else 0
    check(f"{v} masks_keyframe 有文件", n > 0, f"{n} files")

print("\n=== Step 11: vggt_tracks.npz ===")
vp = f"{SEQ}/vggt_tracks.npz"
if os.path.exists(vp):
    vd = np.load(vp)
    n_tracks = vd['track_v1'].shape[0] if 'track_v1' in vd else 0
    check("vggt_tracks 轨迹数 > 0", n_tracks > 0, f"{n_tracks} tracks")
else:
    check("vggt_tracks.npz 存在", False)

print("\n=== Step 14: cameras.npz ===")
for v in ["v1", "v2"]:
    p = f"{SEQ}/{v}/cameras.npz"
    if os.path.exists(p):
        d = np.load(p)
        det = np.linalg.det(d['R'])
        valid = np.all(np.abs(det - 1) < 0.05)
        check(f"{v} 旋转矩阵合法（det≈1）", valid,
              f"det mean={det.mean():.4f}")
    else:
        check(f"{v}/cameras.npz 存在", False)

print("\n=== Step 15: optim_params.npz ===")
op = f"{SEQ}/optim_params.npz"
if os.path.exists(op):
    od = np.load(op, allow_pickle=True)
    keys = list(od.keys())
    expected = ['global_orient', 'body_pose', 'betas', 'transl',
                'keypoints3d', 'optim_total_loss']
    for k in expected:
        check(f"字段 '{k}' 存在", k in keys)
    if 'optim_total_loss' in od:
        loss = float(od['optim_total_loss'])
        check("优化损失合理（< 100）", loss < 100, f"loss={loss:.2f}")
    if 'transl' in od:
        check("transl 不全为零", not np.allclose(od['transl'], 0))
    if 'betas' in od:
        beta_max = float(np.abs(od['betas']).max())
        check("betas 在合理范围（< 5）", beta_max < 5, f"max={beta_max:.2f}")
else:
    check("optim_params.npz 存在", False)
```

### 4.3 最终成功判定标准

满足以下全部条件，可判定主流程**正确输出**：

| # | 条件 | 检查方法 |
|---|------|---------|
| 1 | `optim_params.npz` 存在且含所有必需字段 | 上方脚本 |
| 2 | `optim_total_loss < 100` | 上方脚本 |
| 3 | `body_pose` 不全为零，T 与帧数一致 | 上方脚本 |
| 4 | `transl` 不全为零（人体有位移） | 上方脚本 |
| 5 | `betas` 绝对值 < 5（体型合理） | 上方脚本 |
| 6 | v1/v2 `cameras.npz` 旋转矩阵行列式 ≈ 1 | 上方脚本 |
| 7 | Viser 可视化中人体站在地板上（不漂浮） | 目视检查 |
| 8 | Viser 可视化中人体运动连续（无瞬移） | 目视检查 |

> **注**：定量指标通过但目视效果差时，优先相信目视结果——损失值合理不代表重建语义正确。反之，目视大体合理但损失略高，可能是权重设置问题而非重建失败。

---

## 五、常见整体性失败模式

| 失败表现 | 最可能的根因 | 定位方法 |
|----------|-------------|---------|
| optim_params.npz 存在但人体漂在空中 | Step 14 相机优化未收敛 | 检查 cameras.npz 的 T 量级；重跑 Step 14 |
| 双视角人体错位（v1/v2 人体在不同位置） | Step 12 相机对齐失败 | 检查 cameras_sai_transformed.npz；重跑 Step 8/12 |
| 人体形态扭曲（关节角度畸形） | Step 7 ViTPose 关键点检测失败 | 检查 v1/smpl_params.npz；核查 ViTPose 是否正常 |
| 场景网格为空或仅有极少点 | COLMAP 无 CUDA 匹配失败 | 检查 COLMAP 日志；考虑增加输入图像质量 |
| Step 10 后 masks_keyframe 为空 | xformers 未安装或 lingbot_depth checkpoint 缺失 | `python -c "import xformers"` 验证；检查 checkpoint |
| Step 11 轨迹为空 | Step 10 未完成 | 先确保 masks_keyframe/ 非空 |
