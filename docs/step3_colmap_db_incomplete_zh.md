# Step 3 生成了 `database.db` 但仍然失败：COLMAP 数据库不完整导致 Step 8 报 `Sparse model image ... not found`

本文描述一种非常“迷惑”的故障：你已经重跑了 scene 级 **Step 3（rebuild_colmap）**，`colmap/database.db` 也确实存在、甚至 sqlite3 查询也显示“非空”，但 **Step 8 仍然失败**，并出现：

```text
RuntimeError: Sparse model image 'frame_00193.jpg' not found in database images table
```

这几乎总是因为：**Step 3 只跑了一小部分（半成品/被中断/命令失败），导致 database 只包含极少数图片的特征**。

---

## 1. 关键结论（先看这个）

当你看到：

- `wc -l <scene>/colmap/image-list.txt` 结果是几十/几百（例如 193）
- 但 `sqlite3 <scene>/colmap/database.db "select count(*) from images;"` 结果非常小（例如 1）

则可判定：**Step 3 的 `colmap feature_extractor` 没有成功处理完 `image-list.txt` 里列出的图片**。

此时 Step 8 会在 `processor/regist_seq.sh` 的“稀疏模型 ID remap”阶段直接失败，因为 sparse 模型里引用的 image name（例如 `frame_00193.jpg`）在 db 的 `images` 表里根本不存在。

这与 Open3D 坐标系无关：报错发生在 sqlite 读 `images` 表阶段，属于 COLMAP 数据/执行问题。

---

## 2. 30 秒自检：确认是不是“半成品数据库”

在服务器上：

```bash
cd ~/EmbodMocap_dev/embod_mocap
export DATA_ROOT=../datasets/my_capture
export SCENE=scene_0014
export SCENE_DIR="$DATA_ROOT/$SCENE"

# 1) 稀疏模型期望的图片数量（来自 sparse/0/images.txt 导出的 image-list）
wc -l "$SCENE_DIR/colmap/image-list.txt" || true

# 2) Step 3 拷贝到 colmap/images 的实际图片数量
ls -1 "$SCENE_DIR/colmap/images" 2>/dev/null | wc -l || true

# 3) COLMAP 数据库里注册的图片数量（应与 image-list 同量级）
sqlite3 "$SCENE_DIR/colmap/database.db" "select count(*) from images;"
sqlite3 "$SCENE_DIR/colmap/database.db" "select name from images limit 5;"
sqlite3 "$SCENE_DIR/colmap/database.db" "select count(*) from images where name='frame_00193.jpg';"
```

典型坏例子（你的 case）：

- `image-list.txt` = 193 行
- db `images` 只有 1 行（例如只看到 `frame_00001.jpg`）
- 查询 `frame_00193.jpg` 为 0

这就解释了 Step 8 的报错。

---

## 3. 为什么会出现“只处理了 1 张图”的 Step 3

常见原因（按概率排序）：

1) **COLMAP 读图失败 / 某张 jpg 损坏**  
   `colmap feature_extractor` 通常会在遇到不可读图片时直接退出（或返回非 0）。

2) **进程被中断或被系统 kill**  
   例如 OOM、手动 Ctrl+C、被 systemd/脚本超时杀掉。

3) **并发写入导致复制到半成品 db**  
   如果同时有多个任务在写同一个 `<scene>/colmap/*`，很容易出现：
   - Step 3 正在写数据库
   - 另一个任务启动 Step 8/或再次 Step 3，读到/覆盖到半成品状态

4) **脚本没有 fail-fast，失败被“吞掉”**  
   若 shell 脚本未 `set -e`，或上层执行器未把非零退出当作 fatal，就可能留下半成品 `database.db`，并被误认为“已生成”。

> 实际排查经验：如果你是通过 `run_stages.py` 跑 Step 3，而上层只做了“文件存在性”检查，那么即使 `rebuild_colmap.sh` 中途失败，也可能留下一个只有 1 张图的 `database.db`。  
> 这种情况下，**优先看 Step 3 日志**（`feature_extractor` 是否完整跑完），而不要只看 `database.db` 是否存在。

---

## 4. 怎么修（推荐路径）

### 4.1 先确保没有同 scene 并发任务

如果你用 systemd --user 跑自动化：

```bash
systemctl --user stop embodmocap-scene-auto.service 2>/dev/null || true
systemctl --user stop sdr-incoming-bridge.service 2>/dev/null || true
```

如果你是多终端手工跑：

```bash
pgrep -af run_stages.py | grep "$SCENE" || true
pgrep -af colmap | grep "$SCENE" || true
```

### 4.2 用 debug 日志重跑一次 rebuild_colmap（最推荐）

```bash
conda activate embodmocap
bash -x processor/rebuild_colmap.sh "$SCENE_DIR" |& tee "$SCENE_DIR/colmap/rebuild_colmap.debug.log"
```

然后在日志里重点找：

- `feature_extractor`
- `Could not read image` / `No such file` / `FreeImage`
- 任何 `ERROR` 或非零退出

### 4.3 如果怀疑是“某张坏图”

你可以先用 OpenCV 快速扫描 `scene/images`（注意：COLMAP 用 FreeImage/自身 reader，OpenCV 能读不代表 COLMAP 一定能读，但能先过滤一批明显坏图）：

```bash
python - <<'PY'
import os, sys, cv2
scene_dir = os.environ.get("SCENE_DIR")
if not scene_dir:
    raise SystemExit("Please export SCENE_DIR=... first")
img_dir = os.path.join(scene_dir, "images")
bad = []
for name in sorted(os.listdir(img_dir)):
    if not name.lower().endswith((".jpg", ".jpeg", ".png")):
        continue
    p = os.path.join(img_dir, name)
    im = cv2.imread(p, cv2.IMREAD_COLOR)
    if im is None or im.size == 0:
        bad.append(name)
print("bad_count=", len(bad))
print("bad_examples=", bad[:20])
PY
```

如果发现坏图：重新导出/重录/重传该 scene，或修复损坏文件后再重跑 Step 3。

---

## 5. 如何确认“不是你改了 Open3D 坐标系导致的”

这类报错发生在 COLMAP 数据库层（sqlite），与 Open3D/坐标系无关。  
如果你仍担心代码改动，可在服务器上直接对比 origin/main：

```bash
git fetch origin
git diff --name-only origin/main..HEAD

# 重点看 COLMAP 相关脚本
git diff origin/main..HEAD -- embod_mocap/processor/rebuild_colmap.sh embod_mocap/processor/regist_seq.sh
```

若你确实在自己的分支里改动过这些脚本，且怀疑有副作用，可以临时回退对比：

```bash
git checkout origin/main -- embod_mocap/processor/rebuild_colmap.sh embod_mocap/processor/regist_seq.sh
```

（注意：这会覆盖本地改动，请先确认/备份。）

---

## 6. 关联文档

- Step 8 总体排障：`docs/step8_cameras_colmap_missing_zh.md`
- 上传命名 & 桥接链路：`docs/拍摄上传命名对齐与自动化处理部署指南.md`
- 自动化服务运维命令：`docs/automation_services_ops_zh.md`
