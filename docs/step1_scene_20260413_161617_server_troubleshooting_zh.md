# scene_20260413_161617 在服务器 Step1 失败排障记录（最终定稿）

## 最终结论（2026-04-13）

在当前数据条件下，`scene_20260413_161617` 对 SAI 离线建图不可解，属于**边界样本触发的建图失败**，并且已可确认：

1. 不是 xlsx 字段问题（Step1 不依赖 `v1_start`/`v2_start`）。
2. 不是目录缺文件或权限问题（核心文件齐全、目录可写）。
3. 不是参数问题（`default`/`--mono` 且 `key_frame_distance` 多档位均失败）。
4. 不是“服务器环境整体不可用”问题（同机同环境 demo scene 可成功）。

因此当前应定性为：**该 scene 在当前观测信息量与运动几何条件下不可建图**，而非简单参数配置错误。

## 证据链（按时间顺序）

### 1) 基线复现：default 与 mono 均失败

命令：

```bash
sai-cli process $SCENE $SCENE --key_frame_distance 0.1
sai-cli process $SCENE $SCENE --mono --key_frame_distance 0.1
```

共同结果：

- `Selected device type: ios-tof`
- `Mapping failed: no output generated`
- `exit code = 1`

结论：不是“只在 default 失败”。

### 2) 参数扫描：排除“参数没调对”

扫描命令：

```bash
SCENE=../datasets/my_capture/scene_20260413_161617

for k in 0.1 0.05 0.03 0.02; do
  sai-cli process "$SCENE" "$SCENE" --key_frame_distance "$k"
  echo "default k=$k exit=$?"
done

for k in 0.05 0.03 0.02; do
  sai-cli process "$SCENE" "$SCENE" --mono --key_frame_distance "$k"
  echo "mono k=$k exit=$?"
done
```

结果摘要：

- default: `k=0.1/0.05/0.03/0.02` 全部 `exit=1`
- mono: `k=0.05/0.03/0.02` 全部 `exit=1`
- 错误始终为 `Mapping failed: no output generated`

结论：可排除“`key_frame_distance` 不合适导致失败”。

### 3) A/B 对照：排除“服务器环境整体不可用”

同一服务器、同一 conda 环境下，运行官方 demo scene：

```bash
DEMO=../datasets/dataset_demo/0618_capture/0618livingroom1
sai-cli process "$DEMO" "$DEMO" --key_frame_distance 0.1; echo "demo_default_exit=$?"
sai-cli process "$DEMO" "$DEMO" --mono --key_frame_distance 0.1; echo "demo_mono_exit=$?"
```

结果：

- `demo_default_exit=0`
- `demo_mono_exit=0`
- 输出包含 `Done!` 与 `output written to ...`

结论：服务器上的 SAI/SDK/运行环境具备可用性，不是“机器完全跑不起来”。

### 4) 输入规模对比：目标 scene 明显偏短、偏小

使用 `tools/compare_sai_inputs.py` 对比目标 scene 与 demo scene，得到：

| 指标 | target (`scene_20260413_161617`) | demo (`0618livingroom1`) |
|---|---:|---:|
| `frames2` 文件数 | 126 | 872 |
| `data.jsonl` 行数 | 1165 | 9567 |
| `data.mov` 时长 | 4.196667 s | 29.068333 s |
| `data.mov` 帧数 | 126 | 872 |

脚本结论也明确提示：

1. target `data.jsonl` 行数远小于 demo
2. target `frames2` 数量远小于 demo
3. target 视频时长远短于 demo

结论：该 scene 可用于结构合法性检查，但建图观测信息量处于边界甚至不足。

### 5) 本地 diagnose `Passed` 不等于“可稳定建图”

本地 HTML 诊断报告 `Outcome=Passed`，说明的是：

- 传感器流格式完整
- 时间戳与文件可解析

但它不直接保证：

- 运动几何可观测性足够
- 关键帧/视差质量足够支撑离线建图

因此“diagnose 通过 + 服务器建图失败”并不矛盾。

### 6) Step1 单跑批量验证：`my_capture` 下两个 scene 均失败

命令：

```bash
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 1 --mode overwrite
```

结果：

- `scene_20260413_161617`：`Mapping failed: no output generated`
- `scene_20260413_201337`：`Mapping failed: no output generated`

结论：失败不是单 scene 偶发，更像是当前 `my_capture` 采集数据在建图可观测性上的共性问题。

## 具体原因说明（为什么不是参数问题）

### 原因 1：有效建图观测不足

目标 scene 仅约 4.2 秒 / 126 帧，和可成功 demo（29 秒 / 872 帧）相比，信息量差距明显。离线建图常需要更充分的时长、覆盖与回环。

### 原因 2：运动几何可能退化

即使数据文件完整，若轨迹以旋转为主、平移基线偏小、有效纹理不足，仍会导致 `Mapping failed: no output generated`。

### 原因 3：边界样本的实现敏感性

该 scene 属于边界可解/不可解附近样本。本地与服务器底层实现差异（解码、调度、浮点路径）可能触发不同分支：本地可过、服务器不过。

## 代码路径说明

- Step1 入口：[embod_mocap/run_stages.py](../embod_mocap/run_stages.py)
- Step1 调用脚本：[embod_mocap/processor/sai.sh](../embod_mocap/processor/sai.sh)
- 当前命令：

```bash
sai-cli process ${1} ${1} --key_frame_distance ${2:-0.05}
```

## 建议处置

### A. 流程解阻（短期）

若本地已成功产出 Step1 结果，可先同步至服务器继续后续步骤。

至少同步：

- `transforms.json`
- `images/`
- `sparse_pc.ply`
- 以及 `transforms.json` 中引用到的深度路径（若有 `depth_file_path`）

> 注意：Step2 会按 `transforms.json` 的路径字段读取数据，不能只拷单个 json 文件。

#### A1. 你的 `my_capture` 对应命令（可直接执行）

在 `~/EmbodMocap_dev/embod_mocap` 目录下执行：

```bash
# 1) 生成 xlsx（步骤 0）
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --steps 0

# 2) 运行 Step1-5（scene 级 + 前半预处理）
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 1-5 --mode overwrite
```

说明：

1. `--data_root` 已替换为你的数据根目录 `../datasets/my_capture`。
2. 其中 `scene_20260413_161617` 会作为 `my_capture` 下的一个 scene 被扫描并处理。

### B. 数据侧修复（中期）

建议重录 scene，并满足：

1. 时长建议 15~30 秒
2. 轨迹含明显平移，不仅是原地旋转
3. 尽量覆盖更多视角并形成回环

### C. 诊断闭环（可选）

若仍需追根，可对本地与服务器执行同一组哈希、`ffprobe` 与版本信息对齐，判断是否存在“同名但非同文件”或二进制差异。

## 当前状态

1. 服务器上 `scene_20260413_161617` 的 Step1 在当前数据条件下仍 blocked。
2. 失败类型已明确为“不可建图（非参数问题）”，后续应优先走“同步本地 Step1 产物”或“重采数据”两条路径。
