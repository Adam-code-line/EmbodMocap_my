# scene_20260413_113659 在 EmbodMocap 的 step0/step1 排障说明

本文只关注 step0 和 step1。

## 结论（先给结果）

1. step0 的逻辑本身没有问题，但它依赖 scene 目录下存在 seq\* 子目录。
2. 当前这个 scene 已经有 seq0，因此 step0 可以识别到该 scene（不属于“空场景被跳过”）。
3. step1 失败的直接原因是 SAI 默认处理链路报错：Invalid value ... for dtype int64。
4. EmbodMocap 的 step1 目前没有 --mono 回退逻辑，因此默认失败会直接中断。

## 证据与代码定位

### step0 如何决定“要不要处理 scene”

- step0 自动生成 xlsx 时，只扫描每个 scene 下名字以 seq 开头的目录：
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L616)
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L621)
- 只有扫描到 seq\* 才会写入一行 scene_folder/seq_name：
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L626)

### step1 如何触发

- full_steps 会从 xlsx 行里收集 scene_folders：
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L823)
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L826)
- step1 对每个 scene_folder 调用 sai.sh：
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L852)
  [embod_mocap/run_stages.py](embod_mocap/run_stages.py#L855)
- sai.sh 的实际命令只有默认模式，没有 mono 回退：
  [embod_mocap/processor/sai.sh](embod_mocap/processor/sai.sh#L1)

### 当前 scene 的状态

- scene 路径：
  [docs/scene_20260413_113659](docs/scene_20260413_113659)
- 已存在 seq0：
  [docs/scene_20260413_113659/seq0](docs/scene_20260413_113659/seq0)
- seq0 下有两个 recording zip，符合 step0 的最小扫描前提。

## 失败复现（step1）

用与 EmbodMocap step1 等价的命令复现（key_frame_distance=0.1）：

```powershell
sai-cli process <scene_path> <scene_path> --key_frame_distance 0.1
```

关键日志：

- Selected device type: ios-tof
- generating a simplified point cloud...
- ERROR: Invalid value '14.333333333333334' for dtype 'int64'

说明失败发生在默认 ios-tof 链路的点云简化阶段，不是 step0 的表格生成逻辑导致。

## 与项目文档的一致性检查

- 官方流程说明了 step0 先自动生成 xlsx：
  [docs/embod_mocap_zh.md](docs/embod_mocap_zh.md#L86)
- 也明确了自采数据应放在 scene/seq*/recording\_*.zip 结构：
  [docs/embod_mocap_zh.md](docs/embod_mocap_zh.md#L53)
  [docs/embod_mocap_zh.md](docs/embod_mocap_zh.md#L64)

## 只针对 step0/step1 的建议

### 1) 先确认 step0 输入是否有效

```powershell
# scene 下至少要有一个 seq* 目录
Get-ChildItem <scene_path> -Directory | Where-Object { $_.Name -like 'seq*' }
```

如果为空，step0 会生成 0 行或漏掉该 scene，后续 step1 看起来就像“没跑/跑不通”。

### 2) 对 step1 增加临时绕过（服务器先跑通）

先手工验证 mono：

```powershell
sai-cli process <scene_path> <scene_path> --mono --key_frame_distance 0.1
```

如果 mono 成功，建议把 step1 改成“默认失败后自动 mono 回退”（仅 step1 层面，不影响后续步骤定义）。

### 3) 为什么要回退

当前默认模式在该 scene 上稳定触发 dtype int64 错误，而 mono 已在同数据上验证可完成输出。对于“先跑通 pipeline”目标，step1 回退是成本最低方案。
