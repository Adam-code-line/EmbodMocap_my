# EmbodMocap Docker 分发与部署指南

> 适用版本：EmbodMocap（CVPR 2026），镜像 `embodmocap:latest`（构建于 2026-03-13）
> 本文覆盖两部分：**①镜像发布者：如何上传镜像** + **②使用者：从零到跑通完整流程**

---

## 目录

- [Part 1：发布者——上传镜像](#part-1发布者上传镜像)
  - [方式 A：推送到阿里云容器镜像服务（ACR）](#方式-a推送到阿里云容器镜像服务acr)
  - [方式 B：导出 tar 包通过文件传输分发](#方式-b导出-tar-包通过文件传输分发)
  - [上传 Checkpoints 到 HuggingFace](#上传-checkpoints-到-huggingface)
- [Part 2：使用者——完整部署流程](#part-2使用者完整部署流程)
  - [Step 0：确认宿主机环境](#step-0确认宿主机环境)
  - [Step 1：获取 Docker 镜像](#step-1获取-docker-镜像)
  - [Step 2：准备 Checkpoints（模型权重）](#step-2准备-checkpoints模型权重)
  - [Step 3：准备 Body Models（SMPL）](#step-3准备-body-modelssmpl)
  - [Step 4：准备输入数据](#step-4准备输入数据)
  - [Step 5：准备目录结构与配置](#step-5准备目录结构与配置)
  - [Step 6：验证环境](#step-6验证环境)
  - [Step 7：运行 Demo](#step-7运行-demo)
  - [Step 8：处理自定义数据](#step-8处理自定义数据)
  - [Step 9：可视化结果](#step-9可视化结果)
- [常见问题](#常见问题)

---

## Part 1：发布者——上传镜像

### 方式 A：推送到 GitHub Container Registry（ghcr.io）✅ 已完成

镜像已推送至：`ghcr.io/adam-code-line/embodmocap:cvpr2026`

接收方直接 `docker pull` 即可，无需账号。

> **注意**：服务器无法访问 Docker Hub，ghcr.io 是可用的免费公开 Registry。

#### 如需重新推送（更新镜像时使用）

```bash
# 1. 生成 GitHub Personal Access Token（勾选 write:packages 权限）
#    https://github.com/settings/tokens

# 2. 登录 ghcr.io
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u adam-code-line --password-stdin

# 3. 打标签
docker tag embodmocap:latest ghcr.io/adam-code-line/embodmocap:cvpr2026

# 4. 推送（挂后台）
nohup docker push ghcr.io/adam-code-line/embodmocap:cvpr2026 > push.log 2>&1 &
tail -f push.log
```

#### 设置镜像为公开（首次推送后操作一次）

打开 `https://github.com/Adam-code-line/EmbodMocap_my/pkgs/container/embodmocap`
→ 右侧 **Package settings** → 最下方 **Change visibility** → 选 **Public**

---

### 方式 B：导出 tar 包通过文件传输分发

适用于内网环境或无法访问公网 Registry 的场景。

#### 1. 导出镜像

```bash
# 压缩导出，约 13GB → 压缩后约 11GB，需要约 30 分钟
docker save embodmocap:latest | gzip > embodmocap_cvpr2026.tar.gz

# 计算校验码（方便接收方验证完整性）
sha256sum embodmocap_cvpr2026.tar.gz > embodmocap_cvpr2026.tar.gz.sha256
```

#### 2. 传输文件

```bash
# 方式一：rsync 到目标服务器
rsync -avh --progress embodmocap_cvpr2026.tar.gz user@target-server:/path/to/

# 方式二：通过网盘（坚果云、百度网盘等）上传 tar.gz 共享链接

# 方式三：NFS/SMB 共享目录直接复制
```

#### 3. 接收方导入镜像

```bash
# 验证校验码
sha256sum -c embodmocap_cvpr2026.tar.gz.sha256

# 导入镜像（约 5-10 分钟）
docker load < embodmocap_cvpr2026.tar.gz

# 确认镜像已加载
docker image ls embodmocap
```

---

### 上传 Checkpoints 到 HuggingFace

镜像本身不含模型权重，需单独分发 Checkpoints。以下文件需上传到 HuggingFace：

| 文件 | 大小 | 说明 |
|------|------|------|
| `vimo_checkpoint.pth.tar` | 2.6GB | VIMO 运动估计模型 |
| `lingbot_depth_vitl14.pt` | 1.28GB | 深度估计模型（内部模型） |

> **注意**：以下文件有官方公开来源，接收方自行下载，**无需你上传**：
> - `vggt.pt` ← HuggingFace `facebook/vggt`
> - `vitpose-h-multi-coco.pth` ← ViTPose 官方
> - `sam2.1_hiera_large.pt` ← HuggingFace `facebook/sam2.1-hiera-large`
> - `sam2.1_hiera_small.pt` ← HuggingFace `facebook/sam2.1-hiera-small`
> - `yolov8x.pt` ← Ultralytics 自动下载
> - `grounding_dino_base/` ← HuggingFace `IDEA-Research/grounding-dino-base`
> - `vocab_tree_flickr100K_words32K.bin` ← COLMAP 官方
>
> **SMPL body_models** 全部文件均已上传至 `WenjiaWang/EmbodMocap_release`，接收方可直接从 hf-mirror.com 下载，无需额外申请（见 Step 3）。

#### 上传步骤

```bash
pip install huggingface_hub

python - <<'EOF'
from huggingface_hub import HfApi
api = HfApi()

# 上传到已有的 EmbodMocap_release 仓库
repo_id = "WenjiaWang/EmbodMocap_release"

api.upload_file(
    path_or_fileobj="/home/wubin/EmbodMocap_dev/checkpoints/vimo_checkpoint.pth.tar",
    path_in_repo="checkpoints/vimo_checkpoint.pth.tar",
    repo_id=repo_id,
    repo_type="dataset",
)

api.upload_file(
    path_or_fileobj="/home/wubin/EmbodMocap_dev/checkpoints/lingbot_depth_vitl14.pt",
    path_in_repo="checkpoints/lingbot_depth_vitl14.pt",
    repo_id=repo_id,
    repo_type="dataset",
)
print("上传完成")
EOF
```

---

## Part 2：使用者——完整部署流程

---

### Step 0：确认宿主机环境

| 要求 | 最低版本 | 验证命令 |
|------|---------|---------|
| NVIDIA 显卡 | RTX 20 系及以上（显存 ≥ 16GB 推荐） | `nvidia-smi` |
| NVIDIA 驱动 | ≥ 525.x（支持 CUDA 12.1） | `nvidia-smi \| grep Driver` |
| nvidia-container-toolkit | 任意版本 | `docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi` |
| Docker | ≥ 20.10 | `docker version` |
| 磁盘空间 | ≥ 80GB | 镜像 13GB + checkpoints 14GB + 数据集 |

**安装 nvidia-container-toolkit**（若未安装）：

```bash
# Ubuntu 22.04
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# 验证
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

---

### Step 1：获取 Docker 镜像

#### 方式 A：从 ghcr.io 拉取（推荐）

```bash
# 无需登录，直接拉取公开镜像
docker pull ghcr.io/adam-code-line/embodmocap:cvpr2026

# 打本地标签，便于后续使用
docker tag ghcr.io/adam-code-line/embodmocap:cvpr2026 embodmocap:latest
```

#### 方式 B：从 tar 包导入（离线环境）

```bash
docker load < embodmocap_cvpr2026.tar.gz
```

#### 验证镜像

```bash
docker image ls embodmocap
# 期望输出类似：
# REPOSITORY   TAG       IMAGE ID       CREATED       SIZE
# embodmocap   latest    4703d7a92c4a   xx hours ago  38.2GB
```

---

### Step 2：准备 Checkpoints（模型权重）

```bash
mkdir -p ~/embodmocap_data/checkpoints
cd ~/embodmocap_data/checkpoints
```

#### 2.1 下载 ckpt_lazypack.tar（12.8GB，含绝大多数 checkpoints）

```bash
wget -c "https://hf-mirror.com/datasets/WenjiaWang/EmbodMocap_release/resolve/main/ckpt_lazypack.tar"
tar -xf ckpt_lazypack.tar
```

解压后包含：`vggt.pt`、`vimo_checkpoint.pth.tar`、`vitpose-h-multi-coco.pth`、`lingbot_depth_vitl14.pt`、`sam2.1_hiera_large.pt`、`sam2.1_hiera_small.pt`、`yolov8x.pt`、`vocab_tree_flickr100K_words32K.bin`、`vocab_tree_flickr100K_words1M.bin`

#### 2.2 单独下载 Grounding DINO（~891MB，Step 10 必需）

```bash
mkdir -p ~/embodmocap_data/checkpoints/grounding_dino_base
cd ~/embodmocap_data/checkpoints/grounding_dino_base

for f in model.safetensors config.json preprocessor_config.json \
          tokenizer.json tokenizer_config.json special_tokens_map.json vocab.txt; do
    wget -c "https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/$f"
done
cd -
```

#### 验证 Checkpoints

```bash
ls ~/embodmocap_data/checkpoints/
# 期望看到：
# grounding_dino_base/  lingbot_depth_vitl14.pt  sam2.1_hiera_large.pt
# sam2.1_hiera_small.pt  vggt.pt  vitpose-h-multi-coco.pth
# vimo_checkpoint.pth.tar  vocab_tree_flickr100K_words32K.bin
# vocab_tree_flickr100K_words1M.bin  yolov8x.pt

ls ~/embodmocap_data/checkpoints/grounding_dino_base/
# 期望看到 7 个文件（含 model.safetensors）
```

---

### Step 3：准备 Body Models（SMPL）

所有文件均可从 HuggingFace `WenjiaWang/EmbodMocap_release` 直接下载，无需注册申请：

```bash
mkdir -p ~/embodmocap_data/body_models/smpl
cd ~/embodmocap_data/body_models/smpl

HF_BASE=https://hf-mirror.com/datasets/WenjiaWang/EmbodMocap_release/resolve/main

wget -c ${HF_BASE}/SMPL_NEUTRAL.pkl
wget -c ${HF_BASE}/J_regressor_extra.npy
wget -c ${HF_BASE}/J_regressor_h36m.npy
wget -c ${HF_BASE}/smpl_mean_params.npz
wget -c ${HF_BASE}/mesh_downsampling.npz

# 验证
ls ~/embodmocap_data/body_models/smpl/
# SMPL_NEUTRAL.pkl  J_regressor_extra.npy  J_regressor_h36m.npy
# smpl_mean_params.npz  mesh_downsampling.npz
```

---

### Step 4：准备输入数据

#### 使用官方 Demo 数据（推荐先用 demo 验证环境）

```bash
mkdir -p ~/embodmocap_data/datasets

# 从 HuggingFace 下载 demo 数据集（~2GB）
cd ~/embodmocap_data/datasets
wget -c "https://hf-mirror.com/WenjiaWang/EmbodMocap_release/resolve/main/dataset_demo.tar"
tar -xf dataset_demo.tar  # 解压得到 dataset_demo/

# 下载对应的 xlsx 配置文件
wget -c "https://hf-mirror.com/WenjiaWang/EmbodMocap_release/resolve/main/release_demo.xlsx"
```

demo 数据包含两个场景：
- `0618_capture/0618livingroom1`（seq0, seq12）
- `0914_capture/0914livingroom1`（seq1, seq5）

#### 使用自定义数据

```bash
# 参考 demo 数据的目录结构，准备双视角视频：
# datasets/your_capture/your_scene/
# ├── raw_data/  ← 原始录制文件（SpectacularAI SDK 录制格式）
```

---

### Step 5：准备目录结构与配置

最终目录结构：

```
~/embodmocap_data/
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
│       └── ...（共 8-9 个文件）
├── body_models/
│   └── smpl/
│       ├── SMPL_NEUTRAL.pkl
│       ├── J_regressor_extra.npy
│       ├── J_regressor_h36m.npy
│       ├── smpl_mean_params.npz
│       └── mesh_downsampling.npz
└── datasets/
    ├── release_demo.xlsx
    └── dataset_demo/
        ├── 0618_capture/
        └── 0914_capture/
```

---

### Step 6：验证环境

先不挂载数据，只测试 Python 环境：

```bash
docker run --rm --gpus all embodmocap:latest python -c "
import torch, xformers, mmcv, mmpose, sam2
import pytorch3d, spectacularai, spconv, embod_mocap
print('torch:', torch.__version__, '| CUDA:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')
print('xformers:', xformers.__version__)
print('mmcv:', mmcv.__version__)
print('mmpose:', mmpose.__version__)
print('pytorch3d:', pytorch3d.__version__)
print('ALL OK')
"
```

期望输出：
```
torch: 2.4.1+cu121 | CUDA: True
GPU: NVIDIA GeForce RTX 4090 (或其他型号)
xformers: 0.0.27.post2
mmcv: 1.7.2
mmpose: 0.24.0
pytorch3d: 0.7.8
ALL OK
```

---

### Step 7：运行 Demo

#### 7.1 启动容器

```bash
# 将下面路径替换为你的实际路径
DATA_ROOT=~/embodmocap_data

docker run --rm -it --gpus all \
  -v $DATA_ROOT/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro \
  -v $DATA_ROOT/body_models:/workspace/EmbodMocap_dev/body_models:ro \
  -v $DATA_ROOT/datasets:/workspace/EmbodMocap_dev/datasets \
  embodmocap:latest bash
```

#### 7.2 在容器内运行流水线

以下命令均在容器内执行：

```bash
cd /workspace/EmbodMocap_dev/embod_mocap

# ======== 第一段：Steps 1-5（场景重建 + 视角分割）========
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 1-5 --mode overwrite
```

> ⚠️ **Step 6 之前需手动操作**：Steps 1-5 完成后，打开 `release_demo.xlsx`，填写每个序列的 `v1_start`、`v2_start` 列（视角切分的起始帧号）。可通过 `raw1/images/` 和 `raw2/images/` 目录确认帧号。

```bash
# ======== 第二段：Steps 6-9（人体检测 + 关键帧）========
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 6-9 --mode overwrite

# ======== 第三段：Step 10（深度 + 分割掩码，最耗时）========
# 每个序列约 3-5 分钟，4 个序列共约 15-20 分钟
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 10 --mode overwrite

# ======== 第四段：Steps 11-15（相机追踪 + 运动优化）========
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --config config_fast.yaml --steps 11-15 --mode overwrite
```

#### 7.3 检查各阶段输出

```bash
# 检查所有步骤完成情况
python run_stages.py ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --check --config config_fast.yaml --steps 1-15

# 期望输出：4 seq success, 0 failed, 0 unfinished
```

#### 7.4 关键输出文件

| 文件 | 位置 | 说明 |
|------|------|------|
| `mesh_raw.ply` | `scene/` | 场景点云 |
| `mesh_simplified.ply` | `scene/` | 简化场景网格 |
| `optim_params.npz` | `seq*/` | 优化后的人体运动参数（核心输出） |
| `cameras_*.npz` | `seq*/v*/` | 相机参数 |
| `masks_keyframe/` | `seq*/v*/` | 人体分割掩码 |
| `vggt_tracks.npz` | `seq*/` | VGGT 特征点追踪 |

---

### Step 8：处理自定义数据

```bash
# 容器内执行

# 1. 生成 xlsx 模板
python run_stages.py /workspace/EmbodMocap_dev/datasets/my_seq.xlsx \
  --data_root /workspace/EmbodMocap_dev/datasets/my_dataset \
  --steps 0

# 2. 在宿主机编辑 xlsx（填写场景名、序列名等）
# 然后按照 Demo 的步骤分段执行：

python run_stages.py ../datasets/my_seq.xlsx \
  --data_root ../datasets/my_dataset \
  --config config.yaml --steps 1-5 --mode overwrite
# ... (手动填写 v1_start/v2_start 后继续)
python run_stages.py ../datasets/my_seq.xlsx \
  --data_root ../datasets/my_dataset \
  --config config.yaml --steps 6-15 --mode overwrite
```

**多 GPU 并行（加速处理多个序列）**：

```bash
# 容器启动时需要指定多 GPU
docker run --rm -it --gpus all \
  -v $DATA_ROOT/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro \
  -v $DATA_ROOT/body_models:/workspace/EmbodMocap_dev/body_models:ro \
  -v $DATA_ROOT/datasets:/workspace/EmbodMocap_dev/datasets \
  embodmocap:latest bash

# 容器内
python run_stages_mp.py ../datasets/my_seq.xlsx \
  --data_root ../datasets/my_dataset \
  --config config.yaml --steps 1-15 --mode overwrite \
  --gpu_ids 0,1,2
```

---

### Step 9：可视化结果

```bash
# 方式一：Viser 交互式可视化（推荐，无需额外依赖）
# 在容器内启动，然后在浏览器访问 http://localhost:8080

docker run --rm -it --gpus all \
  -p 8080:8080 \
  -v $DATA_ROOT/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro \
  -v $DATA_ROOT/body_models:/workspace/EmbodMocap_dev/body_models:ro \
  -v $DATA_ROOT/datasets:/workspace/EmbodMocap_dev/datasets \
  embodmocap:latest bash

# 如果宿主机 8080 已被占用：改用 8081（端口映射和脚本参数要同时改）
#   -p 8081:8081
#   --port 8081

# 容器内执行：
python /workspace/EmbodMocap_dev/embod_mocap/tools/visualize_viser.py \
  --scene_path ../datasets/dataset_demo/0618_capture/0618livingroom1 \
  --port 8080 --stride 2 --mesh_level 1 --scene_mesh simple
# 浏览器访问 http://<服务器IP>:8080

# 方式二：渲染视频输出
python /workspace/EmbodMocap_dev/embod_mocap/tools/visualize.py \
  /workspace/EmbodMocap_dev/datasets/dataset_demo/0618_capture/0618livingroom1/seq0 \
  --input --optim_cam --downscale 2 --mode overwrite
```

---

## 常见问题

**Q: `torch.cuda.is_available()` 返回 False？**

A: 容器启动时必须加 `--gpus all`，且宿主机需要安装 `nvidia-container-toolkit`。

```bash
# 确认 GPU 在容器内可见
docker run --rm --gpus all embodmocap:latest nvidia-smi
```

**Q: Step 10 报 Grounding DINO 找不到文件？**

A: 确认 `checkpoints/grounding_dino_base/model.safetensors` 存在，且 volume 挂载路径正确。

```bash
docker run --rm \
  -v $DATA_ROOT/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro \
  embodmocap:latest \
  ls /workspace/EmbodMocap_dev/checkpoints/grounding_dino_base/
```

**Q: Step 10 报 `Could not load MultiScaleDeformableAttention kernel`？**

A: 这是警告，不是错误，可以忽略。会自动 fallback 到纯 Python 实现，结果正确。

**Q: COLMAP 很慢？**

A: Docker 镜像中 COLMAP 是 apt 版本（无 CUDA 加速），大场景重建（Step 2/3）会较慢，是预期行为。

**Q: Step 6 之前需要手动填 xlsx，能否自动化？**

A: `v1_start`/`v2_start` 表示视频中人物入场的帧号，取决于具体录制内容，必须人工确认。可通过 `seq*/raw1/images/` 目录预览帧图来确定。

**Q: 磁盘空间不够？**

A: 可以在处理完成后清理中间文件：

```bash
# 容器内执行 dry-run 预览清理内容
python run_stages.py ../datasets/my_seq.xlsx \
  --data_root ../datasets/my_dataset \
  --clean fast --clean_dry_run

# 执行清理
python run_stages.py ../datasets/my_seq.xlsx \
  --data_root ../datasets/my_dataset \
  --clean fast
```

**Q: 如何在 docker-compose.yml 中直接配置？**

修改项目根目录下的 `docker-compose.yml`，将 volume 路径改为你的实际路径：

```yaml
volumes:
  - /你的路径/embodmocap_data/checkpoints:/workspace/EmbodMocap_dev/checkpoints:ro
  - /你的路径/embodmocap_data/body_models:/workspace/EmbodMocap_dev/body_models:ro
  - /你的路径/embodmocap_data/datasets:/workspace/EmbodMocap_dev/datasets:rw
```

然后：

```bash
docker compose run --rm embodmocap bash
```
