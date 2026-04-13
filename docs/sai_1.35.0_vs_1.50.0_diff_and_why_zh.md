# spectacularAI 1.35.0 与 1.50.0 差异及 Step1 成败原因说明

## 1. 文档目的

回答两个问题：

1. spectacularAI 1.35.0 和 1.50.0 在本次问题上的差异是什么。
2. 为什么 1.50.0 能跑起来，而 1.35.0 跑不起来。

本文只基于当前项目的实测证据，不做超出证据范围的结论。

## 2. 结论速览

1. 在相同数据、相同命令下，1.35.0 对目标 scene 会报 `Mapping failed: no output generated`，1.50.0 可稳定输出结果。
2. 该差异不是由参数导致，也不是输入文件不一致导致，更不是“服务器完全不可用”导致。
3. 最合理结论是：目标 scene 属于边界样本（短时长、低观测冗余），1.35.0 在该边界上的鲁棒性不足，1.50.0 的建图鲁棒性更好，因此成败分叉。

## 3. 已验证事实（证据链）

### 3.1 输入一致，不是数据不一致问题

本地与服务器核心输入文件 SHA256 完全一致，`data.mov` 的 ffprobe 关键信息一致（codec、分辨率、帧率、帧数、时长）。

- 参考: [step1_scene_20260413_161617_consistency_check_zh.md](./step1_scene_20260413_161617_consistency_check_zh.md)

### 3.2 参数扫描失败，排除“参数没调对”

在 1.35.0 环境下，default/mono + 多档 `key_frame_distance` 均失败，且错误一致：

- `Mapping failed: no output generated`

- 参考: [step1_scene_20260413_161617_server_troubleshooting_zh.md](./step1_scene_20260413_161617_server_troubleshooting_zh.md)

### 3.3 环境可用，排除“机器/安装完全坏掉”

同机同环境中，demo scene 可成功跑通（default/mono 均 `exit=0`），说明 SAI 工具链本身可运行。

- 参考: [step1_scene_20260413_161617_server_troubleshooting_zh.md](./step1_scene_20260413_161617_server_troubleshooting_zh.md)

### 3.4 版本 A/B 结果直接显示分叉

在隔离环境中将 spectacularAI 升级到 1.50.0 后，目标两个 scene 的 Step1 均成功（default/mono 均 `exit=0`）。

- 参考: [step1_sai_version_ab_success_report_zh.md](./step1_sai_version_ab_success_report_zh.md)

### 3.5 目标 scene 是边界样本

目标 scene 约 4.20 秒、126 帧，明显短于可稳定成功的 demo 样本（约 29 秒、872 帧），可观测信息冗余更低。

- 参考: [step1_scene_20260413_161617_server_troubleshooting_zh.md](./step1_scene_20260413_161617_server_troubleshooting_zh.md)

## 4. 1.35.0 与 1.50.0 的“可证实差异”

注意：当前没有拿到可直接引用的官方逐版本变更说明，因此此处列的是可实测、可复现差异。

1. 版本号差异
   - 旧环境: spectacularAI 1.35.0
   - 新环境: spectacularAI 1.50.0

2. 相同输入下的行为差异
   - 1.35.0: target scene Step1 失败，报 `Mapping failed: no output generated`
   - 1.50.0: target scene Step1 成功，出现 `Done!` 与 `output written to ...`

3. 对边界样本的结果差异
   - 1.35.0 在短序列边界样本上更容易失败
   - 1.50.0 在同样样本上可以完成输出

## 5. 为什么 1.50.0 能跑、1.35.0 跑不起来

从证据链推导：

1. 输入一致 + 命令一致 + 机器可运行 demo
   - 排除了“数据不同”“命令误用”“环境彻底损坏”。

2. 参数扫描仍全部失败
   - 排除了“只是 key_frame_distance 不对”。

3. 仅切换版本即可把失败变成功
   - 说明关键变量是版本本身。

4. 目标 scene 属于观测信息边界样本
   - 在边界样本上，算法鲁棒性的小幅提升就可能造成成败分叉。

因此更准确的说法是：

- 不是 1.35.0 完全不能跑，而是 1.35.0 对该类短序列边界样本更容易失败。
- 1.50.0 在当前样本上表现出更好的建图鲁棒性，从而成功产出。

## 6. 关于“内部机制差异”的说明

当前无法从公开资料中确认 1.35.0 -> 1.50.0 的具体内部改动点（例如前端跟踪、关键帧选择、初始化策略或后端优化细节）。

因此本文不把“内部算法改了什么”写成确定事实，只给出事实级结论：

- 在本项目、这批样本、这套命令下，1.50.0 的可用性显著高于 1.35.0。

## 7. 实操建议（与本文结论一致）

1. 将 Step1 固定在 spectacularAI 1.50.0 的隔离环境执行。
2. 主环境保留原有依赖用于 Step2+，避免 torch/xformers/numpy 链式冲突扩散。
3. 若未来有官方 changelog，可在本文补充“机制级差异”章节。

---

最后更新：2026-04-13
