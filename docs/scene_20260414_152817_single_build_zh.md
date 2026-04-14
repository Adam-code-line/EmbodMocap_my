# scene_20260414_152817 单独构建执行手册

## 1. 目标

只对 `scene_20260414_152817` 执行构建，不处理 `my_capture` 下其它 scene。

核心做法：

1. 先生成总表 xlsx。
2. 过滤出只包含目标 scene 的单场景 xlsx。
3. 后续所有 `run_stages.py` 都使用这个单场景 xlsx。

## 2. 一次性变量（先执行）

```bash
cd ~/EmbodMocap_dev/embod_mocap

export DATA_ROOT=../datasets/my_capture
export SCENE=scene_20260414_152817
export XLSX_ALL=seq_info_all.xlsx
export XLSX_ONE=seq_info_scene_20260414_152817.xlsx
export CFG=config_fast.yaml
```

## 3. 生成单场景 xlsx

### 3.1 生成总表（Step0）

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ALL" --data_root "$DATA_ROOT" --steps 0
```

### 3.2 过滤成仅目标 scene 的 xlsx

```bash
python - <<'PY'
import pandas as pd

src = "seq_info_all.xlsx"
dst = "seq_info_scene_20260414_152817.xlsx"
scene = "scene_20260414_152817"

xl = pd.ExcelFile(src)
dfs = [pd.read_excel(src, sheet_name=s) for s in xl.sheet_names]
df = pd.concat(dfs, ignore_index=True)

scene_col = df["scene_folder"].astype(str).str.strip()
out = df.loc[scene_col == scene].copy()

if out.empty:
    raise SystemExit(f"No rows found for {scene} in {src}")

out.to_excel(dst, index=False)
print(f"Saved {dst}, rows={len(out)}")
print(out[["scene_folder", "seq_name"]].drop_duplicates().to_string(index=False))
PY
```

### 3.3 确认过滤结果

```bash
python - <<'PY'
import pandas as pd
df = pd.read_excel("seq_info_scene_20260414_152817.xlsx")
print("rows=", len(df))
print("unique scenes=", sorted(df["scene_folder"].astype(str).unique().tolist()))
print(df[["scene_folder", "seq_name"]].drop_duplicates().to_string(index=False))
PY
```

## 4. 单场景构建完整命令

### 4.1 Step1（sai150 环境）

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 1 \
  --mode overwrite \
  --force_all
```

检查 Step1 产物：

```bash
test -f "$DATA_ROOT/$SCENE/transforms.json" && echo "[OK] transforms.json" || echo "[MISSING] transforms.json"
```

### 4.2 Step2-4（主环境）

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"

python run_stages.py "$XLSX_ONE" \
  --data_root "$DATA_ROOT" \
  --config "$CFG" \
  --steps 2-4 \
  --mode overwrite \
  --force_all
```

检查 Step4 抽帧：

```bash
for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  echo "=== $q ==="
  find "$q/raw1/images" -maxdepth 1 -name '*.jpg' | wc -l
  find "$q/raw2/images" -maxdepth 1 -name '*.jpg' | wc -l
done
```

### 4.3 Step5（sai150 环境）

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

检查 Step5 产物：

```bash
for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  echo "=== $q ==="
  test -f "$q/raw1/cameras_sai.npz" && echo "[OK] raw1/cameras_sai.npz" || echo "[MISSING] raw1/cameras_sai.npz"
  test -f "$q/raw2/cameras_sai.npz" && echo "[OK] raw2/cameras_sai.npz" || echo "[MISSING] raw2/cameras_sai.npz"
done
```

### 4.4 Step6-16（主环境）

先确认 `seq_info_scene_20260414_152817.xlsx` 的 `v1_start`、`v2_start` 已填写。

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

## 5. Step5 失败时的抢救命令（单场景）

当日志出现 `Fallback produced too few frames`，执行：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap

for q in "$DATA_ROOT/$SCENE"/seq*; do
  [ -d "$q" ] || continue
  echo "=== rescue $q ==="
  python processor/smooth_camera.py "$q" \
    --proc_v1 --proc_v2 \
    --fallback_key_frame_distance 0.03 \
    --min_fallback_frames 30 \
    --fallback_try_mono
done
```

抢救后继续：

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 6,8 --mode overwrite --force_all
```

## 6. 一条命令检查当前完成度

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1-16 --check --force_all
```

## 7. 说明

1. `run_stages.py` 本身没有“按 scene 名过滤”的独立参数，所以必须通过单场景 xlsx 控制范围。
2. 只要后续命令始终使用 `$XLSX_ONE`，就只会处理 `scene_20260414_152817`。
3. 若该 scene 的某个 seq 仍长期只能恢复极少帧（如 < 10），建议重录该 seq。
