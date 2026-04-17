# EmbodMocap 运行使用手册

## 1. 文档定位

本手册面向“执行同学/运维同学”，目标是：

1. 拿到一个 scene 后可以独立跑通 1-16 步。
2. 遇到常见故障能按分支快速定位。
3. 保证输入数据质量，避免无效算力消耗。

## 2. 使用前硬性要求

### 2.1 必须是双机位真实采集

禁止把 `raw1` 复制一份当 `raw2`。这是伪双机位，会导致 Step5/6/8 高概率失败。

详见：`docs/capture_data_side_issues_zh.md`。

### 2.2 环境要求（双 conda）

1. `embodmocap`：主流程（Step2-4, Step6-16）
2. `embodmocap_sai150`：Step1、Step5

检查版本：

```bash
conda activate embodmocap_sai150
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
```

## 3. 变量模板（先改再跑）

```bash
cd ~/EmbodMocap_dev/embod_mocap

export DATA_ROOT=../datasets/my_capture
export SCENE=scene_20260414_152817
export XLSX_ALL=seq_info_all.xlsx
export XLSX_ONE=seq_info_${SCENE}.xlsx
export CFG=config_fast.yaml
```

## 4. 单 scene 执行流程（标准）

### 4.1 生成总表并过滤成单 scene xlsx

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap

python run_stages.py "$XLSX_ALL" --data_root "$DATA_ROOT" --steps 0

python - <<'PY'
import os, pandas as pd
src = os.environ["XLSX_ALL"]
dst = os.environ["XLSX_ONE"]
scene = os.environ["SCENE"]
xl = pd.ExcelFile(src)
df = pd.concat([pd.read_excel(src, sheet_name=s) for s in xl.sheet_names], ignore_index=True)
out = df.loc[df["scene_folder"].astype(str).str.strip() == scene].copy()
if out.empty:
    raise SystemExit(f"No rows found for {scene} in {src}")
out.to_excel(dst, index=False)
print(f"Saved {dst}, rows={len(out)}")
print(out[["scene_folder", "seq_name"]].drop_duplicates().to_string(index=False))
PY
```

### 4.2 Step1（sai150）

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 1 \
  --mode overwrite \
  --force_all
```

### 4.3 Step2-4（主环境）

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 2-4 \
  --mode overwrite \
  --force_all
```

### 4.4 Step5（sai150）

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 5 \
  --mode overwrite \
  --force_all
```

### 4.5 填写同步点（人工）

打开 `$XLSX_ONE`，填写每个 seq 的：

1. `v1_start`
2. `v2_start`

### 4.6 Step6-16（主环境）

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 6-16 \
  --mode overwrite \
  --force_all
```

## 5. 每阶段最小检查命令

### 5.1 Step1 后

```bash
test -f "$DATA_ROOT/$SCENE/transforms.json" && echo "[OK] transforms.json" || echo "[MISSING] transforms.json"
```

### 5.2 Step4 后

```bash
for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  echo "=== $q ==="
  find "$q/raw1/images" -maxdepth 1 -name '*.jpg' | wc -l
  find "$q/raw2/images" -maxdepth 1 -name '*.jpg' | wc -l
done
```

### 5.3 Step5 后

```bash
for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  echo "=== $q ==="
  test -f "$q/raw1/cameras_sai.npz" && echo "[OK] raw1" || echo "[MISSING] raw1"
  test -f "$q/raw2/cameras_sai.npz" && echo "[OK] raw2" || echo "[MISSING] raw2"
done
```

### 5.4 全量完成度检查

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1-16 --check --force_all
```

## 6. 常见故障分支

### 6.1 Step5 过早丢失（最常见）

症状：`Fallback produced too few frames`，最佳帧数很低（如 2-5）。

先抢救一次：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap

for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  python processor/smooth_camera.py "$q" \
    --proc_v1 --proc_v2 \
    --fallback_key_frame_distance 0.03 \
    --min_fallback_frames 30 \
    --fallback_try_mono
done
```

若最佳帧数仍 < 10，建议重录，不再继续调参。

### 6.2 Step6 报 `v1/images is empty` 或 `v2/images is empty`

高概率是 Step4 抽帧缺失或命名不匹配。

修复顺序：

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 4,6 --mode overwrite --force_all
```

### 6.3 Step8 COLMAP 失败

先重建 scene 级基础，再回跑 5-8：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite --force_all

conda activate embodmocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 3 --mode overwrite --force_all
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 5-8 --mode overwrite --force_all
```

## 7. 仅看场景构建预览（SSH + 本地浏览器）

本节用于“我现在只想看场景构建效果”，不要求先跑完 1-16 全流程。

### 7.1 本地建立 SSH 端口转发

在你的本地电脑执行（推荐后台模式）：

```bash
ssh -p 22 -Nf -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

如果你希望前台观察连接状态，可用：

```bash
ssh -p 22 -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

### 7.2 登录服务器并准备变量

```bash
ssh -p 22 wubin@1080.alpen-y.top

cd ~/EmbodMocap_dev/embod_mocap
export DATA_ROOT=../datasets/my_capture
export XLSX_ONE=seq_info.xlsx
export CFG=config_fast.yaml
```

### 7.3 如果场景网格还没生成，先跑最小构建（Step1-2）

`$XLSX_ONE` 需先按第 4.1 节准备好（单 scene xlsx）。

```bash
# Step1：sai150 环境
conda activate embodmocap_sai150
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite --force_all

# Step2：主环境
conda activate embodmocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 2 --mode overwrite --force_all
```

### 7.4 启动“仅场景网格”预览服务（不依赖 optim_params.npz）

启动后可在 Viser GUI 的下拉列表里切换不同录制（只会列出已生成 mesh 的 scene），并默认优先展示 `mesh_raw.ply`。

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python tools/preview_scene_meshes_viser.py \
  --data_root "$DATA_ROOT" \
  --default_scene "$SCENE" \
  --mesh_mode prefer_raw \
  --port 8080
```

保持这个终端不退出，然后在本地浏览器访问：

```text
http://127.0.0.1:18080
```

### 7.5 如果要看“完整渲染 demo（人体+场景）”

该模式要求 seq 下已存在 `optim_params.npz`（通常 Step15 后才有）。

方式 A（推荐，单服务）：直接使用第 7.4 节启动的 Viser，在 GUI 的 `Human Demo (SMPL + Scene)` 里选择 `Sequence` 并点击 `Load Human`，再用 `Frame`/`Play` 播放。  
（前提：仓库根目录下 `body_models/smpl` 已准备好；可执行 `bash embod_mocap/tools/download_body_models.sh`）

方式 B（兼容旧用法，单独脚本）：

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python tools/visualize_viser.py --xlsx "$XLSX_ONE" --data_root "$DATA_ROOT" --scene_mesh simple --mesh_level 1 --stride 2 --port 8080
```

## 8. 执行交付要求

每次执行后必须回传：

1. 本次 `SCENE` 名称。
2. Step1/4/5 三个检查命令输出。
3. 若失败，贴完整报错段与对应修复分支执行结果。
