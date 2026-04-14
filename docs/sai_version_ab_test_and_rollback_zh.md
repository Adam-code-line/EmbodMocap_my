# SAI 版本 A/B 测试与回退手册（embodmocap）

本文用于在服务器上做 spectacularAI 版本 A/B 验证，并提供明确回退路径。

## 适用场景

- 现象：my_capture 下多个 scene 在 Step1 均报 Mapping failed: no output generated。
- 目标：验证是否由 spectacularAI 版本差异导致（服务器 1.35.0 vs 本地可用环境 1.50.0）。

## 零、先设置变量（可直接复制）

先在 bash 中一次性设置变量，后续命令都可直接复制：

```bash
export PROJECT_ROOT=~/EmbodMocap_dev
export PIPELINE_DIR="$PROJECT_ROOT/embod_mocap"
export DATA_ROOT="$PROJECT_ROOT/datasets/my_capture"
export XLSX="$PIPELINE_DIR/seq_info.xlsx"
export CFG="$PIPELINE_DIR/config_fast.yaml"
export LOG_DIR="$PROJECT_ROOT/logs"


export MAIN_ENV=embodmocap
export AB_ENV=embodmocap_sai150

# A/B 用例（按需替换）
export SCENE1="$DATA_ROOT/scene_20260414_102711"
# 可选第二个 scene（如不需要可不设置）
# export SCENE2="$DATA_ROOT/scene_20260413_201337"
```

可选检查：

```bash
echo "$PROJECT_ROOT"
echo "$PIPELINE_DIR"
echo "$DATA_ROOT"
echo "$XLSX"
```

## 一、先做环境快照（必须）

在当前主环境中执行：

```bash
conda activate "$MAIN_ENV"
mkdir -p "$LOG_DIR"
python -m pip freeze > "$LOG_DIR/pip_freeze_${MAIN_ENV}_before_sai_upgrade_$(date +%F_%H%M%S).txt"
conda list --explicit > "$LOG_DIR/conda_explicit_${MAIN_ENV}_before_sai_upgrade_$(date +%F_%H%M%S).txt"
```

说明：

1. pip freeze 用于 Python 包版本回退。
2. conda explicit 用于更完整的环境恢复。

## 二、新建隔离环境做 A/B（推荐）

```bash
conda create -n "$AB_ENV" python=3.11 -y
conda activate "$AB_ENV"
python -m pip install --upgrade pip
python -m pip install "spectacularAI[full]==1.50.0"
python -m pip install --upgrade "pandas<2.2"
```

如果已安装基础包但运行时报缺依赖（如 `cv2`、`pandas`），可补装：

```bash
python -m pip install opencv-python-headless
```

如果你已经遇到下面这个错误：

- `TypeError: Invalid value 'xxx' for dtype 'int64'`

可在当前环境直接执行：

```bash
conda activate "$AB_ENV"
python -m pip install --upgrade "pandas<2.2"
python -c "import pandas as pd; print('pandas=', pd.__version__)"
```

## 三、校验版本与可执行路径

注意：模块路径字段应使用 `__file__`，不是 `file`。

```bash
conda activate "$AB_ENV"
python -c "from importlib.metadata import version; import spectacularAI,sys,platform; print(sys.version); print(platform.platform()); print(version('spectacularAI')); print(spectacularAI.__file__)"
command -v sai-cli
```

补充说明：

1. `spectacularAI.file` 不存在，会触发 `AttributeError`。
2. 若出现 `No module named 'cv2'` 或 `No module named 'pandas'`，先回到第二步补依赖，再继续测试。

预期：

1. version 输出 1.50.0。
2. sai-cli 与 python 指向当前隔离环境。

## 四、只测 Step1（两个 scene）

```bash
conda activate "$AB_ENV"

# 支持只测一个 scene，或测两个 scene
SCENES=("$SCENE1")
[ -n "${SCENE2:-}" ] && SCENES+=("$SCENE2")

for S in "${SCENES[@]}"; do
    [ -d "$S" ] || { echo "[SKIP] scene not found: $S"; continue; }
    echo "=== $S ==="
    sai-cli process "$S" "$S" --key_frame_distance 0.1; echo "default_exit=$?"
    sai-cli process "$S" "$S" --mono --key_frame_distance 0.1; echo "mono_exit=$?"
done
```

## 五、结果判读

### 情况 A：1.50.0 能过

说明：版本差异很可能是关键因素。推荐保持双环境：Step1/Step5 在 `$AB_ENV`，Step2-4 与 Step6-16 在 `$MAIN_ENV`。

后续动作：

```bash
cd "$PIPELINE_DIR"

# 0) 先在主环境生成/刷新 Step0 的 xlsx（已存在则先备份）
conda activate "$MAIN_ENV"
[ -f "$XLSX" ] && cp "$XLSX" "${XLSX%.xlsx}_backup_$(date +%F_%H%M%S).xlsx"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --steps 0

# 1) 在 AB 环境完成 Step1
conda activate "$AB_ENV"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite

# 2) 回主环境跑 Step2-4
conda activate "$MAIN_ENV"
python -m pip install "spectacularAI==1.35.0"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 2-4 --mode overwrite

# 3) 回 AB 环境跑 Step5（避免 1.35 在 raw1/raw2 上 no output）
conda activate "$AB_ENV"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 5 --mode overwrite

# 4) 回主环境继续 Step6-16
conda activate "$MAIN_ENV"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 6-16 --mode overwrite
```

如果你明确要把主环境也升级为 1.50.0（不推荐，可能引入依赖冲突），再用：

```bash
conda activate "$MAIN_ENV"
python -m pip install "spectacularAI==1.50.0"
```

### 情况 B：1.50.0 仍不过

说明：可基本定性为数据侧不可建图（边界样本），优先选择：

1. 同步本地可用 Step1 产物到服务器继续 Step2。
2. 重录数据（建议 15-30 秒，明显平移，尽量回环）。

## 六、怎么回退

### 回退 1：删除测试环境（最常用）

```bash
conda deactivate
conda env remove -n "$AB_ENV"
```

### 回退 2：主环境只回退 spectacularAI 版本

如果你把主环境升到了 1.50.0，想回到 1.35.0：

```bash
conda activate "$MAIN_ENV"
python -m pip install "spectacularAI==1.35.0"
```

校验：

```bash
python -c "from importlib.metadata import version; print(version('spectacularAI'))"
```

### 回退 3：按 freeze 文件恢复 Python 包（保守方案）

先找到第一步导出的 freeze 文件，再执行：

```bash
conda activate "$MAIN_ENV"
python -m pip install -r "$LOG_DIR/pip_freeze_${MAIN_ENV}_before_sai_upgrade_YYYY-MM-DD_HHMMSS.txt"
```

### 回退 4：按 conda explicit 文件重建环境（最彻底）

```bash
conda create -n embodmocap_restore --file "$LOG_DIR/conda_explicit_${MAIN_ENV}_before_sai_upgrade_YYYY-MM-DD_HHMMSS.txt" -y
```

说明：这是重建新环境，不会覆盖原环境。

## 七、执行建议

1. 先用隔离环境做 A/B，不要直接改主环境。
2. 先跑 Step0，再单跑 Step1 成功，再继续 Step2-4，并把 Step5 放在 `$AB_ENV` 执行，避免连锁报错干扰判断。
3. 每次改版本前都先做快照，确保可回退。

## 八、快速指令

```bash
export PROJECT_ROOT=~/EmbodMocap_dev
export PIPELINE_DIR="$PROJECT_ROOT/embod_mocap"
export DATA_ROOT="$PROJECT_ROOT/datasets/my_capture"
export XLSX="$PIPELINE_DIR/seq_info.xlsx"
export CFG="$PIPELINE_DIR/config_fast.yaml"
export MAIN_ENV=embodmocap
export AB_ENV=embodmocap_sai150

cd "$PIPELINE_DIR"

# 修复 int64 报错（建议先执行一次）
conda activate "$AB_ENV"
python -m pip install --upgrade "pandas<2.2"

# 0) Step0：生成/刷新 xlsx（已存在则先备份）
conda activate "$MAIN_ENV"
[ -f "$XLSX" ] && cp "$XLSX" "${XLSX%.xlsx}_backup_$(date +%F_%H%M%S).xlsx"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --steps 0

# 1) Step1：在 sai150 环境执行
conda activate "$AB_ENV"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite

# 2) Step2-4：切回主环境执行
conda activate "$MAIN_ENV"
python -m pip install "spectacularAI==1.35.0"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 2-4 --mode overwrite

# 3) Step5：回 sai150 环境执行
conda activate "$AB_ENV"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 5 --mode overwrite

# 4) Step6-16：回主环境执行
conda activate "$MAIN_ENV"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 6-16 --mode overwrite
```
