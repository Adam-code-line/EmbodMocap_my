# Installation (EmbodMocap)

**Language / 语言切换:** [English](install.md) | [中文](install_zh.md)

This guide covers the open-source main pipeline setup and required dependencies/checkpoints.

## 1) Clone Repository

```bash
git clone --recurse-submodules https://github.com/WenjiaWang0312/EmbodMocap
cd EmbodMocap
```

If already cloned without submodules:

```bash
git submodule update --init --recursive
```

## 2) Create Python Environment

```bash
conda create -n embodmocap python=3.11 -y
conda activate embodmocap
```

Install PyTorch according to your CUDA runtime (give two examples here):

```bash
# CUDA 12.4 example
pip install torch==2.4.1 torchvision==0.19.1 --extra-index-url https://download.pytorch.org/whl/cu124

# CUDA 12.8 example
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

## 3) Install Core Dependencies

```bash
pip install -r requirements.txt
pip install -e embod_mocap
```

## 4) Third-party Modules (Submodules)

Third-party dependencies are managed as Git submodules rather than vendored code.

Common modules:

- `embod_mocap/thirdparty/lingbot_depth`
- `embod_mocap/thirdparty/lang_sam`
- `embod_mocap/thirdparty/ViTPose`

If editable install is needed:

```bash
pip install -e embod_mocap/thirdparty/lingbot_depth
pip install -e embod_mocap/thirdparty/lang_sam
pip install -e embod_mocap/thirdparty/ViTPose
```

## 5) Checkpoints

```bash
mkdir -p checkpoints
```

Store project checkpoints under the repository-level `checkpoints/` folder.

Recommended checkpoints (examples):

```bash
# VGGT
wget https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt -O checkpoints/vggt.pt

# SAM2, choose your preferred one
wget https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt -O checkpoints/sam2.1_hiera_large.pt
wget https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt -O checkpoints/sam2.1_hiera_small.pt

# VIMO
gdown --fuzzy -O ./checkpoints/vimo_checkpoint.pth.tar https://drive.google.com/file/d/1fdeUxn_hK4ERGFwuksFpV_-_PHZJuoiW/view?usp=share_link

# detector / pose checkpoints
gdown "https://drive.google.com/uc?id=1zJ0KP23tXD42D47cw1Gs7zE2BA_V_ERo&export=download&confirm=t" -O 'checkpoints/yolov8x.pt'
gdown "https://drive.google.com/uc?id=1xyF7F3I7lWtdq82xmEPVQ5zl4HaasBso&export=download&confirm=t" -O 'checkpoints/vitpose-h-multi-coco.pth'
```

## 6) Pipeline Assets

Dataset download links and the recommended file layout now live in `docs/embod_mocap.md` so the run commands and data organization stay in one place.

## 7) COLMAP

```bash
sudo apt install libopenimageio-dev openimageio-tools
sudo apt install libopenexr-dev
```

COLMAP install guide:

- https://colmap.github.io/install.html

Optional COLMAP vocab tree files (store them under `checkpoints/` as well):

```bash
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_flickr100K_words32K.bin' -O checkpoints/vocab_tree_flickr100K_words32K.bin
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_faiss_flickr100K_words1M.bin' -O checkpoints/vocab_tree_faiss_flickr100K_words1M.bin
```

## 8)  Other Dependencies

### torch-scatter (for selected training/eval paths)

```bash
pip install torch-scatter -f https://data.pyg.org/whl/torch-2.7.0+cu128.html
```

### pytorch3d / rendering stack (optional)

```bash
conda install -c iopath iopath
conda install -c bottler nvidiacub
# choose an appropriate pytorch3d package for your CUDA/PyTorch
pip install git+https://github.com/WenjiaWang0312/torch3d_render.git
```

## 10) Troubleshooting

### COLMAP

#### Installation

- https://github.com/colmap/colmap/issues/2464

#### `No CMAKE_CUDA_COMPILER could be found`

- https://github.com/jetsonhacks/buildLibrealsense2TX/issues/13

#### `FAILED: src/colmap/mvs/CMakeFiles/xxx`

- https://github.com/colmap/colmap/issues/2091

#### `libcudart.so` error

- https://github.com/vllm-project/vllm/issues/1369
- Example:

```bash
export LD_LIBRARY_PATH=/home/wwj/miniconda3/envs/droidenv/lib/:$LD_LIBRARY_PATH
```

#### Registration issues

For COLMAP registration and localization issues, see:

- https://colmap.github.io/faq.html#register-localize-new-images-into-an-existing-reconstruction

### NumPy

#### `ImportError: cannot import name 'bool' from 'numpy'`

Try:

```bash
pip install git+https://github.com/mattloper/chumpy
```

#### `floating point exception`

Try:

```bash
pip install numpy==1.26.4
```

You may also need:

```bash
pip install --force-reinstall charset-normalizer==3.1.0
```

#### `ValueError: numpy.dtype size changed`

Example error:

```text
ValueError: numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject.
```

Recommended version:

```ini
numpy==1.26.4
```

### Isaac Gym

Example `LD_LIBRARY_PATH` settings:

```bash
export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/envs/gym/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/pkgs/python-3.8.20-he870216_0/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
```
