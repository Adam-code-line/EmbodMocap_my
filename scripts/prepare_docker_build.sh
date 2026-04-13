#!/bin/bash
# ============================================================
# prepare_docker_build.sh
# Docker 构建前置脚本：将不在 git repo 内的第三方源码打包进 vendor/
# 必须在 docker build 之前运行一次
# 服务器无法访问 GitHub，所有第三方源码从 /home/wubin/third_src/ 本地复制
# ============================================================

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/vendor"
THIRD_SRC="/home/wubin/third_src"

echo "[0/4] 创建 vendor 目录..."
mkdir -p "$VENDOR_DIR"

# --- t3drender ---
T3DRENDER_SRC="$THIRD_SRC/torch3d_render-main"
if [ -d "$T3DRENDER_SRC" ]; then
    echo "[1/3] 复制 t3drender 源码到 vendor/torch3d_render ..."
    rm -rf "$VENDOR_DIR/torch3d_render"
    cp -r "$T3DRENDER_SRC" "$VENDOR_DIR/torch3d_render"
    echo "  完成：$VENDOR_DIR/torch3d_render"
else
    echo "[错误] t3drender 源码不存在：$T3DRENDER_SRC"
    exit 1
fi

# --- mmcv 1.7.2 ---
MMCV_SRC="$THIRD_SRC/mmcv-1.7.2"
if [ -d "$MMCV_SRC" ]; then
    echo "[2/3] 复制 mmcv-1.7.2 源码到 vendor/mmcv-1.7.2 ..."
    rm -rf "$VENDOR_DIR/mmcv-1.7.2"
    cp -r "$MMCV_SRC" "$VENDOR_DIR/mmcv-1.7.2"
    echo "  完成：$VENDOR_DIR/mmcv-1.7.2"
else
    echo "[错误] mmcv 源码不存在：$MMCV_SRC"
    exit 1
fi

# --- SAM2 v1.0 ---
SAM2_SRC="$THIRD_SRC/sam2"
if [ -d "$SAM2_SRC" ]; then
    echo "[3/4] 复制 SAM2 源码到 vendor/sam2 ..."
    rm -rf "$VENDOR_DIR/sam2"
    cp -r "$SAM2_SRC" "$VENDOR_DIR/sam2"
    echo "  完成：$VENDOR_DIR/sam2"
else
    echo "[错误] SAM2 源码不存在：$SAM2_SRC"
    exit 1
fi

# --- chumpy（patched，纯 Python，GitHub 不通时从宿主机 site-packages 复制）---
CHUMPY_SRC="/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/chumpy"
if [ -d "$CHUMPY_SRC" ]; then
    echo "[4/4] 复制 patched chumpy 到 vendor/chumpy ..."
    rm -rf "$VENDOR_DIR/chumpy"
    cp -r "$CHUMPY_SRC" "$VENDOR_DIR/chumpy"
    echo "  完成：$VENDOR_DIR/chumpy"
else
    echo "[错误] chumpy 未安装：$CHUMPY_SRC"
    exit 1
fi

echo ""
echo "====================================="
echo "准备完成！现在可以执行 docker build："
echo "  cd $REPO_ROOT"
echo "  docker build -t embodmocap:latest ."
echo "  # 或者："
echo "  docker compose build"
echo "====================================="
