# Step5 Tracking 很早丢失：问题说明与修复方案

## 1. 现象

常见表现：

1. 视频录了 20+ 秒，但后续 `v1/images`、`v2/images` 只有 2-3 张。
2. Step5/Step6 日志出现：
   - `warning: Lost tracking!`
   - `Smoothing failed: no output generated`
   - `Fallback produced too few frames ...`
3. Step8 失败并提示缺少 `v1/cameras_colmap.npz`、`v2/cameras_colmap.npz`。

## 2. 为什么会这样

`v1/images`、`v2/images` 是 **Step6** 产物，长度受 Step5 的 `cameras_sai.npz` 里 `frame_ids` 范围限制。

即使 Step4 从 `raw1/data.mov`、`raw2/data.mov` 抽出了几百帧，如果 Step5 只恢复出很短轨迹（例如 `frame_ids` 只到 4），Step6 也只会切出极少帧。

## 3. 你这次命令里的一个坑

你执行了：

```bash
SEQ=../datasets/my_capture/scene_xxx/seq0
python - <<'PY'
import os
seq = os.environ["SEQ"]
PY
```

会报 `KeyError: 'SEQ'`，因为 `SEQ` 没有 `export`。

正确写法：

```bash
export SEQ=../datasets/my_capture/scene_20260414_140541/seq0
```

## 4. 快速诊断（可直接复制）

```bash
export SEQ=../datasets/my_capture/scene_20260414_140541/seq0

# 1) 先看 Step4 原始抽帧数量（注意是 *.jpg，不是 .jpg）
find "$SEQ/raw1/images" -maxdepth 1 -name '*.jpg' | wc -l
find "$SEQ/raw2/images" -maxdepth 1 -name '*.jpg' | wc -l

# 2) 看 Step5 轨迹覆盖范围
python - <<'PY'
import numpy as np, os
seq = os.environ.get("SEQ")
if not seq:
    raise SystemExit("Please run: export SEQ=... first")
for v in ["raw1", "raw2"]:
    p = f"{seq}/{v}/cameras_sai.npz"
    d = np.load(p)
    f = d["frame_ids"]
    strict_inc = bool((np.diff(f) > 0).all()) if len(f) > 1 else True
    print(v, "count=", len(f), "min=", int(f.min()), "max=", int(f.max()), "strict_inc=", strict_inc)
    print("head:", f[:20].tolist())
    print("tail:", f[-20:].tolist())
PY
```

判定规则：

1. `raw1/raw2/images` 很多（几百）但 `frame_ids` 很短（只有几帧） => Step5 tracking 早丢失。
2. `frame_ids` 非严格递增（重复/乱序） => 旧版 Step6 可能在插值时报错。

## 5. 修复方案（推荐顺序）

### 方案 A：先提高 Step5 可恢复帧数（首选）

在 `embodmocap_sai150` 跑 Step5，并尝试更小 `key_frame_distance`：

```bash
conda activate embodmocap_sai150
cd ~/EmbodMocap_dev/embod_mocap
export SEQ=../datasets/my_capture/scene_20260414_140541/seq0

python processor/smooth_camera.py "$SEQ" \
  --proc_v1 --proc_v2 \
  --fallback_key_frame_distance 0.03 \
  --min_fallback_frames 30
```

若日志显示 best candidate 仍很短（例如 5 帧），可显式开启 mono 回退再试一次：

```bash
python processor/smooth_camera.py "$SEQ" \
  --proc_v1 --proc_v2 \
  --fallback_key_frame_distance 0.03 \
  --min_fallback_frames 30 \
  --fallback_try_mono
```

然后回主环境：

```bash
conda activate embodmocap
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 6,8 --mode overwrite
```

### 方案 B：强制重做 Step4，再做 Step6

如果 `raw1/raw2/images` 数量本身就很少：

```bash
conda activate embodmocap
cd ~/EmbodMocap_dev/embod_mocap
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 4,6 --mode overwrite
```

### 方案 C：Step8 仍报 colmap 失败时

说明是 scene 级 COLMAP 一致性问题，先重跑 scene 级 Step1/3，再回到 Step5-8：

```bash
conda activate embodmocap_sai150
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 1 --mode overwrite

conda activate embodmocap
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 3 --mode overwrite
python run_stages.py seq_info.xlsx --data_root ../datasets/my_capture --config config_fast.yaml --steps 5-8 --mode overwrite
```

## 6. 何时应重录

满足任一条件建议重录该 seq：

1. Step5 在多次 kfd 尝试后仍只能恢复 < 10 帧。
2. Step6 反复只能切出 2-3 帧。
3. Step8 长期无法稳定产出 `cameras_colmap.npz`。

重录建议：

1. 增加可观测纹理（避免纯墙/纯地面）。
2. 减少快速旋转，增加平移和小回环。
3. 保证足够光照，降低动态模糊。

## 7. 本次日志判读（你贴的案例）

日志关键行：

1. `Best candidate was 0.03`
2. `Fallback produced too few frames ... 5 (< 30)`

判读：

1. 这不是命令写法问题，而是该序列 `raw2` 的可恢复轨迹本体过短。
2. `libtinfo` 警告与 pandas `FutureWarning` 不是这次失败主因。
3. 这组数据在当前画面质量下已接近不可恢复边界，应优先重录；若必须尝试抢救，先用 `--fallback_try_mono` 做最后一次回退验证。
