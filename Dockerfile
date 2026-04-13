# ============================================================
# EmbodMocap — Dockerfile
# Base: nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04
# Python: 3.11 (via Miniconda)
# PyTorch: 2.4.0+cu121
# ============================================================

FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# ---------- 基础系统环境变量 ----------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ---------- 系统依赖 ----------
# 包含：COLMAP (apt 3.7, 无 CUDA), OpenGL, build tools, git, ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget curl unzip ca-certificates \
        colmap \
        libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libxext6 \
        ninja-build build-essential cmake \
        libboost-all-dev libeigen3-dev \
        ffmpeg libavcodec-dev libavformat-dev libswscale-dev \
        libopencv-dev \
        tzdata \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------- Miniconda (Python 3.11) ----------
# 需要 conda 才能安装 pytorch3d 预编译 conda 包
RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-py311_24.7.1-0-Linux-x86_64.sh \
        -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh
ENV PATH="/opt/conda/bin:$PATH"
RUN conda init bash && conda clean -afy

# ---------- 配置 pip 镜像（可选，加速国内构建） ----------
# 如在国内构建服务器，取消下方注释以使用清华源：
# RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- PyTorch 2.4.1 + CUDA 12.1 ----------
# ⚠️ 先装 2.4.1（torchvision 0.19.1 的原生兼容版本）
# xformers 安装后会将 torch 降至 2.4.0，两版本 API 等价
RUN pip install --no-cache-dir \
        torch==2.4.1+cu121 \
        torchvision==0.19.1+cu121 \
        --index-url https://download.pytorch.org/whl/cu121

# ---------- xformers 0.0.27.post2 ----------
# ⚠️ Step 10 (lingbot_depth DINOv2) 强依赖；安装后 torch 仍是 2.4.0
RUN pip install --no-cache-dir \
        xformers==0.0.27.post2 \
        --index-url https://download.pytorch.org/whl/cu121

# ---------- pytorch3d 0.7.8（conda 预编译包）----------
# ⚠️ 不要源码编译（编译时极易 OOM）
# 从清华镜像下载预编译 conda 包并安装
RUN wget -q https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch3d/linux-64/pytorch3d-0.7.8-py311_cu121_pyt241.tar.bz2 \
        -O /tmp/pytorch3d.tar.bz2 && \
    conda install -y --use-local /tmp/pytorch3d.tar.bz2 && \
    rm /tmp/pytorch3d.tar.bz2 && \
    conda clean -afy

# ---------- 第三方源码依赖（从 vendor/ 复制，不依赖 GitHub 网络）----------
# vendor/ 由 prepare_docker_build.sh 在 docker build 前准备好
COPY vendor/mmcv-1.7.2 /opt/third_src/mmcv-1.7.2
COPY vendor/sam2 /opt/third_src/sam2

# ---------- mmcv 1.7.2 源码编译（不带 CUDA ops）----------
# ⚠️ 不能用 mmcv 2.x（ViTPose 依赖 mmcv.parallel 等 1.x 模块）
RUN MMCV_WITH_OPS=0 pip install --no-build-isolation -e /opt/third_src/mmcv-1.7.2

# ---------- SAM2 v1.0 源码安装 ----------
# ⚠️ PyPI 新版 SAM-2 要求 torch>=2.5.1，必须用 v1.0 源码
RUN pip install --no-cache-dir -e /opt/third_src/sam2

# ---------- 主项目代码 ----------
WORKDIR /workspace
COPY . /workspace/EmbodMocap_dev
WORKDIR /workspace/EmbodMocap_dev

# ---------- t3drender 安装 ----------
# t3drender 非 PyPI 包，从项目内 vendor 目录安装
# 构建前需将源码放入 vendor/torch3d_render/（见文档）
RUN pip install --no-cache-dir -e /workspace/EmbodMocap_dev/vendor/torch3d_render

# ---------- mmpose 0.24.0（ViTPose submodule）----------
# ⚠️ 必须在 mmcv 1.7.2 之后安装，且必须 patch mmcv_maximum_version
RUN sed -i "s/mmcv_maximum_version = .*/mmcv_maximum_version = '99.0.0'/" \
        /workspace/EmbodMocap_dev/embod_mocap/thirdparty/ViTPose/mmpose/__init__.py && \
    pip install --no-cache-dir --no-deps \
        -e /workspace/EmbodMocap_dev/embod_mocap/thirdparty/ViTPose

# ---------- lang_sam（submodule）----------
# ⚠️ lang_sam/requirements.txt 里 sam-2 路径写死了宿主机路径，需 patch 为容器内路径
RUN sed -i 's|sam-2 @ file:///home/wubin/third_src/sam2|sam-2 @ file:///opt/third_src/sam2|g' \
        /workspace/EmbodMocap_dev/embod_mocap/thirdparty/lang_sam/requirements.txt && \
    pip install --no-cache-dir \
        -e /workspace/EmbodMocap_dev/embod_mocap/thirdparty/lang_sam

# ---------- spconv-cu121 ----------
RUN pip install --no-cache-dir spconv-cu121==2.3.8

# ---------- 主要 pip 依赖（清理后的 requirements）----------
RUN pip install --no-cache-dir \
        scikit-learn openpyxl open3d smplx trimesh \
        imageio imageio-ffmpeg pillow>=10.1.0 \
        easydict gradio==6.9.0 litserve pydantic==2.9.2 \
        gdown yacs progress \
        ultralytics==8.4.21 \
        supervision==0.23.0 \
        transformers==4.44.2 \
        spectacularAI==1.35.0 \
        lightning pytorch-lightning \
        einops tqdm ipdb termcolor \
        numpy opencv-python scipy matplotlib h5py \
        tyro==0.9.2 \
        huggingface_hub safetensors \
        scikit-image \
        timm \
        natsort \
        hydra-core accelerate prettytable \
        json-tricks pyquaternion \
        plyfile viser \
        pycocotools xtcocotools \
        mmdet mmengine \
        cython \
        fvcore iopath \
        embreex manifold3d \
        plotly dash \
        fire colorlog

# ---------- chumpy（numpy 兼容补丁）----------
# ⚠️ numpy>=1.24 与原版 chumpy 不兼容，必须安装 patched 版本
# GitHub 不通，从 vendor/ 直接复制 patched 源码（纯 Python，无需编译）
COPY vendor/chumpy /opt/conda/lib/python3.11/site-packages/chumpy

# ---------- 主项目安装（embod_mocap package）----------
# ⚠️ setup.py 用了 package_dir={"":".."}，pip editable install 路径解析有 bug
# 改用 .pth 文件将项目根加入 sys.path，效果与 pip install -e 完全等价
RUN echo "/workspace/EmbodMocap_dev" \
        > /opt/conda/lib/python3.11/site-packages/embod_mocap.pth

# ---------- LD_LIBRARY_PATH（COLMAP 运行时需要）----------
ENV LD_LIBRARY_PATH="/opt/conda/lib:${LD_LIBRARY_PATH}"

# ---------- 运行时配置 ----------
# checkpoints/ 和 body_models/ 通过 volume 挂载（不打包进镜像）
ENV EMBODMOCAP_ROOT=/workspace/EmbodMocap_dev
WORKDIR /workspace/EmbodMocap_dev/embod_mocap

# 默认入口：bash（便于交互调试）
# 正式使用时通过 docker-compose command 覆盖
CMD ["/bin/bash"]
