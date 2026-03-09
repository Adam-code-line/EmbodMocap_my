# 安装说明（EmbodMocap）

**语言切换 / Language:** [中文](install_zh.md) | [English](install.md)

本文覆盖开源主流程所需的安装步骤与依赖 / checkpoints 配置。

## 1）克隆仓库

```bash
git clone --recurse-submodules https://github.com/WenjiaWang0312/EmbodMocap
cd EmbodMocap
```

如果已克隆但没拉 submodule：

```bash
git submodule update --init --recursive
```

## 2）创建 Python 环境

```bash
conda create -n embodmocap python=3.11 -y
conda activate embodmocap
```

按 CUDA 版本安装 PyTorch（任选一套）：

```bash
# CUDA 12.4 示例
pip install torch==2.4.1 torchvision==0.19.1 --extra-index-url https://download.pytorch.org/whl/cu124

# CUDA 12.8 示例
# pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

## 3）安装核心依赖

```bash
pip install -r requirements.txt
pip install -e embod_mocap
```


## 4）第三方模块（Submodule）

第三方依赖通过 Git submodule 管理，而非直接内置源码。

常见模块：
- `embod_mocap/thirdparty/lingbot_depth`
- `embod_mocap/thirdparty/lang_sam`
- `embod_mocap/thirdparty/ViTPose`

如需可编辑安装：

```bash
pip install -e embod_mocap/thirdparty/lingbot_depth
pip install -e embod_mocap/thirdparty/lang_sam
pip install -e embod_mocap/thirdparty/ViTPose
```

## 5）Checkpoints

```bash
mkdir -p checkpoints
```

常用示例：

```bash
# VGGT
wget https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt -O checkpoints/vggt.pt

# SAM2
wget https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt -O checkpoints/sam2.1_hiera_large.pt
wget https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt -O checkpoints/sam2.1_hiera_small.pt

# VIMO
gdown --fuzzy -O ./checkpoints/vimo_checkpoint.pth.tar https://drive.google.com/file/d/1fdeUxn_hK4ERGFwuksFpV_-_PHZJuoiW/view?usp=share_link

# detector / pose checkpoints
gdown "https://drive.google.com/uc?id=1zJ0KP23tXD42D47cw1Gs7zE2BA_V_ERo&export=download&confirm=t" -O 'checkpoints/yolov8x.pt'
gdown "https://drive.google.com/uc?id=1xyF7F3I7lWtdq82xmEPVQ5zl4HaasBso&export=download&confirm=t" -O 'checkpoints/vitpose-h-multi-coco.pth'
```

## 6）数据集下载

在运行主流程之前，请先从以下任一渠道下载发布数据：

- HuggingFace：[EmbodMocap_release](https://huggingface.co/datasets/WenjiaWang/EmbodMocap_release)
- OneDrive：[EmbodMocap OneDrive Data](https://connecthkuhk-my.sharepoint.com/:f:/g/personal/wwj2022_connect_hku_hk/IgAh_tLK24aLT61TePApWqk1AdpvlVBHvyttzmO61fegoC0?e=ikzCTO)

推荐下载以下文件：

- `dataset_demo.tar` + `release_demo.xlsx`
  - 小型 demo 数据包
  - 包含 2 个 scene、4 个 seq
  - 适合安装验证和快速试跑
- `dataset_release.tar` + `release.xlsx`
  - 完整发布数据包
  - 包含 25 个 scene、105 个 seq
  - 适合完整 benchmark 或主实验

解压后的推荐目录结构：

```text
datasets/
├── dataset_demo/
│   └── ...
├── dataset_release/
│   └── ...
├── release_demo.xlsx
└── release.xlsx
```

解压后可直接使用如下命令：

```bash
# demo
cd embod_mocap
python run_stages.py ../datasets/release_demo.xlsx --data_root ../datasets/dataset_demo --config config.yaml --steps 1-15 --mode overwrite

# 完整发布数据
python run_stages.py ../datasets/release.xlsx --data_root ../datasets/dataset_release --config config.yaml --steps 1-15 --mode overwrite
```

## 7）外部工具

### COLMAP

```bash
sudo apt install libopenimageio-dev openimageio-tools
sudo apt install libopenexr-dev
```

COLMAP 官方安装：
- https://colmap.github.io/install.html

可选 vocab tree：

```bash
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_flickr100K_words32K.bin' -O $your_colmap_path
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_faiss_flickr100K_words1M.bin' -O $your_colmap_path
```

## 8）高级可选依赖

### torch-scatter（部分训练/评估路径）

```bash
pip install torch-scatter -f https://data.pyg.org/whl/torch-2.7.0+cu128.html
```

### pytorch3d / 渲染栈（可选）

```bash
conda install -c iopath iopath
conda install -c bottler nvidiacub
# 选择匹配你 CUDA/PyTorch 的 pytorch3d 版本
pip install git+https://github.com/WenjiaWang0312/torch3d_render.git
```


## 9）示例路径布局

以下是一个简单示例，展示如何在本仓库周围组织 checkpoints、body models 和 datasets：

```text
EmbodMocap/
├── checkpoints/
│   ├── vggt.pt
│   ├── sam2.1_hiera_large.pt
│   ├── sam2.1_hiera_small.pt
│   ├── vimo_checkpoint.pth.tar
│   ├── yolov8x.pt
│   ├── vitpose-h-multi-coco.pth
│   ├── vocab_tree_flickr100K_words32K.bin
│   └── vocab_tree_faiss_flickr100K_words1M.bin
├── body_models/
│   └── smpl/
│       ├── SMPL_NEUTRAL.pkl
│       ├── J_regressor_extra.npy
│       ├── J_regressor_h36m.npy
│       └── mesh_downsampling.npz
├── datasets/
│   └── dataset_raw/
│       └── example_capture/
│           └── example_scene/
│               ├── calibration.json (原始输入)
│               ├── data.jsonl (原始输入)
│               ├── metadata.json (原始输入)
│               ├── transforms.json (步骤 1 输出)
│               ├── mesh_simplified.ply (步骤 2 输出)
│               └── seq0/
│                   ├── raw1/
│                   │   ├── data.mov (原始输入)
│                   │   ├── data.jsonl (原始输入)
│                   │   ├── calibration.json (原始输入)
│                   │   ├── metadata.json (原始输入)
│                   │   └── frames2/ (原始输入帧)
│                   ├── raw2/
│                   │   └── ... (与 raw1 相同)
│                   ├── v1/
│                   │   ├── images/ (步骤 6 输出)
│                   │   ├── depths/ (步骤 10 输出，standard 模式)
│                   │   ├── depths_refined/ (步骤 10 输出，standard 模式)
│                   │   └── masks/ (步骤 10 输出，standard 模式)
│                   ├── v2/
│                   │   └── ... (与 v1 相同)
│                   └── optim_params.npz (步骤 15 输出)
└── embod_mocap/
```

建议用法：

- 将 checkpoints 放在 `checkpoints/`。
- 将 SMPL/SMPL-X body-model 资产放在 `body_models/`。
- 将捕获的 scene 放在 `datasets/` 下，并将该根目录传递给 `--data_root`。

例如：

```bash
cd embod_mocap
python run_stages.py seq_info.xlsx --data_root ../datasets/dataset_raw --config config.yaml --steps 1-5 --mode overwrite
```

## 10）快速自检

```bash
cd embod_mocap
python run_stages.py -h
python tools/visualize.py -h
```

## 11）排障

### COLMAP

#### 安装

- https://github.com/colmap/colmap/issues/2464

#### `No CMAKE_CUDA_COMPILER could be found`

- https://github.com/jetsonhacks/buildLibrealsense2TX/issues/13

#### `FAILED: src/colmap/mvs/CMakeFiles/xxx`

- https://github.com/colmap/colmap/issues/2091

#### `libcudart.so` 错误

- https://github.com/vllm-project/vllm/issues/1369
- 示例：

```bash
export LD_LIBRARY_PATH=/home/wwj/miniconda3/envs/droidenv/lib/:$LD_LIBRARY_PATH
```

#### 配准问题

COLMAP 配准和定位问题，参考：

- https://colmap.github.io/faq.html#register-localize-new-images-into-an-existing-reconstruction

### NumPy

#### `ImportError: cannot import name 'bool' from 'numpy'`

尝试：

```bash
pip install git+https://github.com/mattloper/chumpy
```

#### `floating point exception`

尝试：

```bash
pip install numpy==1.26.4
```

可能还需要：

```bash
pip install --force-reinstall charset-normalizer==3.1.0
```

#### `ValueError: numpy.dtype size changed`

错误示例：

```text
ValueError: numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject.
```

推荐版本：

```ini
numpy==1.26.4
```

### Isaac Gym

`LD_LIBRARY_PATH` 设置示例：

```bash
export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/envs/gym/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/pkgs/python-3.8.20-he870216_0/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
```
