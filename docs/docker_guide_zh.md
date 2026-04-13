# EmbodMocap Docker 打包与分发指南

> 编写时间：2026-03-13
> 适用版本：EmbodMocap（CVPR 2026 投稿版），conda 环境 `embodmocap`

---

## 目录

1. [概述与设计决策](#1-概述与设计决策)
2. [需要分发的文件清单](#2-需要分发的文件清单)
3. [构建前准备](#3-构建前准备)
4. [构建镜像](#4-构建镜像)
5. [运行容器](#5-运行容器)
6. [已知问题与解决方案](#6-已知问题与解决方案)
7. [镜像大小估算](#7-镜像大小估算)
8. [FAQ](#8-faq)

---

## 1. 概述与设计决策

### 为什么这个项目打 Docker 比普通项目复杂

| 复杂度来源 | 说明 |
|-----------|------|
| **pytorch3d 只有 conda 包** | 0.7.8 版本没有 PyPI wheel，必须通过 conda 从清华镜像安装，因此 Docker 中需要安装 Miniconda |
| **mmcv 1.7.2 需要源码编译** | Python 3.11 无预编译轮子，必须 `git clone` 后 `MMCV_WITH_OPS=0 pip install -e .` |
| **SAM2 必须用 v1.0 源码** | PyPI 版本要求 torch>=2.5.1，与本项目 torch 2.4.0 不兼容，必须从 GitHub tag `v1.0` 克隆安装 |
| **t3drender 不在公开 PyPI/GitHub** | 第三方渲染库，只有本地源码，需手动 COPY 进镜像 |
| **xformers 强依赖版本** | `0.0.27.post2` 在安装时会将 torch 从 2.4.1 降为 2.4.0（但功能等价），需在 torch 之后安装 |
| **COLMAP 无 CUDA** | apt 版本 3.7 无 GPU 支持，大数据集重建会很慢 |
| **checkpoints 体积巨大** | 总计 ~14GB，不能打包进镜像，必须通过 volume 挂载 |

### 核心设计原则

- **镜像只含代码和依赖，不含模型文件**：checkpoints（14GB）、body_models（239MB）、datasets 均通过 Docker volume 挂载
- **使用 Miniconda 作为 Python 环境**：便于 conda install pytorch3d
- **基础镜像**：`nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04`（CUDA 12.1，与 torch 2.4.0+cu121 匹配）

---

## 2. 需要分发的文件清单

### 2.1 Docker 镜像（代码+依赖，约 15-20GB）

通过 `docker save` / `docker push` 分发，或让接收方自行 `docker build`。

### 2.2 Checkpoints（模型权重，必须分发，约 14GB）

绝大多数 checkpoint 已打包至 `WenjiaWang/EmbodMocap_release` 的 `ckpt_lazypack.tar`（12.8GB）。

| 文件 / 目录 | 大小 | 来源 | 步骤 |
|------------|------|------|------|
| `vggt.pt` | 4.7GB | `ckpt_lazypack.tar` | Step 11 |
| `vimo_checkpoint.pth.tar` | 2.6GB | `ckpt_lazypack.tar` | Step 7/15 |
| `vitpose-h-multi-coco.pth` | 2.4GB | `ckpt_lazypack.tar` | Step 7 |
| `lingbot_depth_vitl14.pt` | 1.28GB | `ckpt_lazypack.tar` | Step 10 |
| `sam2.1_hiera_large.pt` | 857MB | `ckpt_lazypack.tar` | Step 10 |
| `sam2.1_hiera_small.pt` | 176MB | `ckpt_lazypack.tar` | Step 10 |
| `yolov8x.pt` | 131MB | `ckpt_lazypack.tar` | Step 7 |
| `vocab_tree_flickr100K_words32K.bin` | 15MB | `ckpt_lazypack.tar` | Step 3 |
| `vocab_tree_flickr100K_words1M.bin` | — | `ckpt_lazypack.tar` | 可选 |
| `grounding_dino_base/`（目录） | ~891MB | hf-mirror 单独下载 | Step 10 |

**总计：约 14GB**

> `grounding_dino_base/` 不在 lazypack 中，需单独从 `hf-mirror.com/IDEA-Research/grounding-dino-base` 下载（见接收方部署文档 Step 2）。
> 国内服务器无法访问 huggingface.co，所有下载均使用 **https://hf-mirror.com**。

### 2.3 Body Models（SMPL，必须分发，约 239MB）

接收方需将以下文件放到挂载目录的 `body_models/smpl/` 下：

| 文件 | 大小 | 来源 |
|------|------|------|
| `SMPL_NEUTRAL.pkl` | 247MB | HuggingFace: `WenjiaWang/EmbodMocap_release` |
| `J_regressor_extra.npy` | 496KB | HuggingFace: `WenjiaWang/EmbodMocap_release` |
| `J_regressor_h36m.npy` | 937KB | HuggingFace: `WenjiaWang/EmbodMocap_release` |
| `smpl_mean_params.npz` | — | HuggingFace: `WenjiaWang/EmbodMocap_release` |
| `mesh_downsampling.npz` | 1.72MB | HuggingFace: `WenjiaWang/EmbodMocap_release` |

**总计：约 239MB**

### 2.4 分发目录结构示例

接收方需要按以下结构准备挂载目录：

```
embodmocap_data/          ← 总数据目录（挂载根）
├── checkpoints/
│   ├── vggt.pt
│   ├── vimo_checkpoint.pth.tar
│   ├── vitpose-h-multi-coco.pth
│   ├── lingbot_depth_vitl14.pt
│   ├── sam2.1_hiera_large.pt
│   ├── sam2.1_hiera_small.pt
│   ├── yolov8x.pt
│   ├── vocab_tree_flickr100K_words32K.bin
│   └── grounding_dino_base/
│       ├── model.safetensors
│       ├── pytorch_model.bin
│       ├── config.json
│       ├── preprocessor_config.json
│       ├── tokenizer.json
│       ├── tokenizer_config.json
│       ├── special_tokens_map.json
│       └── vocab.txt
├── body_models/
│   └── smpl/
│       ├── SMPL_NEUTRAL.pkl
│       ├── J_regressor_extra.npy
│       ├── J_regressor_h36m.npy
│       ├── smpl_mean_params.npz
│       └── mesh_downsampling.npz
└── datasets/             ← 用户自己的输入数据
```

---

## 3. 构建前准备

### 3.1 确认宿主机环境

| 要求 | 说明 |
|------|------|
| NVIDIA 驱动 ≥ 525 | 支持 CUDA 12.1（docker 内 CUDA 运行时） |
| nvidia-container-toolkit | 已安装并配置（`docker info \| grep nvidia`） |
| Docker ≥ 20.10 | 支持 `deploy.resources.reservations.devices` |
| 磁盘空间 | 构建时 ≥ 40GB 可用（构建缓存 + 最终镜像） |

验证 GPU 可用：
```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

### 3.2 准备 t3drender 源码（vendor 目录）

`t3drender` 不在 PyPI 也不在 Git submodule，必须手动复制到 `vendor/` 目录：

```bash
# 在项目根目录执行
bash scripts/prepare_docker_build.sh
```

执行后确认 `vendor/torch3d_render/setup.py` 存在。

### 3.3 确认 submodules 已初始化

```bash
cd /path/to/EmbodMocap_dev
git submodule update --init --recursive
# 确认以下目录非空：
ls embod_mocap/thirdparty/ViTPose/mmpose/__init__.py
ls embod_mocap/thirdparty/lang_sam/setup.py
ls embod_mocap/thirdparty/lingbot_depth/mdm/
```

---

## 4. 构建镜像

### 4.1 标准构建

```bash
cd /path/to/EmbodMocap_dev

# 方式一：直接 docker build
docker build -t embodmocap:latest . 2>&1 | tee build.log

# 方式二：通过 docker-compose
docker compose build 2>&1 | tee build.log
```

**预计构建时间**：
- 国内服务器（清华源）：约 30-60 分钟（主要耗时在 pytorch3d 下载、mmcv 编译）
- 境外服务器：约 20-40 分钟

### 4.2 分阶段构建（调试时使用）

可以用 `--target` 停在某个阶段（若后续改为 multi-stage Dockerfile 时使用）。

### 4.3 保存镜像供分发

#### 方式一：推送到 ghcr.io（推荐）✅ 已完成

镜像已推送至 `ghcr.io/adam-code-line/embodmocap:cvpr2026`，接收方直接拉取：

```bash
docker pull ghcr.io/adam-code-line/embodmocap:cvpr2026
```

> **注意**：服务器无法访问 Docker Hub，使用 GitHub Container Registry（ghcr.io）代替。
> 推送前需生成 GitHub PAT（`write:packages` 权限），推送后在 GitHub Package 页面设置为 Public。

#### 方式二：导出 tar 包（离线环境）

```bash
# 导出为 tar 文件（约 15-20GB）
docker save embodmocap:latest | gzip > embodmocap_cvpr2026.tar.gz

# 接收方导入
docker load < embodmocap_cvpr2026.tar.gz
```

---

## 5. 运行容器

### 5.1 修改 docker-compose.yml 挂载路径

编辑 `docker-compose.yml`，将 volume 左侧改为接收方的实际路径：

```yaml
volumes:
  - /实际路径/embodmocap_data/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro
  - /实际路径/embodmocap_data/body_models:/workspace/EmbodMocap_dev/body_models:ro
  - /实际路径/embodmocap_data/datasets:/workspace/EmbodMocap_dev/datasets:rw
```

### 5.2 交互式运行（调试）

```bash
docker compose run --rm embodmocap bash
# 或
docker run --rm -it --gpus all \
  -v /path/to/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro \
  -v /path/to/body_models:/workspace/EmbodMocap_dev/body_models:ro \
  -v /path/to/datasets:/workspace/EmbodMocap_dev/datasets:rw \
  embodmocap:latest bash
```

### 5.3 执行流水线

```bash
# 进入容器后
cd /workspace/EmbodMocap_dev/embod_mocap

# 全流程 fast 模式（Steps 1-15）
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 1-15 --mode overwrite

# 分步执行（推荐）
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 1-5 --mode overwrite
# ⚠️ 手动填写 xlsx 的 v1_start/v2_start 后继续
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 6-15 --mode overwrite
```

---

## 6. 已知问题与解决方案

### 问题 1：pytorch3d 安装失败（conda 下载超时）

**现象**：
```
HTTPError: 404 Client Error
```
或下载中断。

**原因**：清华镜像偶发不可用，或网络问题。

**解决方案**：
```dockerfile
# 方式 A：先将 pytorch3d.tar.bz2 放入宿主机，COPY 进镜像
COPY pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2 /tmp/
RUN conda install -y --use-local /tmp/pytorch3d-*.tar.bz2

# 方式 B：用备用 URL
RUN wget -q "https://anaconda.org/pytorch3d/pytorch3d/0.7.8/download/linux-64/pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2" \
        -O /tmp/pytorch3d.tar.bz2
```

### 问题 2：mmcv 编译失败（缺少编译头）

**现象**：
```
error: 'XXX' was not declared in this scope
```

**原因**：Dockerfile 中使用 `-devel` 基础镜像已包含 CUDA 开发头文件，但 `build-essential` 未安装。

**解决方案**：确认 Dockerfile 中 `build-essential cmake ninja-build` 已安装（已包含在当前 Dockerfile）。

### 问题 3：SAM2 安装时 torch 版本冲突

**现象**：
```
ERROR: sam2 0.x requires torch>=2.5.1
```

**原因**：从 PyPI 安装了新版 SAM2（> v1.0）。

**解决方案**：Dockerfile 已使用 `git clone --branch v1.0`，确保分支 tag 正确：
```bash
# 验证
docker run --rm embodmocap:latest python -c "import sam2; print(sam2.__version__)"
# 应输出 1.0
```

### 问题 4：容器内看不到 GPU

**现象**：`nvidia-smi` 无输出，或 `torch.cuda.is_available()` 返回 False。

**原因**：宿主机未安装 `nvidia-container-toolkit` 或未重启 Docker daemon。

**解决方案**：
```bash
# 宿主机安装
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list \
    | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 问题 5：COLMAP 运行时 `libcudart.so not found`

**现象**：
```
error while loading shared libraries: libcudart.so.12: cannot open shared object file
```

**原因**：apt 安装的 COLMAP 尝试加载 CUDA 动态库但路径不对。

**解决方案**：Dockerfile 已设置 `ENV LD_LIBRARY_PATH="/opt/conda/lib:..."` ，确认容器内：
```bash
echo $LD_LIBRARY_PATH  # 应包含 /opt/conda/lib
```

### 问题 6：Step 10 Grounding DINO 联网失败

**现象**：
```
ConnectionError: Couldn't connect to 'https://huggingface.co/IDEA-Research/grounding-dino-base'
```

**原因**：容器内网络无法访问 huggingface.co。

**解决方案**：`checkpoints/grounding_dino_base/` 已通过 volume 挂载，代码层面已修复本地路径传参（`config_paths.py` + `process_depth_mask.py`），无需在线访问。

**验证**：
```bash
ls /workspace/EmbodMocap_dev/checkpoints/grounding_dino_base/model.safetensors
# 文件存在即可
```

### 问题 7：xformers 安装后 torch 降级

**现象**：
```
pip install xformers 时提示 torch 从 2.4.1 降到 2.4.0
```

**这是预期行为**，2.4.0 与 2.4.1 功能等价，不影响项目。Dockerfile 直接安装 torch==2.4.0，避免触发降级。

### 问题 8：mmpose 版本检查报错

**现象**：
```
AssertionError: MMCV==1.7.2 is used but incompatible...
```

**原因**：mmpose 的 `__init__.py` 有 mmcv 版本上限检查。

**解决方案**：Dockerfile 已包含 sed patch：
```dockerfile
RUN sed -i "s/mmcv_maximum_version = .*/mmcv_maximum_version = '99.0.0'/" \
        .../mmpose/__init__.py
```

### 问题 9：MultiScaleDeformableAttention 警告

**现象**：
```
UserWarning: Could not load MultiScaleDeformableAttention kernel
```

**这是警告，不是错误**，可以安全忽略。缺少 CUDA 编译头文件，自动 fallback 到纯 Python 实现，推理结果不受影响。

### 问题 10：镜像构建中 chumpy 安装失败

**现象**：
```
ModuleNotFoundError: No module named 'numpy.core.numeric'
```
（这是运行时错误，不是构建错误）

**原因**：PyPI 上的原版 chumpy 与 numpy>=1.24 不兼容。

**解决方案**：Dockerfile 已使用 `git+https://github.com/mattloper/chumpy`（已修复版本）。

---

## 7. 镜像大小估算

| 层 | 大小估算 |
|----|---------|
| Base: nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 | ~5.5GB |
| Miniconda + Python 3.11 | ~0.5GB |
| PyTorch 2.4.0+cu121 + torchvision | ~3.0GB |
| xformers 0.0.27.post2 | ~0.3GB |
| pytorch3d 0.7.8 | ~0.4GB |
| mmcv 1.7.2 + mmpose + mmdet/mmengine | ~0.8GB |
| SAM2 v1.0 源码 + 其他 pip 包 | ~1.5GB |
| t3drender + 项目代码 + submodules | ~0.3GB |
| spconv-cu121 等其他依赖 | ~1.0GB |
| **总计（压缩后）** | **约 13-15GB** |

**不含checkpoints（14GB）和 body_models（239MB）**，这些通过 volume 挂载。

---

## 8. FAQ

**Q: 接收方没有 GPU 能运行吗？**
A: 不能。本项目 Step 10（DINOv2 + xformers）、Step 11（VGGT）、Step 7（ViTPose）等都强依赖 GPU。

**Q: 能支持多 GPU 吗？**
A: 可以。使用 `run_stages_mp.py` 替代 `run_stages.py`：
```bash
python run_stages_mp.py seq_info.xlsx --data_root /path --config config.yaml \
  --steps 1-15 --mode overwrite --gpu_ids 0,1,2
```

**Q: CUDA 驱动版本有要求吗？**
A: 宿主机 NVIDIA 驱动需要 ≥ **525.x**（CUDA 12.1 的最低驱动要求）。查看：`nvidia-smi | grep Driver`

**Q: 为什么不用 conda environment.yml 而是 Dockerfile？**
A: Docker 可以确保系统级依赖（COLMAP、系统库）和 Python 环境的完整可复现性，适合跨机器分发。

**Q: 如何验证镜像环境正确？**
```bash
docker run --rm --gpus all embodmocap:latest python -c "
import torch, xformers, pytorch3d, sam2, mmpose, mmcv
import spectacularai
print('torch:', torch.__version__, '| cuda:', torch.cuda.is_available())
print('xformers:', xformers.__version__)
print('pytorch3d:', pytorch3d.__version__)
print('mmcv:', mmcv.__version__)
print('mmpose:', mmpose.__version__)
print('spectacularAI:', spectacularai.__version__)
"
```
期望输出：
```
torch: 2.4.0+cu121 | cuda: True
xformers: 0.0.27.post2
pytorch3d: 0.7.8
mmcv: 1.7.2
mmpose: 0.24.0
spectacularAI: 1.35.0
```
