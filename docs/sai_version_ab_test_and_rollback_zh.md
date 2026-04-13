# SAI 版本 A/B 测试与回退手册（embodmocap）

本文用于在服务器上做 spectacularAI 版本 A/B 验证，并提供明确回退路径。

## 适用场景

- 现象：my_capture 下多个 scene 在 Step1 均报 Mapping failed: no output generated。
- 目标：验证是否由 spectacularAI 版本差异导致（服务器 1.35.0 vs 本地可用环境 1.50.0）。

## 一、先做环境快照（必须）

在当前主环境 embodmocap 中执行：

    mkdir -p ~/EmbodMocap_dev/logs
    python -m pip freeze > ~/EmbodMocap_dev/logs/pip_freeze_embodmocap_before_sai_upgrade_$(date +%F_%H%M%S).txt
    conda list --explicit > ~/EmbodMocap_dev/logs/conda_explicit_embodmocap_before_sai_upgrade_$(date +%F_%H%M%S).txt

说明：

1. pip freeze 用于 Python 包版本回退。
2. conda explicit 用于更完整的环境恢复。

## 二、新建隔离环境做 A/B（推荐）

    conda create -n embodmocap_sai150 python=3.11 -y
    conda activate embodmocap_sai150
    python -m pip install --upgrade pip
    python -m pip install "spectacularAI[full]==1.50.0"

如果已安装基础包但运行时报缺依赖（如 `cv2`、`pandas`），可补装：

    python -m pip install pandas opencv-python-headless

## 三、校验版本与可执行路径

注意：模块路径字段应使用 __file__，不是 file。

    python -c "from importlib.metadata import version; import spectacularAI,sys,platform; print(sys.version); print(platform.platform()); print(version('spectacularAI')); print(spectacularAI.__file__)"
    which sai-cli

补充说明：

1. `spectacularAI.file` 不存在，会触发 `AttributeError`。
2. 若出现 `No module named 'cv2'` 或 `No module named 'pandas'`，先回到第二步补依赖，再继续测试。

预期：

1. version 输出 1.50.0。
2. sai-cli 与 python 指向当前隔离环境。

## 四、只测 Step1（两个 scene）

    SCENE1=../datasets/my_capture/scene_20260413_161617
    SCENE2=../datasets/my_capture/scene_20260413_201337

    for S in "$SCENE1" "$SCENE2"; do
      echo "=== $S ==="
      sai-cli process "$S" "$S" --key_frame_distance 0.1; echo "default_exit=$?"
      sai-cli process "$S" "$S" --mono --key_frame_distance 0.1; echo "mono_exit=$?"
    done

## 五、结果判读

### 情况 A：1.50.0 能过

说明：版本差异很可能是关键因素。

后续动作：

    conda activate embodmocap
    python -m pip install spectacularAI==1.50.0

然后再跑流程：

    python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 1 --mode overwrite
    python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 2-5 --mode overwrite

### 情况 B：1.50.0 仍不过

说明：可基本定性为数据侧不可建图（边界样本），优先选择：

1. 同步本地可用 Step1 产物到服务器继续 Step2。
2. 重录数据（建议 15-30 秒，明显平移，尽量回环）。

## 六、怎么回退

### 回退 1：删除测试环境（最常用）

    conda deactivate
    conda env remove -n embodmocap_sai150

### 回退 2：主环境只回退 spectacularAI 版本

如果你把主环境升到了 1.50.0，想回到 1.35.0：

    conda activate embodmocap
    python -m pip install spectacularAI==1.35.0

校验：

    python -c "from importlib.metadata import version; print(version('spectacularAI'))"

### 回退 3：按 freeze 文件恢复 Python 包（保守方案）

先找到第一步导出的 freeze 文件，再执行：

    conda activate embodmocap
    python -m pip install -r ~/EmbodMocap_dev/logs/pip_freeze_embodmocap_before_sai_upgrade_YYYY-MM-DD_HHMMSS.txt

### 回退 4：按 conda explicit 文件重建环境（最彻底）

    conda create -n embodmocap_restore --file ~/EmbodMocap_dev/logs/conda_explicit_embodmocap_before_sai_upgrade_YYYY-MM-DD_HHMMSS.txt -y

说明：这是重建新环境，不会覆盖原环境。

## 七、执行建议

1. 先用隔离环境做 A/B，不要直接改主环境。
2. 先单跑 Step1 成功，再继续 Step2-5，避免连锁报错干扰判断。
3. 每次改版本前都先做快照，确保可回退。
