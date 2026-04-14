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

## 7. 可视化与远程访问

远程服务器端起服务后，可在本地端口转发：

```bash
ssh -p 22 -L 8080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

浏览器访问：`http://127.0.0.1:8080`。

## 8. 执行交付要求

每次执行后必须回传：

1. 本次 `SCENE` 名称。
2. Step1/4/5 三个检查命令输出。
3. 若失败，贴完整报错段与对应修复分支执行结果。
