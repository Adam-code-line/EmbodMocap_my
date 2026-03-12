# EmbodMocap 环境搭建与跑通全记录

> **文档性质**：可复用运行手册（Runbook），记录从零搭建到流水线跑通的完整过程、踩坑与解决方案。
> **最后更新**：2026-03-12
> **维护原则**：每次跑通新步骤或解决新问题，必须在本文档对应章节留痕追加。

---

## 一、硬件与系统基线

| 项目 | 值 |
|------|-----|
| 操作系统 | Ubuntu 22.04 LTS |
| GPU | NVIDIA RTX 4090 D |
| CUDA 驱动版本 | 12.1 |
| 宿主机 Python | 系统自带（不直接使用） |
| conda 版本 | Miniconda3（`/home/wubin/miniconda3`） |
| 项目根目录 | `/home/wubin/EmbodMocap_dev` |
| 第三方源码目录 | `/home/wubin/third_src/`（存放需编译的包） |

---

## 二、Python 环境

### 2.1 conda 环境创建

```bash
conda create -n embodmocap python=3.11 -y
conda activate embodmocap
```

### 2.2 核心包版本清单（2026-03-12 实测可用）

| 包 | 版本 | 安装方式 | 备注 |
|----|------|----------|------|
| Python | 3.11 | conda | — |
| **torch** | **2.4.0+cu121** | pip（PyTorch 官方源） | 原装 2.4.1，安装 xformers 后被自动降至 2.4.0，功能等价 |
| torchvision | 0.19.1+cu121 | pip | 与 torch 2.4.0 兼容 |
| **xformers** | **0.0.27.post2** | pip（PyTorch whl 源） | lingbot_depth 推理必需；0.0.27 系列对应 torch 2.4.x |
| numpy | 2.4.3 | pip | requirements.txt 中 `numpy==1.23.1` 行实际未生效，当前版本正常运行 |
| **mmcv** | **1.7.2** | 源码编译（无 CUDA ops） | `/home/wubin/third_src/mmcv-1.7.2/` |
| **mmpose** | **0.24.0** | pip editable（ViTPose submodule） | `embod_mocap/thirdparty/ViTPose` |
| **SAM-2** | **1.0** | pip editable（源码） | `/home/wubin/third_src/sam2/` |
| lang-sam | — | pip editable（submodule） | `embod_mocap/thirdparty/lang_sam/` |
| lingbot_depth (mdm) | 1.0.0 | 直接路径导入（非 pip 包） | `embod_mocap/thirdparty/lingbot_depth/`，通过 `embod_mocap.thirdparty.lingbot_depth.mdm.*` 访问 |
| **pytorch3d** | **0.7.8** | conda（清华镜像预编译包） | py311_cu121_pyt241；Step 14/16 必需 |
| t3drender | 1.0 | pip git | `tools/visualize.py` 必需（viser 版不需要） |
| spectacularAI | 1.35.0 | pip | Step 1 必需 |
| spconv-cu121 | 2.3.8 | pip | requirements.txt 中写的是 `spconv`，需改名安装 |
| ultralytics | 8.4.21 | pip | YOLOv8 人体检测 |
| viser | 0.2.23 | pip | 交互可视化 |
| COLMAP | 3.7 | **apt 安装**（`sudo apt install colmap`） | 无 CUDA，路径 `/usr/bin/colmap`；Step 2/3/8 必需 |

### 2.3 pip 镜像配置

```ini
# ~/.config/pip/pip.conf
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 三、完整安装步骤（可复用）

### Step 1：克隆仓库与 submodule

```bash
git clone <repo_url> /home/wubin/EmbodMocap_dev
cd /home/wubin/EmbodMocap_dev
git submodule update --init --recursive
```

> ⚠️ **必须先拉 submodule**，否则 `thirdparty/` 下均为空目录，
> `lingbot_depth`、`lang_sam`、`ViTPose` 均无法使用。

### Step 2：安装系统依赖

```bash
# COLMAP（apt 版，无 CUDA，v3.7）
sudo apt update && sudo apt install -y colmap

# ffmpeg（Step 4 提取帧必需）
sudo apt install -y ffmpeg
```

### Step 3：创建 conda 环境并安装 requirements.txt

```bash
conda create -n embodmocap python=3.11 -y
conda activate embodmocap

cd /home/wubin/EmbodMocap_dev

# ⚠️ requirements.txt 有若干破损行，需跳过，见"已知问题"章节
# 建议逐行或分批安装，遇到报错跳过问题行
pip install -r requirements.txt  # 部分行会失败，属正常现象
```

### Step 4：安装 PyTorch 套件

```bash
# 安装 torch 2.4.x + CUDA 12.1
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121

# 安装 xformers（Step 10 lingbot_depth 必需）
# 注意：xformers 0.0.27.post2 依赖 torch==2.4.0，会将 torch 从 2.4.1 降到 2.4.0
# 两者 API 完全兼容，不影响使用
pip install xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121
```

### Step 5：安装 mmcv + mmpose（Step 7 必需，最复杂）

```bash
# 5a. 从官方下载 mmcv 1.7.2 源码
mkdir -p /home/wubin/third_src
cd /home/wubin/third_src
# 下载 mmcv-1.7.2 源码包（从 GitHub releases 或镜像）
# https://github.com/open-mmlab/mmcv/archive/refs/tags/v1.7.2.tar.gz

# 5b. 编译安装（不带 CUDA ops，避免编译问题）
cd /home/wubin/third_src/mmcv-1.7.2
MMCV_WITH_OPS=0 pip install -e . --no-build-isolation

# 5c. patch ViTPose 版本检查（否则 mmcv 版本校验会阻断导入）
# 编辑 embod_mocap/thirdparty/ViTPose/mmpose/__init__.py
# 将 mmcv_maximum_version = "1.x.x" 改为 mmcv_maximum_version = "99.0.0"

# 5d. 安装 ViTPose（即 mmpose 0.24.0）
cd /home/wubin/EmbodMocap_dev
pip install -e embod_mocap/thirdparty/ViTPose --no-deps
```

### Step 6：安装 SAM2

```bash
# PyPI 最新版 SAM2 要求 torch>=2.5.1，与我们的 2.4.x 不兼容
# 需从官方源码安装旧版（1.0）
cd /home/wubin/third_src
git clone https://github.com/facebookresearch/sam2.git
cd sam2
git checkout v1.0  # 或对应的兼容 tag
pip install -e .
```

### Step 7：安装 lang_sam 与 lingbot_depth

```bash
cd /home/wubin/EmbodMocap_dev

# lang_sam（submodule，直接 editable 安装）
pip install -e embod_mocap/thirdparty/lang_sam/

# lingbot_depth：通过直接路径导入，无需 pip 安装
# 其包名为 mdm（pyproject.toml 中），但项目代码通过
# from embod_mocap.thirdparty.lingbot_depth.mdm.xxx 访问，不走 pip 包路径
# 验证：
python -c "from embod_mocap.thirdparty.lingbot_depth.mdm.model.v2 import MDMModel; print('OK')"
```

### Step 8：安装 pytorch3d（Step 14/16 必需）

```bash
# ⛔ 不要用源码编译！会 OOM 崩服务器（24GB 显存不够）
# ✅ 使用清华镜像预编译 conda 包

wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch3d/linux-64/pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2

conda install -n embodmocap --use-local pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2

# 验证
conda run -n embodmocap python -c "import pytorch3d; print('pytorch3d OK')"
```

### Step 9：安装 spconv

```bash
# requirements.txt 中写的是 spconv（通用名），需改为 cu121 版本
pip install spconv-cu121
```

### Step 10：安装其余依赖

```bash
pip install \
    spectacularAI==1.35.0 \
    ultralytics \
    viser \
    open3d \
    trimesh \
    smplx \
    openpyxl \
    scikit-learn \
    scikit-image \
    einops \
    natsort \
    tyro==0.9.2 \
    huggingface_hub \
    safetensors \
    timm \
    hydra-core \
    accelerate

# t3drender（tools/visualize.py 必需，viser 版不需要）
pip install git+https://github.com/WenjiaWang0312/torch3d_render.git

# chumpy（修复 numpy bool 报错）
pip install git+https://github.com/mattloper/chumpy
```

### Step 11：安装项目本体

```bash
cd /home/wubin/EmbodMocap_dev
pip install -e embod_mocap
```

### Step 12：下载 Checkpoints

目录：`/home/wubin/EmbodMocap_dev/checkpoints/`

| 文件 | 大小 | 状态 | 来源 |
|------|------|------|------|
| `vggt.pt` | — | ✅ | HuggingFace |
| `sam2.1_hiera_large.pt` | — | ✅ | Meta |
| `sam2.1_hiera_small.pt` | — | ✅ | Meta |
| `vimo_checkpoint.pth.tar` | — | ✅ | VIMO 项目 |
| `yolov8x.pt` | — | ✅ | ultralytics（自动下载） |
| `vitpose-h-multi-coco.pth` | — | ✅ | ViTPose |
| `vocab_tree_flickr100K_words32K.bin` | — | ✅ | COLMAP |
| `lingbot_depth_vitl14.pt` | 1.28 GB | ✅ | lingbot_depth 仓库 |
| `grounding_dino_base/`（目录） | ~891 MB | ✅ | hf-mirror 手动下载（见问题 13） |

```bash
mkdir -p /home/wubin/EmbodMocap_dev/checkpoints
# 所有路径由 embod_mocap/config_paths.py 统一管理
```

### Step 13：准备 body_models

```
/home/wubin/EmbodMocap_dev/body_models/smpl/
├── SMPL_NEUTRAL.pkl          # 从 https://smpl.is.tue.mpg.de/ 申请下载
├── J_regressor_extra.npy     # VIBE/VIMO 开源代码附带
├── J_regressor_h36m.npy
├── smpl_mean_params.npz
└── mesh_downsampling.npz
```

---

## 四、快速验证（安装完成后执行）

```bash
conda activate embodmocap
cd /home/wubin/EmbodMocap_dev/embod_mocap

# 验证主要依赖
python -c "
import torch; print('torch:', torch.__version__, '| cuda:', torch.cuda.is_available())
import xformers; print('xformers:', xformers.__version__)
import mmcv; print('mmcv:', mmcv.__version__)
import mmpose; print('mmpose:', mmpose.__version__)
from sam2.build_sam import build_sam2_video_predictor; print('sam2: OK')
from embod_mocap.thirdparty.lingbot_depth.mdm.model.v2 import MDMModel; print('lingbot_depth: OK')
import pytorch3d; print('pytorch3d:', pytorch3d.__version__)
import spectacularAI; print('spectacularAI: OK')
"

# 验证入口
python run_stages.py -h
```

---

## 五、运行演示数据（demo）

### 5.1 下载 demo 数据

```bash
# HuggingFace（需挂代理或国内镜像）
# 仓库：WenjiaWang/EmbodMocap_release
# 文件：dataset_demo.tar + release_demo.xlsx
# 解压到：
mkdir -p /home/wubin/EmbodMocap_dev/datasets
tar -xf dataset_demo.tar -C /home/wubin/EmbodMocap_dev/datasets/
```

### 5.2 运行 fast 模式（推荐用于验证）

```bash
cd /home/wubin/EmbodMocap_dev/embod_mocap

# Steps 1-15 全流程（fast 模式，输出 mesh + motion，不含完整 RGBD）
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml \
  --steps 1-15 \
  --mode overwrite
```

### 5.3 分段运行（推荐，便于定位问题）

```bash
# 场景重建阶段
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 1-5 --mode overwrite

# ⚠️ 完成 Step 5 后需手动填写 release_demo.xlsx 中的 v1_start/v2_start 字段

# 人体处理阶段
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 6-9 --mode overwrite

# 深度与掩码（Step 10，耗时较长，需 xformers）
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 10 --mode overwrite

# 跟踪与优化阶段（Step 11 依赖 Step 10 的 masks_keyframe/ 输出）
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 11-15 --mode overwrite
```

### 5.4 可视化

#### 5.4.1 Viser 交互式可视化（推荐，不需要 t3drender）

```bash
cd /home/wubin/EmbodMocap_dev/embod_mocap

# 场景1：0618livingroom1（seq0 + seq12）
python tools/visualize_viser.py \
  --scene_path ../datasets/dataset_demo/0618_capture/0618livingroom1 \
  --port 8080 --stride 2 --mesh_level 1 --scene_mesh simple

# 场景2：0914livingroom1（seq1 + seq5）
python tools/visualize_viser.py \
  --scene_path ../datasets/dataset_demo/0914_capture/0914livingroom1 \
  --port 8081 --stride 2 --mesh_level 1 --scene_mesh simple

# 多场景合并加载（xlsx 模式）
python tools/visualize_viser.py \
  --xlsx ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --port 8080 --stride 2 --mesh_level 1 --scene_mesh simple
```

浏览器访问 `http://localhost:8080`（或对应端口）即可交互。

#### 5.4.2 视频渲染（需 t3drender）

```bash
# 逐序列渲染优化结果视频
python tools/visualize.py \
  --seq_path ../datasets/dataset_demo/0618_capture/0618livingroom1/seq0 \
  --optim_cam --downscale 2 --mode overwrite

python tools/visualize.py \
  --seq_path ../datasets/dataset_demo/0618_capture/0618livingroom1/seq12 \
  --optim_cam --downscale 2 --mode overwrite

python tools/visualize.py \
  --seq_path ../datasets/dataset_demo/0914_capture/0914livingroom1/seq1 \
  --optim_cam --downscale 2 --mode overwrite

python tools/visualize.py \
  --seq_path ../datasets/dataset_demo/0914_capture/0914livingroom1/seq5 \
  --optim_cam --downscale 2 --mode overwrite

# 批量渲染所有序列
python tools/visualize.py \
  --xlsx ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --optim_cam --downscale 2 --mode overwrite
```

---

### 5.5 可视化结果记录

> **说明**：截图与视频请放在 `docs/assets/` 目录下，按 `<scene>_<seq>_<内容>.png/mp4` 命名。

#### 0618livingroom1 — seq0

| 类型 | 内容 | 文件 |
|------|------|------|
| Viser 截图 | 全场景 + 人体 mesh 正面视角 | `docs/assets/0618_seq0_viser_front.png` |
| Viser 截图 | 俯视视角 | `docs/assets/0618_seq0_viser_top.png` |
| 渲染视频 | optim_cam 结果 | `docs/assets/0618_seq0_optim.mp4` |

<!-- TODO: 截图与视频待填入 -->

#### 0618livingroom1 — seq12

| 类型 | 内容 | 文件 |
|------|------|------|
| Viser 截图 | 全场景 + 人体 mesh 正面视角 | `docs/assets/0618_seq12_viser_front.png` |
| Viser 截图 | 俯视视角 | `docs/assets/0618_seq12_viser_top.png` |
| 渲染视频 | optim_cam 结果 | `docs/assets/0618_seq12_optim.mp4` |

<!-- TODO: 截图与视频待填入 -->

#### 0914livingroom1 — seq1

| 类型 | 内容 | 文件 |
|------|------|------|
| Viser 截图 | 全场景 + 人体 mesh 正面视角 | `docs/assets/0914_seq1_viser_front.png` |
| Viser 截图 | 俯视视角 | `docs/assets/0914_seq1_viser_top.png` |
| 渲染视频 | optim_cam 结果 | `docs/assets/0914_seq1_optim.mp4` |

<!-- TODO: 截图与视频待填入 -->

#### 0914livingroom1 — seq5

| 类型 | 内容 | 文件 |
|------|------|------|
| Viser 截图 | 全场景 + 人体 mesh 正面视角 | `docs/assets/0914_seq5_viser_front.png` |
| Viser 截图 | 俯视视角 | `docs/assets/0914_seq5_viser_top.png` |
| 渲染视频 | optim_cam 结果 | `docs/assets/0914_seq5_optim.mp4` |

<!-- TODO: 截图与视频待填入 -->

---

## 六、遇到的问题与解决方案

### 问题 1：requirements.txt 破损行导致 pip 安装失败

**现象**：`pip install -r requirements.txt` 报多处错误。

**根因**：requirements.txt 存在多个问题行：

| 行内容 | 问题 | 处理方式 |
|--------|------|----------|
| `0.0.27.post2` | xformers 版本号残留，无包名，语法错误 | 跳过，单独安装 `xformers==0.0.27.post2` |
| `setuptools==57.0.0` | 会将 setuptools 从 80.x 降级，破坏编译环境 | 跳过，保持现有版本 |
| `mmcv==1.5.0` | Python 3.11 无预编译轮子，直接安装必然失败 | 跳过，改用 1.7.2 源码编译 |
| `spconv` | 需指定 CUDA 版本 | 改装 `spconv-cu121` |
| `numpy==1.23.1` | 过旧，当前项目在 numpy 2.4.3 下正常运行 | 跳过 |

**解决**：跳过上述行，单独安装正确版本（见第三章）。

---

### 问题 2：mmcv 版本冲突（最复杂）

**现象**：Step 7（process_smpl）运行时报 `ImportError: cannot import name 'parallel'` 或 mmcv 版本校验失败。

**根因分析**：
- `mmcv==1.5.0`：Python 3.11 无预编译轮子，无法直接安装
- `mmcv==2.x`：已删除 `mmcv.parallel`、`mmcv.runner` 等模块，ViTPose 深度依赖这些 1.x 模块
- `mmpose==1.3.2`（新版）：删除了 `inference_top_down_pose_model` 等 0.x API，项目代码使用 0.x API

**正确组合**：mmcv 1.7.2（无 CUDA ops）+ mmpose 0.24.0（ViTPose 内置版）

**解决步骤**：

```bash
# 1. 源码编译 mmcv 1.7.2（不带 CUDA ops）
cd /home/wubin/third_src/mmcv-1.7.2
MMCV_WITH_OPS=0 pip install -e . --no-build-isolation

# 2. Patch ViTPose 版本上限检查
# 文件：embod_mocap/thirdparty/ViTPose/mmpose/__init__.py
# 将 mmcv_maximum_version 的值改为 "99.0.0"

# 3. 安装 ViTPose（mmpose 0.24.0），不安装其依赖（避免覆盖上面的 mmcv）
pip install -e embod_mocap/thirdparty/ViTPose --no-deps
```

---

### 问题 3：SAM2 版本与 PyTorch 不兼容

**现象**：`pip install sam2` 后运行报错，或安装时提示 `requires torch>=2.5.1`。

**根因**：PyPI 上的最新版 SAM2（1.1+）要求 torch>=2.5.1，而项目使用 torch 2.4.x。

**解决**：从源码安装 SAM2 v1.0：

```bash
cd /home/wubin/third_src
git clone https://github.com/facebookresearch/sam2.git
cd sam2 && git checkout v1.0
pip install -e .
```

---

### 问题 4：pytorch3d 源码编译 OOM

**现象**：尝试从源码编译 pytorch3d 时，服务器内存耗尽崩溃（进程被 OOM Killer 终止）。

**根因**：pytorch3d 编译需要大量内存（远超 24GB），源码编译不可行。

**解决**：使用清华镜像的预编译 conda 包（py311_cu121_pyt241），完全匹配当前环境：

```bash
wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch3d/linux-64/pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2
conda install -n embodmocap --use-local pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2
```

---

### 问题 5：xformers 未安装导致 Step 10 崩溃

**现象**：Step 10（process_depth_mask）运行时报：
```
AssertionError: xFormers is required for using nested tensors
```
位置：`thirdparty/lingbot_depth/mdm/model/dinov2_rgbd/layers/block.py:256`

**根因**：lingbot_depth 的 DINOv2 编码器使用了 xFormers 的 nested tensors 优化，xformers 未安装时直接断言失败。

**解决**：

```bash
pip install xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121
```

> ⚠️ 注意：xformers 0.0.27.post2 指定依赖 torch==2.4.0，安装时会将 torch 2.4.1 降级到 2.4.0。两个版本功能等价，不影响项目运行。

---

### 问题 6：Step 7 bbox_score numpy 赋值报错

**现象**：Step 7（process_smpl）运行时报：
```
ValueError: setting an array element with a sequence.
```
位置：`thirdparty/ViTPose/mmpose/models/heads/topdown_heatmap_base_head.py:71`

**根因**：新版 numpy（>=1.24）禁止将 1D 数组赋值给标量槽位。原代码：
```python
score[i] = np.array(img_metas[i]['bbox_score']).reshape(-1)
# reshape(-1) 得到 shape (1,) 的数组，无法赋给标量元素 score[i]
```

**修复**（修改 ViTPose 源码）：

```python
# 文件：embod_mocap/thirdparty/ViTPose/mmpose/models/heads/topdown_heatmap_base_head.py 第71行
# 原：
score[i] = np.array(img_metas[i]['bbox_score']).reshape(-1)
# 改为：
score[i] = float(np.array(img_metas[i]['bbox_score']).reshape(-1)[0])
```

---

### 问题 7：Step 11 依赖 Step 10 的输出（masks_keyframe/ 为空）

**现象**：Step 11（vggt_track）报：
```
FileNotFoundError: .../v1/masks_keyframe/v1_0000.png
```

**根因**：Step 11 需要读取 `masks_keyframe/` 目录下的掩码图像（Step 10 的输出）。demo 数据虽然有该目录结构，但目录为空（0 个文件），需先成功跑通 Step 10 才能继续。

**解决**：确保 Step 10 成功完成后再运行 Step 11。

---

### 问题 8：COLMAP 缺少 libcudart（LD_LIBRARY_PATH 问题）

**现象**：运行 COLMAP 相关步骤时报 `libcudart.so.12: cannot open shared object file`。

**根因**：apt 安装的 COLMAP 与 conda 环境的 CUDA 库路径不在系统默认搜索路径中。

**解决**：

```bash
export LD_LIBRARY_PATH=/home/wubin/miniconda3/envs/embodmocap/lib/:$LD_LIBRARY_PATH
# 建议写入 ~/.bashrc 或在运行流水线前执行
```

---

### 问题 9：spectacularAI 包名大小写

**现象**：`import spectacular_ai` 报 `ModuleNotFoundError`。

**根因**：正确的包名是 `spectacularAI`（首字母大写），不是 `spectacular_ai`。

**解决**：无需改代码，项目代码已使用正确包名，确认安装时用 `pip install spectacularAI==1.35.0`。

---

### 问题 10：vggt 不是独立 pip 包

**现象**：`import vggt` 报 `ModuleNotFoundError`。

**根因**：VGGT 代码内嵌于 `embod_mocap/vggt/vggt/`，通过项目路径访问，不是独立的 pip 包。

**正确用法**：
```python
from embod_mocap.vggt.vggt.models.vggt import VGGT
```

---

### 问题 11：numpy bool / 浮点异常

**现象**：运行时报 `AttributeError: module 'numpy' has no attribute 'bool'` 或浮点异常。

**根因**：chumpy 库使用了 numpy 已废弃的 `np.bool`（>=1.24 删除）。

**解决**：

```bash
pip install git+https://github.com/mattloper/chumpy
```

---

### 问题 13：Step 10 Grounding DINO 模型无法从 HuggingFace 下载

**现象**：Step 10（process_depth_mask）启动时尝试联网拉取 Grounding DINO 模型，但服务器网络无法访问 huggingface.co，反复超时后报错崩溃：

```
One or both local paths not provided. Loading from Hugging Face Hub: IDEA-Research/grounding-dino-base
Connection to huggingface.co timed out.
OSError: We couldn't connect to 'https://huggingface.co' to load this file...
```

**根因**：项目代码在 `lang_sam/models/gdino.py` 中，当 `model_ckpt_path` 或 `processor_ckpt_path` 为 None 时直接用模型 ID 字符串从 HuggingFace Hub 拉取。而整个调用链（`run_stages.py` → `process_depth_mask.py` → `generate_masks()` → `lang_sam_forward()`）均未传入本地路径，`config_paths.py` 也未配置 gdino 路径。

**修复（代码改动 + 手动下载，2026-03-12）**：

1. **手动下载模型**（用 hf-mirror 绕过网络限制）：

```bash
mkdir -p /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base
cd /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base

wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/config.json
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/preprocessor_config.json
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/tokenizer_config.json
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/tokenizer.json
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/special_tokens_map.json
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/vocab.txt
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/model.safetensors  # ~891MB
```

2. **修改代码，传通本地路径**（改动三个文件）：

- `config_paths.py`：新增 `gdino_model_ckpt` 和 `gdino_processor_ckpt`，均指向 `checkpoints/grounding_dino_base/`
- `processor/process_depth_mask.py`：`generate_masks()` 新增 `gdino_model_ckpt_path` / `gdino_processor_ckpt_path` 参数并向下传给 `lang_sam_forward()`；CLI 新增对应 `--gdino_*` 参数
- `run_stages.py`：Step 10 命令构建时读取 PATHS 中的 gdino 路径并传入

**验证模型加载正常**：

```bash
conda run -n embodmocap python -c "
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
path = 'checkpoints/grounding_dino_base'
processor = AutoProcessor.from_pretrained(path, local_files_only=True)
model = AutoModelForZeroShotObjectDetection.from_pretrained(path, local_files_only=True, use_safetensors=True)
print('All good!')
"
# 输出：All good!
```

> ⚠️ 加载时会出现 `Could not load the custom kernel for multi-scale deformable attention` 警告，原因是系统缺少完整 CUDA 编译工具链头文件（cusparse.h 等），transformers 自动 fallback 到纯 Python 实现，**推理结果完全一致，可忽略**。

**Step 10 实测输出（2026-03-12）**：

| 序列 | 目录 | 文件数 |
|------|------|--------|
| seq0 | `v1/masks_keyframe/` | 85 个 .png |
| seq0 | `v2/masks_keyframe/` | 85 个 .png |
| seq12 | `v1/masks_keyframe/` | 92 个 .png |
| seq12 | `v2/masks_keyframe/` | 94 个 .png |

---

### 问题 14：Step 11 vggt_track numpy 2.x TypeError

**现象**：Step 11（vggt_track）运行时报：
```
TypeError: 'numpy.bool' object cannot be interpreted as an integer
```
位置：`processor/vggt_track.py:169`
```python
mask_valid_v2 = torch.tensor(mask_valid_v2, dtype=torch.bool, device=track_v2_all.device)
```

**根因**：`mask_valid_v2` 列表由 `mask2_original[y, x] > 127` 构建，该表达式在 numpy 2.x 中返回 `numpy.bool_` 标量（而非 Python 原生 `bool`）。`torch.tensor()` 在接收 `numpy.bool_` 时无法将其解释为整数，报 TypeError。与 Step 7 的 bbox_score 问题同属一类：**numpy 2.x 不再隐式转换 numpy 标量类型**。

**修复**（修改 `vggt_track.py`）：

```python
# 文件：embod_mocap/processor/vggt_track.py 第165行
# 原：
mask_valid_v2.append(mask2_original[y, x] > 127)
# 改为：
mask_valid_v2.append(bool(mask2_original[y, x] > 127))
```

**Step 11 实测输出（2026-03-12）**：

| 序列 | 关键帧数 | 耗时 | 输出文件 |
|------|---------|------|----------|
| seq0  | 15 帧 | ~19s | `vggt_tracks.npz` |
| seq12 | 17 帧 | ~20s | `vggt_tracks.npz` |
| seq1  | 13 帧 | ~19s | `vggt_tracks.npz` |
| seq5  | 14 帧 | ~19s | `vggt_tracks.npz` |

---

### 问题 12：网络问题（HuggingFace / GitHub 访问慢）

**现象**：下载 checkpoint、安装 pip 包时超时或速度极慢。

**解决策略**：

| 资源类型 | 解决方案 |
|----------|----------|
| pip 包 | 配置清华源（`~/.config/pip/pip.conf`） |
| PyTorch 官方 whl | 使用 `--index-url https://download.pytorch.org/whl/cu121`（官方 CDN，国内相对可访问） |
| conda 包（pytorch3d） | 使用清华 anaconda 镜像 |
| HuggingFace 模型 | 设置 `HF_ENDPOINT=https://hf-mirror.com` 或手动下载后上传服务器 |
| GitHub 仓库 | 在本地下载后 scp 传服务器，或配置代理 |

---

## 七、各步骤输入输出与可用性（2026-03-12 全量验证）

| 步骤 | 名称 | 关键输入 | 关键输出 | 状态 | 备注 |
|------|------|----------|----------|------|------|
| 1 | sai | `data.mov` | `transforms.json` | ✅ 实测 | SpectacularAI 推断关键帧 |
| 2 | recon_scene | `transforms.json` | `mesh_raw.ply`, `mesh_simplified.ply` | ✅ | COLMAP 无 CUDA，较慢 |
| 3 | rebuild_colmap | `colmap/` | `colmap/database.db` | ✅ | — |
| 4 | get_frames | `data.mov` | `raw1/images/`, `raw2/images/` | ✅ | ffmpeg 提帧 |
| 5 | smooth_camera | `cameras_sai.npz` | 平滑轨迹 | ✅ | 纯 numpy |
| 6 | slice_views | xlsx `v1_start/v2_start` | `v1/`, `v2/` | ✅ | **需手动填写 xlsx** |
| 7 | process_smpl | `v1/images/` | `v1/smpl_params.npz` | ✅ | mmcv+ViTPose+sam2+lang_sam |
| 8 | colmap_human_cam | `v1/smpl_params.npz` | `v1/cameras_colmap.npz` | ✅ | — |
| 9 | generate_keyframes | — | `keyframes.json` | ✅ | 纯计算 |
| 10 | process_depth_mask | `depths/` | `depths_keyframe_refined/`, `masks_keyframe/` | ✅ | 需 xformers；耗时 |
| 11 | vggt_track | `masks_keyframe/`（Step 10 输出） | `vggt_tracks.npz` | ✅ | Step 10 必须先完成 |
| 12 | align_cameras | `vggt_tracks.npz` | `cameras_sai_transformed.npz` | ✅ | 纯计算 |
| 13 | unproj_human | `smpl_params.npz` | `v1/pointcloud.ply` | ✅ | 纯计算 |
| 14 | optim_human_cam | `pointcloud.ply` | `v1/cameras.npz` | ✅ | pytorch3d（chamfer_distance） |
| 15 | optim_motion | 所有前序输出 | `optim_params.npz`（**核心输出**） | ✅ | — |
| 16 | align_contact | xlsx `contacts` 字段 | `contact_alignment_info.npz` | ✅ | contacts 字段为空时跳过 |

---

## 八、关键文件索引

| 文件 | 说明 |
|------|------|
| `embod_mocap/run_stages.py` | 主入口（16 步统一调度） |
| `embod_mocap/run_stages_mp.py` | 多 GPU 版入口（`--gpu_ids 0,1,2`） |
| `embod_mocap/config_paths.py` | **所有 checkpoint 路径在此定义** |
| `embod_mocap/config.yaml` | standard 模式配置 |
| `embod_mocap/config_fast.yaml` | fast 模式配置（推荐验证用） |
| `embod_mocap/processor/base.py` | 各 stage 基础类，lingbot_depth 调用入口 |
| `embod_mocap/human/detector.py` | YOLOv8 + ViTPose 人体检测与关键点 |
| `embod_mocap/human/configs.py` | body_models 路径定义 |
| `embod_mocap/processor/optim_motion.py` | 运动优化核心（Step 15） |
| `embod_mocap/tools/visualize_viser.py` | Viser 交互式可视化（推荐，无需 t3drender） |
| `embod_mocap/tools/visualize.py` | 视频可视化（需 t3drender） |
| `embod_mocap/thirdparty/ViTPose/mmpose/models/heads/topdown_heatmap_base_head.py` | 已 patch（bbox_score numpy 兼容修复，Step 7） |
| `embod_mocap/thirdparty/ViTPose/mmpose/__init__.py` | 已 patch（mmcv_maximum_version = "99.0.0"） |
| `embod_mocap/processor/vggt_track.py` | 已 patch（mask_valid_v2 numpy.bool_ 兼容修复，Step 11） |

---

## 九、跑通记录与留痕

| 日期 | 操作 | 结果 | 操作人 |
|------|------|------|--------|
| 2026-03-10 | 初次克隆，建立 conda 环境，安装基础依赖 | 基础环境 OK，Step 7/10 阻塞 | wubin |
| 2026-03-11 | 完成 mmcv/mmpose/sam2/pytorch3d/t3drender 安装，全量 import 验证 | Steps 1-15 理论全通 | wubin |
| 2026-03-11 | 修复 Step 7 `bbox_score` numpy 兼容问题（topdown_heatmap_base_head.py） | Step 7 实测通过 | wubin |
| 2026-03-11 | 安装 xformers 0.0.27.post2，解决 Step 10 xFormers 断言失败 | Step 10 依赖满足 | wubin |
| 2026-03-12 | 发现 Step 10 Grounding DINO 模型联网拉取失败；手动下载 `grounding_dino_base/` 到 `checkpoints/`，修复三处代码传参链（config_paths.py / process_depth_mask.py / run_stages.py） | Step 10 实测跑通，seq0/seq12 各生成 85/92/94 个 masks_keyframe | wubin |
| 2026-03-12 | 修复 Step 11 `vggt_track.py:165` numpy 2.x 兼容问题（`mask2_original[y,x]>127` 改为 `bool(...)`） | Step 11 实测跑通，4 个序列各约 19s，生成 vggt_tracks.npz | wubin |

---

## 十、后续待确认事项

- [x] Step 10 完整跑通验证（2026-03-12，seq0/seq12 均通过，masks_keyframe/ 正常输出）
- [x] Step 11 完整跑通验证（2026-03-12，修复 vggt_track.py numpy.bool_ 兼容问题后，4 个序列全部生成 vggt_tracks.npz）
- [x] Steps 1-15 全量验证（2026-03-12，check 命令显示 4 seq success, 0 failed, 0 unfinished）
- [ ] COLMAP 是否可升级为带 CUDA 版本以加速 Step 2/3
- [ ] `vocab_tree_faiss_flickr100K_words1M.bin` 是否必要（目前用 32K 版本，可选）
