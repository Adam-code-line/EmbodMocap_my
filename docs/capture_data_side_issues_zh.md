# 拍摄数据侧问题说明（含单机复制伪双机位风险）

## 1. 结论先行

如果你把同一台相机的录制数据复制一份当作第二机位（例如把 `raw1` 直接复制成 `raw2`），这是高风险错误输入，会显著提高以下失败概率：

1. Step5 `Lost tracking`、`Fallback produced too few frames`
2. Step6 仅切出 2-3 帧，甚至 `v1/images`、`v2/images` 为空
3. Step8 相机配准失败（`cameras_colmap.npz` 缺失）

该流水线的设计前提是“真实双机位”而不是“同源复制双份数据”。

## 2. 为什么会失败

### 2.1 几何基线退化

真实双机位依赖视差（parallax）和非零基线。复制单机数据后，两路观测几乎同源，几何约束退化，导致跟踪和配准不稳定。

### 2.2 观测信息不足被放大

短序列、纯旋转、弱纹理在真实双机位下尚有机会勉强通过；伪双机位会进一步放大不可观测问题。

### 2.3 后续步骤连锁失败

Step5 相机轨迹一旦很短，Step6 只能按短轨迹切片；切片短又会让 Step8 配准更难收敛。

## 3. 与你现有日志的对应关系

当你看到下面组合信号时，通常可判定是数据侧问题优先：

1. `warning: Lost tracking!`
2. `Fallback produced too few frames ...`
3. Step6 只输出 2-3 帧或提示 `v1/images is empty`, `v2/images is empty`

这类日志中出现的 `xformers FutureWarning`、pandas `FutureWarning` 通常不是主因。

## 4. 快速自检（5 分钟）

在服务器执行：

```bash
export SEQ=../datasets/my_capture/scene_20260414_152817/seq0

# A) 直接看两路 mov 是否字节级相同（完全相同几乎必然是伪双机位）
sha256sum "$SEQ/raw1/data.mov" "$SEQ/raw2/data.mov"

# B) 看两路 jsonl 是否完全一致
sha256sum "$SEQ/raw1/data.jsonl" "$SEQ/raw2/data.jsonl"

# C) 看 Step4 抽帧数
find "$SEQ/raw1/images" -maxdepth 1 -name '*.jpg' | wc -l
find "$SEQ/raw2/images" -maxdepth 1 -name '*.jpg' | wc -l

# D) 看 Step5 轨迹长度
python - <<'PY'
import os, numpy as np
seq = os.environ["SEQ"]
for v in ["raw1", "raw2"]:
    p = f"{seq}/{v}/cameras_sai.npz"
    if not os.path.exists(p):
        print(v, "MISSING", p)
        continue
    d = np.load(p)
    f = d["frame_ids"]
    strict_inc = bool((np.diff(f) > 0).all()) if len(f) > 1 else True
    print(v, "count=", len(f), "min=", int(f.min()), "max=", int(f.max()), "strict_inc=", strict_inc)
PY
```

判定建议：

1. `raw1/raw2` 的 `data.mov` 或 `data.jsonl` 哈希完全相同：基本可判定伪双机位。
2. Step5 最佳恢复帧数长期 < 10：优先重录，不建议继续“调参硬跑”。

## 5. 该怎么改（优先级）

### 5.1 第一优先：重录真实双机位

必须使用两台设备同步采集，不要复制同一路数据模拟第二机位。

### 5.2 重录 Checklist（建议打印给采集同学）

1. 时长 15-30 秒。
2. 开始先慢速平移 2-3 秒，不要上来快速旋转。
3. 场景内要有足够纹理（书架、海报、桌面杂物等）。
4. 光照稳定，避免明显拖影和曝光剧变。
5. 增加小回环（走出去再回看同一区域）。
6. 用激光点/闪光做同步信号，后续填写 `v1_start`、`v2_start`。

### 5.3 第二优先：仅做最后抢救验证

若短期无法重录，可只做一次“可恢复性验证”：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap
export SEQ=../datasets/my_capture/scene_20260414_152817/seq0

python processor/smooth_camera.py "$SEQ" \
  --proc_v1 --proc_v2 \
  --fallback_key_frame_distance 0.03 \
  --min_fallback_frames 30 \
  --fallback_try_mono
```

如果这一步最佳恢复帧数仍 < 10，建议直接重录，不再投入调参时间。

## 6. 给团队的执行规范（可直接贴群）

1. 禁止使用“复制单机数据当双机位”的输入。
2. 提交流水线任务前，必须提供：
   - `sha256sum raw1/data.mov raw2/data.mov`
   - Step4 抽帧数量
   - Step5 `frame_ids` 数量统计
3. 未通过上述检查的序列，不进入 Step8 及后续计算密集步骤。
