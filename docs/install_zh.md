# 安装说明（EmbodMocap）

**语言切换 / Language:** [中文](install_zh.md) | [English](install.md)

本文覆盖开源主流程所需的安装步骤与依赖/权重配置。

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

开源版不直接内置 thirdparty 源码，统一通过 submodule 管理。

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

## 5）模型权重（checkpoints）

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

## 6）外部工具

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

## 7）高级可选依赖

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


## 8）快速自检

```bash
cd embod_mocap
python run_stages.py -h
python processor/visualize.py -h
```

## 9）开源版说明

相较论文实现，当前开源版本在实用链路中将 **PromptDA** 替换为 **LingbotDepth**。

## 10）排障

- 优先查看 [docs/QAs.md](QAs.md)。
- SciPy / NumPy 警告：按 SciPy 依赖范围对齐版本。
- xformers 警告：检查 torch / xformers 兼容性。
- CUDA 不匹配：确认 torch CUDA 构建与本机驱动/工具链一致。
- submodule 导入失败：重新执行 `git submodule update --init --recursive`。
- 权重缺失：检查 `checkpoints/` 文件存在与配置路径一致。

