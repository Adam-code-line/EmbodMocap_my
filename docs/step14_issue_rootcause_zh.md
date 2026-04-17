# Step14 报错原因分析（基于 `docs/step13-15.md`）

## 结论（先说结论）

`Step 14` 的报错**不是**由于“之前修改了 Open3D 坐标系”导致的；从日志来看，它是一个**由 Step 13 上游失败引发的级联错误**：

- `Step 13` 在处理 `v2` 时因为 **RGB 图片文件缺失**（`v2_0750.jpg` 找不到）而中断；
- 因此 `v2/pointcloud.ply` **没有被生成**；
- `Step 14` 在 `--chamfer` 分支里尝试读取 `v2/pointcloud.ply`，Open3D 读不到点云，导致后续对点集做 `min()` 时报 **zero-size array**；
- `Step 15` 依赖 `Step 14` 的输出（如 `v1/cameras.npz` 等），因此继续报“文件不存在”。

换句话说：**Step 14 报错的直接原因是输入文件缺失（或无法打开），而不是坐标系变换。**

---

## 从日志逐段定位（Step 13 → Step 14 → Step 15）

### Step 13：`v2` 失败，导致 `v2/pointcloud.ply` 没生成

`docs/step13-15.md` 里 Step 13 的关键两行是：

- `v1 pointcloud saved to ../datasets/my_capture/scene_0014/seq0/v1/pointcloud.ply`（说明 `v1` 点云生成成功）
- 随后 `v2` 报错：
  - `FileNotFoundError: .../v2/images/v2_0750.jpg`

这意味着在 `v2` 的 unproject 过程中，代码需要读取某一帧的 RGB（`v2_0750.jpg`），但实际路径下不存在该文件，于是程序提前退出，**自然也就不会写出**：

- `../datasets/my_capture/scene_0014/seq0/v2/pointcloud.ply`

#### 为什么 Step13 能产出 `v1/pointcloud.ply`，但产不出 `v2/pointcloud.ply`？

可以把 Step13 理解成“先跑 v1，再跑 v2”。在你的日志里：

- `v1` 阶段已经成功完成并写出了 `v1/pointcloud.ply`；
- 切到 `v2` 阶段时，在读取 RGB（`v2_0750.jpg`）这一步就异常退出，所以 **v2 的点云还没走到保存那一步就被中断了**。

更进一步，`v2_0750.jpg` 缺失通常来自下面几类原因（按常见程度排序）：

1) **v2 视角的抽帧/导出不完整，导致帧号不齐**

- 例如 `v1/images` 有 `v1_0750.jpg`，但 `v2/images` 没有对应的 `v2_0750.jpg`；
- 常见于：录制/上传过程中 v2 丢帧、提前结束、导出脚本中断、只导出了部分帧等。

2) **`keyframes.json` 的帧号是按 v1 的帧数生成的，但 v2 实际帧数更少或帧号不连续**

- 从日志看：`unproj field: 26 frames` 且缺的正好是 `0750`，这非常像 `stride=30` 时的序列（`0, 30, 60, ..., 750`）；
- 如果你的 `keyframes.json` 是通过 `embod_mocap/processor/generate_keyframes.py` 生成的，它会用 `v1/images` 的图片数量作为 `num_frames` 来生成 `unproj` 帧号（即默认认为 v1/v2 的帧范围一致）；当 v2 图片不足或缺号时，Step13 就会在 v2 读图阶段报 `FileNotFoundError`。

3) **文件命名/后缀不一致**

- 例如 v2 实际是 `v2_0750.png`、`v2_750.jpg`、或存放在别的目录，但 `transforms.json`/代码里写死要找 `v2_0750.jpg`。

你可以用下面 3 个最小检查来快速确认属于哪一类：

- `v2/images/` 里是否真的缺 `v2_0750.jpg`（以及 v2 的最大帧号是多少）
- `keyframes.json` 的 `unproj` 列表里是否包含 `750`
- `transforms.json`（v2）里对应帧的 `file_path` 是否指向 `images/v2_0750.jpg`（以及扩展名是否一致）

### Step 14：Open3D 读不到 `v2/pointcloud.ply`，点数组为空

Step 14 的关键日志是：

- `RPly: Unable to open file`
- `[Open3D WARNING] Read PLY failed: unable to open file: .../v2/pointcloud.ply`
- 随后 Python 报：
  - `ValueError: zero-size array to reduction operation minimum which has no identity`

这组信息组合起来非常明确：**点云文件没读到（通常是不存在或权限/路径问题），导致 pointcloud 的 points 为空数组**，后面再做：

- `np.asarray(pc_scene_human2_o3d.points)[:, 2].min()`

就会触发 `zero-size array`。

### Step 15：缺少 `v1/cameras.npz`，属于级联错误

Step 15 报：

- `FileNotFoundError: .../v1/cameras.npz`

这通常是因为 Step 14 没跑完/没产出相机优化结果（或前面更早步骤未产出），所以 Step 15 找不到它依赖的中间产物。

---

## 为什么这不像“Open3D 坐标系修改”导致的问题

“修改 Open3D 坐标系/坐标轴约定”这类改动，常见影响是：

- 点云/相机/人体在可视化里发生翻转、旋转、上下颠倒；
- Z 轴当作高度轴时高度判断不对（例如应当用 Y 却用了 Z）；
- 优化结果出现系统性偏差（对齐方向错误、尺度漂移等）。

但它**通常不会**导致下面这种错误形态：

- `Read PLY failed: unable to open file`（这是**文件打开失败**，不是“点坐标不对”）
- `zero-size array ... min()`（这是**输入点集为空**，不是“坐标系导致点云方向错”）

就本日志而言，Step 14 在进行任何“基于坐标轴的几何逻辑”之前，就已经因为点云文件无法读取而失败，所以与坐标系改动没有直接因果关系。

---

## 建议的排查/修复顺序（按依赖从上到下）

1) 先修复 Step 13 的 `v2` 图片缺失问题（这是根因）

- 检查路径：`../datasets/my_capture/scene_0014/seq0/v2/images/`
- 确认是否存在 `v2_0750.jpg`
  - 如果存在但扩展名不同（如 `.png`），需要统一命名或调整代码读取逻辑
  - 如果文件确实不存在，说明 `keyframes.json` 里引用了一个不存在的帧号（750）

2) 重新跑 Step 13，确保产物齐全

至少要看到：

- `.../v1/pointcloud.ply`
- `.../v2/pointcloud.ply`

3) 再跑 Step 14（优化 human view cameras）

如果仍然报错，再看是否是“点云为空但文件存在”的情况；那时才需要进一步讨论是否有坐标系/深度反投影逻辑问题。

4) 最后跑 Step 15（依赖 Step 14 产物）

---

## 可选：让 Step 14 失败得更“早、更清楚”

目前 Step 14 的报错最终落在 `min()` 上，信息不够直接。更友好的做法是：

- 在读取 `v1/v2/pointcloud.ply` 之后，显式检查文件是否存在、点数是否为 0；
- 若缺失则直接抛出带路径的异常，并提示“先完成 Step 13”。

如果你希望我把这个检查补到代码里（例如 `embod_mocap/processor/optim_human_cam.py`），我可以直接改一版，让错误信息更可读，避免误判为坐标系问题。
