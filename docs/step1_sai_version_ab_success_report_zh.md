# Step1 SAI 版本 A/B 验证成功结论（2026-04-13）

## 1. 背景

在服务器环境 `embodmocap`（spectacularAI 1.35.0）中，`my_capture` 下多个 scene 在 Step1 持续失败，典型报错为：

- `Mapping failed: no output generated`
- `exit code = 1`

此前已完成以下排查：

1. 核心输入文件存在且可读写。
2. 参数扫描（default/mono + 多档 key_frame_distance）仍失败。
3. demo scene 在同机同环境可成功。
4. 本地与服务器核心输入文件 SHA256 一致、ffprobe 信息一致。

## 2. A/B 验证目标

验证“失败是否由 spectacularAI 版本差异导致”。

- 旧环境：`embodmocap`（spectacularAI 1.35.0）
- 新环境：`embodmocap_sai150`（spectacularAI 1.50.0，依赖补齐后）

## 3. A/B 执行结果

测试对象：

1. `../datasets/my_capture/scene_20260413_161617`
2. `../datasets/my_capture/scene_20260413_201337`

测试命令（新环境）：

- default: `sai-cli process "$S" "$S" --key_frame_distance 0.1`
- mono: `sai-cli process "$S" "$S" --mono --key_frame_distance 0.1`

结果汇总：

| Scene | default | mono | 关键日志 |
|---|---|---|---|
| scene_20260413_161617 | `exit=0` | `exit=0` | `Done!`, `output written to ...` |
| scene_20260413_201337 | `exit=0` | `exit=0` | `warning: Lost tracking!` + `Done!` |

## 4. 结论

本轮 A/B 已明确：

1. 在 spectacularAI 1.50.0 环境下，两个 scene 的 Step1 均可成功。
2. 先前在 1.35.0 下的失败，不是简单参数问题，且高概率与版本差异相关。
3. `warning: Lost tracking!` 属于轨迹过程告警，但不阻断当前建图输出（本次均成功写出产物）。

因此可将根因收敛为：

- **主因：服务器端 spectacularAI 版本较旧（1.35.0）导致边界样本鲁棒性不足。**
- **次因：scene 本身偏短、可观测性边界明显，使版本差异更容易触发成败分叉。**

## 5. 建议落地动作

### 5.1 推荐运行策略（双环境）

推荐采用“Step1 在 `embodmocap_sai150`，主流程在 `embodmocap`”的双环境方案：

1. `embodmocap_sai150`（spectacularAI 1.50.0）负责 Step1 建图。
2. `embodmocap`（spectacularAI 1.35.0）负责 Step2-16 主流程，避免 torch/xformers/numpy 链式冲突扩大。
3. 每次执行前先校验环境版本，防止跑错环境：
   - `python -c "from importlib.metadata import version; print(version('spectacularAI'))"`

### 5.2 双环境完整执行命令（可直接复制）

在 `~/EmbodMocap_dev/embod_mocap` 目录下执行：

```bash
# 0) 新环境首次运行前，先安装项目包（见 docs/install_zh.md）
cd ~/EmbodMocap_dev
python -m pip install -e ./embod_mocap
python -c "import embod_mocap; print(embod_mocap.__file__)"

# 进入流程目录
cd ~/EmbodMocap_dev/embod_mocap

export XLSX=seq_info.xlsx
export DATA_ROOT=../datasets/my_capture
export CFG=config_fast.yaml

# 0) 生成/补齐 xlsx（仅首次或数据集变化后执行）
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --steps 0

# 1) 在 sai150 环境执行 Step1
conda activate embodmocap_sai150
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite

# 2) 检查 Step1 关键产物（每个 scene 应有 transforms.json）
for s in "$DATA_ROOT"/scene_*; do
  [ -d "$s" ] || continue
  if [ -f "$s/transforms.json" ]; then
    echo "[OK] $s/transforms.json"
  else
    echo "[MISSING] $s/transforms.json"
  fi
done

# 3) 切回主环境跑 Step2-5
conda activate embodmocap
python -m pip install "spectacularAI==1.35.0"
python -c "from importlib.metadata import version; print('spectacularAI=', version('spectacularAI'))"
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 2-5 --mode overwrite

# 4) 填写/确认 seq_info.xlsx 中 v1_start、v2_start 后，再跑 Step6-16
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 6-16 --mode overwrite
```

如果你已经确认 `v1_start`/`v2_start` 全部填写正确，也可直接执行：

```bash
conda activate embodmocap
python run_stages.py "$XLSX" --data_root "$DATA_ROOT" --config "$CFG" --steps 2-16 --mode overwrite
```

补充说明（常见坑）：

1. 如果在 `embodmocap_sai150` 中运行 `run_stages.py --steps 1` 报 `ModuleNotFoundError`（例如 `torch`、`imageio`、`huggingface_hub`），这是因为 `run_stages.py` 导入链会加载 `processor/base.py` 与 `lingbot_depth`，其模块级依赖较多。
2. 如果在 Step4/Step5 报 `NotADirectoryError: .../seq0/raw1/data.jsonl` 或 `.../raw1/data.mov: Not a directory`，通常是 `raw1`/`raw2` 被创建成“文件”而不是目录（常见于把 `recording_*.zip` 直接重命名成 `raw1/raw2`）。
3. 处理方式二选一：
   - 方式 A（推荐，最小依赖）：在 `embodmocap_sai150` 里直接批量执行 `sai-cli process` 完成 Step1；
  - 方式 B：给 `embodmocap_sai150` 补齐 `run_stages.py` 所需最小依赖后再运行。

方式 A 命令示例：

```bash
conda activate embodmocap_sai150
export DATA_ROOT=../datasets/my_capture

for S in "$DATA_ROOT"/scene_*; do
  [ -d "$S" ] || continue
  echo "=== Step1 $S ==="
  sai-cli process "$S" "$S" --key_frame_distance 0.1
done
```

方式 B 命令示例：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap
python -m pip install -e .
python -m pip install torch imageio pandas openpyxl pyyaml tqdm easydict huggingface_hub safetensors einops timm hydra-core accelerate
python -c "import torch,imageio,pandas,yaml,tqdm,easydict,embod_mocap,huggingface_hub; from embod_mocap.thirdparty.lingbot_depth.mdm.model.v2 import MDMModel; print('imports OK')"
```

### 5.3 质量风险提示

对于出现 `warning: Lost tracking!` 的 scene，建议在后续步骤前检查：

1. `transforms.json` 关键帧数量与轨迹连续性。
2. `images/` 与点云输出完整性。
3. Step2 网格重建结果是否存在明显退化。

## 6. 回退策略（简要）

若主环境升级后需要回退：

1. 直接回退包版本：
   - `python -m pip install spectacularAI==1.35.0`
2. 或使用先前导出的 freeze/conda explicit 快照进行恢复。

---

结论状态：

- 本问题已从“不可建图（疑似数据侧）”升级为“版本相关可修复问题”，并已通过 A/B 实测验证可行修复路径。
