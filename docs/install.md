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

Install PyTorch according to your CUDA runtime (pick one):

```bash
# CUDA 12.4 example
pip install torch==2.4.1 torchvision==0.19.1 --extra-index-url https://download.pytorch.org/whl/cu124

# CUDA 12.8 example
# pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

## 3) Install Core Dependencies

```bash
pip install -r requirements.txt
pip install -e embod_mocap
```


## 4) Third-party Modules (Submodules)

The open-source release does **not** vendor third-party source code directly; use submodules.

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

Recommended checkpoints (examples):

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

## 6) External Tools

### COLMAP

```bash
sudo apt install libopenimageio-dev openimageio-tools
sudo apt install libopenexr-dev
```

COLMAP install guide:
- https://colmap.github.io/install.html

Optional COLMAP vocab tree files:

```bash
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_flickr100K_words32K.bin' -O $your_colmap_path
wget 'https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_faiss_flickr100K_words1M.bin' -O $your_colmap_path
```

## 7) Advanced Optional Dependencies

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


## 8) Sanity Check

```bash
cd embod_mocap
python run_stages.py -h
python processor/visualize.py -h
```

## 9) Open-source Release Note

Compared to the paper implementation, this open-source release replaces **PromptDA** with **LingbotDepth** in practical setup.

## 10) Troubleshooting

- Read [docs/QAs.md](QAs.md) first.
- SciPy / NumPy warnings: align versions to satisfy SciPy requirements.
- xformers warnings: check torch/xformers compatibility.
- CUDA mismatch: ensure torch CUDA build matches local driver/toolkit.
- Submodule import errors: re-run `git submodule update --init --recursive`.
- Missing checkpoints: ensure files exist under `checkpoints/` and config paths match.

