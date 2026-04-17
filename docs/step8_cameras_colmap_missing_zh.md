# Step 8 失败：缺少 `v1/cameras_colmap.npz` / `v2/cameras_colmap.npz`（服务器自动化常见原因与修复）

当你在服务器自动化流水线里看到类似报错：

```text
... Step 8 failed for /path/to/<scene>/<seq>; missing outputs:
['v1/cameras_colmap.npz', 'v2/cameras_colmap.npz'].
Common causes: scene colmap model/database mismatch, too few sliced frames,
or COLMAP image_registrator failure in processor/regist_seq.sh.
```

这表示 **Step 8 的 COLMAP 人体相机配准没有产出相机文件**（`cameras_colmap.npz`），因此后续 Step 9+ 也会连锁失败。

本文给出：为什么在服务器自动化更容易遇到、如何快速定位、以及一套推荐的修复流程（尽量少走弯路）。

---

## 1. Step 8 在做什么（为什么会依赖 Step 1/3/6）

Step 8 对应 `embod_mocap/processor/colmap_human_cam.py`，核心动作是：

1. 读取序列切片帧：`<seq>/v1/images/*.jpg`、`<seq>/v2/images/*.jpg`（来自 Step 6 `slice_views`）。
2. 调用 `embod_mocap/processor/regist_seq.sh`，把这些 v1/v2 图像 **注册到 scene 级 COLMAP 模型**：
   - 输入 scene 级 COLMAP：`<scene>/colmap/database.db` + `<scene>/colmap/sparse/0`
   - 在 `<seq>/v*/colmap/` 下做 feature/matching，然后用 `colmap image_registrator` 进行注册
3. 解析 `<seq>/v*/colmap/images.txt|points3D.txt|cameras.txt`，写出：
   - `v*/cameras_colmap.npz`
   - `v*/points2D.npz`
   - `v*/points3D.npz`

因此 Step 8 失败的本质通常是三类之一：

- **scene 级 COLMAP（Step 3）不一致/不可用**（database 与 sparse 模型不匹配、或半成品）。
- **序列切片帧（Step 6）质量不够**（帧太少、重叠不足、纹理弱/模糊），导致注册不了。
- **COLMAP 命令没跑起来/环境不对**（PATH、vocab tree、动态库等），导致 `regist_seq.sh` 提前退出。

---

## 2. 为什么“服务器自动化”更容易出这个错

结合常见运维方式，服务器上比手工单机更常见的诱因是：

### 2.1 scene 级输出“看起来有，但其实不一致”

典型场景：

- 之前跑过 scene 的 Step 3，但后来又覆盖/替换了 `<scene>/images`（重新上传、清理缓存、手动拷贝），而自动化因为 **非 overwrite** 跳过了 Step 3，导致新旧不一致。
- 同一个 scene 被 **多个服务实例/多张卡并行**处理，Step 1/3 互相覆盖，产生数据库与稀疏模型不同步。
- Step 3 中途失败留下半成品：比如 `database.db` 存在，但 `colmap/sparse/0` 缺失/为空。

这类问题往往导致 v1/v2 **同时失败**（两个 `cameras_colmap.npz` 都缺失）。

### 2.2 Step 6 切片帧不足/重叠不足（自动化更容易“起始帧填错”）

如果 `v1_start/v2_start` 没填或填错、Step 5 tracking 很短（Lost tracking），都会让 Step 6 只切出很短的一段：

- 帧数太少（虽然 Step 8 最低只检查 `>=3` 帧，但 COLMAP 通常需要更多重叠才能稳定注册）
- 帧间变化太大/纯旋转/模糊/弱纹理 → 特征点与匹配不足

这类问题更常见于 **只某一个视角失败**（比如只缺 `v2/cameras_colmap.npz`）。

### 2.3 非交互环境导致 COLMAP / vocab tree / 依赖不可用

自动化常跑在 `systemd` / `cron` / 容器入口脚本里，环境变量和交互 shell 不同：

- 没有 `conda activate` → `colmap` 不在 PATH、Python 依赖不一致
- `PATHS.colmap_vocab_tree_path` 指向的 vocab tree 文件在服务器上不存在或权限不足
- 动态库路径（如 `LD_LIBRARY_PATH`）不同导致 COLMAP 命令直接崩溃

---

## 3. 快速自检（复制即用）

以下命令假设你在服务器上：

```bash
cd ~/EmbodMocap_dev/embod_mocap
export DATA_ROOT=../datasets/my_capture
export SCENE=scene_0014
export SCENE_DIR=$DATA_ROOT/$SCENE
export SEQ=$DATA_ROOT/$SCENE/seq0
```

### 3.1 检查 Step 8 的直接输入（Step 6 切片帧）

```bash
find "$SEQ/v1/images" -maxdepth 1 -name '*.jpg' | wc -l
find "$SEQ/v2/images" -maxdepth 1 -name '*.jpg' | wc -l
```

经验建议：**不要只满足“>=3 帧”**。若只有几十帧甚至更少，先怀疑 Step 5/6 的输入或参数。

### 3.2 检查 scene 级 COLMAP（Step 3 输出）

```bash
ls -lah "$DATA_ROOT/$SCENE/colmap/database.db"
ls -lah "$DATA_ROOT/$SCENE/colmap/sparse/0" | head
```

若 `sparse/0` 不存在或为空，Step 8 一定会失败（`regist_seq.sh` 会直接退出）。

另外，`database.db` **不应只有几 KB**（例如 4.0K 基本等于空库/半成品）。正常情况下，scene 级数据库至少会包含大量 keypoints/descriptors，文件通常是 **几十 MB 甚至更大**。

你可以用 sqlite 直接确认数据库是否“空”：

```bash
sqlite3 "$DATA_ROOT/$SCENE/colmap/database.db" "select count(*) as num_images from images;"
sqlite3 "$DATA_ROOT/$SCENE/colmap/database.db" "select count(*) as num_keypoints from keypoints;"
sqlite3 "$DATA_ROOT/$SCENE/colmap/database.db" "select count(*) as num_descriptors from descriptors;"
```

如果 `num_images=0` 或 `num_keypoints=0`，说明 Step 3 虽然生成了 `database.db`，但实际上是 **空库**；此时即使 `v1/images`、`v2/images` 有几百帧，Step 8 也基本必然注册失败并缺少 `cameras_colmap.npz`。优先修复/重跑 scene 级 Step 3（见第 4 节）。

⚠️ 另外：`num_images>0` 也不代表 Step 3 是“正确完成”的。你还应该检查它是否和 sparse 模型规模匹配：

```bash
# Step 3 会生成 image-list.txt（来自 sparse/0/images.txt）
wc -l "$DATA_ROOT/$SCENE/colmap/image-list.txt" || true

# num_images / num_keypoints / num_descriptors 应该与 image-list 行数同量级
sqlite3 "$DATA_ROOT/$SCENE/colmap/database.db" "select count(*) from images;"
```

如果 `image-list.txt` 有几百行，但数据库只有 `1/1/1` 这种级别，说明 Step 3 很可能失败/中断了（只是留下了一个“半成品 db”）。

### 3.3 检查 COLMAP 与 vocab tree（环境问题一眼看出）

```bash
which colmap || true
colmap -h | head -n 5

python -c "from embod_mocap.config_paths import PATHS; print('vocab_tree=', PATHS.colmap_vocab_tree_path)"
python - <<'PY'
from pathlib import Path
from embod_mocap.config_paths import PATHS
p = Path(PATHS.colmap_vocab_tree_path)
print("exists=", p.exists(), "size=", (p.stat().st_size if p.exists() else None))
PY
```

只要出现：
- `which colmap` 找不到
- vocab tree `exists=False`

优先修复环境（否则重跑多少次都一样）。

---

## 4. 推荐修复流程（最省时间的“正确重跑顺序”）

> 目标：先修“scene 级一致性”，再修“seq 级帧质量/重叠”，避免盲目在 Step 8 里反复碰运气。

### 4.1 先停掉同 scene 的并行任务（非常关键）

确保同一时刻只有一个任务在写：

- `<scene>/colmap/*`
- `<scene>/images/*`

否则你可能在 Step 8 期间又把 scene 的 database/sparse 覆盖掉，导致偶发失败。

你可以用下面方式“停掉同 scene 的并行任务”（按你的部署方式选一种即可）：

```bash
# A) 如果你用 systemd --user 跑自动化服务（推荐）
systemctl --user stop embodmocap-scene-auto.service 2>/dev/null || true
systemctl --user status embodmocap-scene-auto.service --no-pager || true

# B) 如果你是手工/多终端并行跑：找到并结束同 scene 相关进程
pgrep -af run_stages.py | grep "$SCENE" || true
pgrep -af colmap | grep "$SCENE" || true
```

### 4.2 scene 级：重跑 Step 1 + Step 3（overwrite）

> 按项目常用约定：Step 1 在 `embodmocap_sai150`，Step 3 在 `embodmocap`。

```bash
export CFG=config_fast.yaml
export XLSX_ALL=seq_info_all.xlsx
export XLSX_ONE=seq_info_fix_${SCENE}.xlsx

# 从自动化生成的总表里过滤出当前 scene（避免重跑全量）
python - <<'PY'
import os, pandas as pd
scene = os.environ["SCENE"]
src = os.environ["XLSX_ALL"]
dst = os.environ["XLSX_ONE"]
xl = pd.ExcelFile(src)
df = pd.concat([pd.read_excel(src, sheet_name=s) for s in xl.sheet_names], ignore_index=True)
out = df.loc[df["scene_folder"].astype(str).str.strip() == scene].copy()
if out.empty:
    raise SystemExit(f"No rows found for scene={scene} in {src}")
out.to_excel(dst, index=False)
print(f"Saved {dst}, rows={len(out)}")
PY

conda activate embodmocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 3 --mode overwrite --force_all

# 如果 Step 3 提示缺少 colmap/sparse/0，先重跑 Step 1（sai150）再重跑 Step 3：
# conda activate embodmocap_sai150
# python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite --force_all
# conda activate embodmocap
# python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 3 --mode overwrite --force_all
```

### 4.3 seq 级：重跑 Step 5-8（overwrite）

```bash
conda activate embodmocap_sai150
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 5 --mode overwrite --force_all

# 确认 xlsx 已正确填好 v1_start/v2_start 后再继续
conda activate embodmocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 6-8 --mode overwrite --force_all
```

如果你只想修复某一个 seq：建议先生成/维护一个只包含该 scene/seq 的 xlsx（避免重跑全量）。

---

## 5. 仍然失败时：如何从日志里快速判因（对号入座）

Step 8 的最终报错往往只是“missing outputs”。真正原因一般在更上方日志里（来自 `colmap_human_cam.py` / `regist_seq.sh` / COLMAP 本身）。

下面列出几类高频关键字及对应处理：

### 5.1 `Sparse model image 'xxx' not found in database images table`

含义：`<scene>/colmap/sparse/0/images.txt` 里的 image name，**在** `<scene>/colmap/database.db` 的 `images` 表里找不到。

这通常不是 Step 8 本身的问题，而是 **scene 级 Step 3 的数据库没有正确重建完成**（或 Step 3/8 并发导致 Step 8 复制到了“半成品 db”）。

一个非常典型的信号是：你查到的数据库行数非常小，例如：

```text
num_images=1
num_keypoints=1
num_descriptors=1
```

这意味着 Step 3 的 `colmap feature_extractor` 只处理了 1 张图，数据库虽“非空”但实际不可用，Step 8 必然会报此类 mismatch 错误。

处理：
1) 先做一个 30 秒内可完成的自检（确认是 Step 3 半成品还是路径搞错）：

```bash
SCENE_DIR="$DATA_ROOT/$SCENE"

# sparse 模型里一共多少张图
wc -l "$SCENE_DIR/colmap/image-list.txt" || true

# db 里一共多少张图（至少应与 image-list 同量级）
sqlite3 "$SCENE_DIR/colmap/database.db" "select count(*) from images;"
sqlite3 "$SCENE_DIR/colmap/database.db" "select name from images limit 5;"

# 针对报错里那个具体文件名，检查是否真的不在 db
sqlite3 "$SCENE_DIR/colmap/database.db" "select count(*) from images where name='frame_00193.jpg';"
```

2) 如果确认 db 明显偏小（例如 1/1/1），按第 4 节流程：
- **停止同 scene 的并行任务**（否则可能一直复制到半成品 db）
- 用 `--mode overwrite` 重跑 scene 级 **Step 3**

3) 如果重跑 Step 3 后仍然偏小：
- 说明 `processor/rebuild_colmap.sh` 内部的 COLMAP 命令失败/被 kill 了。请直接看 Step 3 日志，重点 grep：
  - `feature_extractor`
  - `exhaustive_matcher`
  - `Could not read image` / `No such file` / `FreeImage`
- 建议手动跑一次便于定位（会把错误完整打印出来）：

```bash
conda activate embodmocap
bash -x processor/rebuild_colmap.sh "$SCENE_DIR" |& tee "$SCENE_DIR/colmap/rebuild_colmap.debug.log"
```

4) 如果 db 数量正常但仍 mismatch：
- 重点检查 `<scene>/images` 是否被改名/替换过、是否存在大小写/路径前缀差异（db 里存的 name 必须与 sparse/0/images.txt 的 name 字符串一致）

> 更完整的“Step 3 半成品 database 导致 Step 8 mismatch”的排障说明见：`docs/step3_colmap_db_incomplete_zh.md`。

### 5.2 `COLMAP registration did not produce cameras.txt/images.txt/points3D.txt`

含义：`regist_seq.sh` 中某一步提前失败或 `image_registrator` 没写出模型。

处理：
- 先按 3.3 检查 `colmap` 与 vocab tree
- 进入 `<seq>/v1/colmap/` 查看是否存在 `database.db`、以及是否有任何输出文件
- 必要时手动运行（更易看到原始错误）：

```bash
conda activate embodmocap
python processor/colmap_human_cam.py "$SEQ" --proc_v1 --proc_v2 --keyframe_mask
```

### 5.3 `COLMAP parsed empty result ... images=0, points3D=0`

含义：COLMAP 跑完了，但 **没有任何 v1/v2 图像成功注册**。

处理建议（从“最可能”到“更激进”）：
1. 增加切片帧的重叠：修 Step 5/6（更小的 key_frame_distance、正确的 v1_start/v2_start）
2. 增加可用帧数：录制更长、减少模糊、提高纹理（书架/海报/桌面杂物比纯墙面好）
3. 调参：增大 Step 8 的 `colmap_num`、降低 `min_valid_ratio`（需要改 config，然后 `--mode overwrite` 重跑 Step 8）

---

## 6. 给自动化脚本/服务的改进建议（避免“偶发”）

1. **scene 级加锁/串行化**：同一 scene 的 Step 1-3 不要并行跑（文件会互相覆盖）。
2. **记录并持久化日志**：把每个 scene/seq 的 stdout/stderr 存到文件，Step 8 失败时能直接 grep 关键字。
3. **在服务入口显式加载环境**：`conda run -n ...` 比 `conda activate` 更稳（systemd/cron 下）。
4. **环境自检前置**：启动时检查 `colmap`、vocab tree 路径存在性；不满足就直接报错退出。

---

## 7. 相关文件（便于你进一步定位）

- Step 8 主逻辑：`embod_mocap/processor/colmap_human_cam.py`
- COLMAP 注册脚本：`embod_mocap/processor/regist_seq.sh`
- 流水线入口与报错：`embod_mocap/run_stages.py`
