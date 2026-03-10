# 安装说明（EmbodMocap）

**语言切换 / Language:** [中文](install_zh.md) | [English](install.md)

本文覆盖开源主流程所需的安装步骤以及必要依赖 / checkpoints 配置。

## 1）克隆仓库

```bash
git clone --recurse-submodules https://github.com/WenjiaWang0312/EmbodMocap
cd EmbodMocap
```

如果已克隆但还没有拉取 submodule：

```bash
git submodule update --init --recursive
```

## 2）创建 Python 环境

```bash
conda create -n embodmocap python=3.11 -y
conda activate embodmocap
```

根据你的 CUDA 运行时安装 PyTorch（下面给出两个示例）：

```bash
# CUDA 12.4 示例
pip install torch==2.4.1 torchvision==0.19.1 --extra-index-url https://download.pytorch.org/whl/cu124

# CUDA 12.8 示例
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

## 3）安装核心依赖

```bash
pip install -r requirements.txt
pip install -e embod_mocap
```

## 4）第三方模块（Submodule）

第三方依赖通过 Git submodule 管理，而不是直接内置在仓库中。

这些 submodule 可通过以下命令添加：

```bash
cd embodmocap
git submodule add https://github.com/luca-medeiros/lang-segment-anything thirdparty/lang_sam
git submodule add https://github.com/Robbyant/lingbot-depth thirdparty/lingbot_depth
git submodule add https://github.com/ViTAE-Transformer/ViTPose thirdparty/ViTPose
```

常见模块：

- `embod_mocap/thirdparty/lingbot_depth`
- `embod_mocap/thirdparty/lang_sam`
- `embod_mocap/thirdparty/ViTPose`

如果需要可编辑安装：

```bash
pip install -e embod_mocap/thirdparty/lingbot_depth
pip install -e embod_mocap/thirdparty/lang_sam
pip install -e embod_mocap/thirdparty/ViTPose
```

## 5）COLMAP

```bash
sudo apt install libopenimageio-dev openimageio-tools
sudo apt install libopenexr-dev
```

COLMAP 安装指南：

- https://colmap.github.io/install.html

## 6）其他依赖

### torch-scatter（部分训练 / 评估路径需要）

```bash
pip install torch-scatter -f https://data.pyg.org/whl/torch-2.7.0+cu128.html
```

### pytorch3d / 渲染栈（可选）

```bash
conda install -c iopath iopath
conda install -c bottler nvidiacub
# 选择与你的 CUDA / PyTorch 匹配的 pytorch3d 包
pip install git+https://github.com/WenjiaWang0312/torch3d_render.git
```

## 7）排障

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

关于 COLMAP 配准与定位问题，参考：

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

你可能还需要：

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
