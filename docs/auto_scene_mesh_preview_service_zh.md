# Step0-2 场景 Mesh 自动化 + Viser 预览（服务化）

本页目标：你把新的录制数据（scene 文件夹或 zip 包）上传到 `DATA_ROOT=../datasets/my_capture` 后，不用手工跑命令，后台服务会自动：

1.（可选）导入 `DATA_ROOT/` 根目录下的新 zip 为一个 scene
2. 自动生成/覆盖 Step0 总表 `seq_info_all.xlsx`
3. 自动跑 Step1（`transforms.json`）与 Step2（`mesh_raw.ply`/`mesh_simplified.ply`）
4. 通过 Viser 在浏览器里下拉选择不同 scene 并查看 mesh（优先 `mesh_raw.ply`）

> 说明：本自动化只覆盖 **Step0/1/2**（场景建图预览）。人体相关 Step4+ 不在这里跑。

---

## 0. 前置条件

1. 你在服务器上能按手册正常跑通 Step1/2（两个 conda 环境都可用）：
   - `embodmocap_sai150`：Step1（sai-cli / spectacularAI）
   - `embodmocap`：Step2（unproj_scene + open3d 等）
2. 你使用的代码目录为 `~/EmbodMocap_dev/embod_mocap`（即包含 `run_stages.py` 的那个目录）

---

## 1. 手工启动（先验证服务脚本可用）

### 1.1 启动自动化后台（前台运行观察日志）

在服务器执行：

```bash
cd ~/EmbodMocap_dev/embod_mocap

# 该脚本会循环扫描 DATA_ROOT，自动写 seq_info_all.xlsx，并补跑缺失的 Step1/2
conda run -n embodmocap python tools/auto_scene_mesh_service.py \
  --data_root ../datasets/my_capture \
  --config config_fast.yaml \
  --xlsx_out seq_info_all.xlsx \
  --auto_import_scene_zips \
  --ensure_seq0 \
  --auto_extract_seq_zips \
  --poll_interval 30
```

### 1.2 启动 Viser 预览（可在 GUI 下拉切换 scene）

在服务器另开一个终端执行：

```bash
cd ~/EmbodMocap_dev/embod_mocap
conda run -n embodmocap python tools/preview_scene_meshes_viser.py \
  --data_root ../datasets/my_capture \
  --mesh_mode prefer_raw \
  --auto_refresh_seconds 10 \
  --host 127.0.0.1 \
  --port 8080
```

---

## 2. 本地电脑访问（SSH 端口转发）

在你的本地电脑执行（推荐后台）：

```bash
ssh -p 22 -Nf -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

然后本地浏览器打开：

```text
http://127.0.0.1:18080
```

---

## 3. 数据上传约定（推荐）

自动化服务支持两种常用输入方式：

### 3.1 方式 A：直接上传 scene 目录

上传后的结构（示例）：

```text
datasets/my_capture/<SCENE>/
  calibration.json
  data.jsonl
  data.mov
  frames2/
  metadata.json
  seq0/
    (可为空；仅用于让 Step0 扫描到该 scene)
```

服务会自动补跑：
- Step1：生成 `<SCENE>/transforms.json`
- Step2：生成 `<SCENE>/mesh_raw.ply` / `<SCENE>/mesh_simplified.ply`

### 3.2 方式 B：把 zip 丢到 `DATA_ROOT/` 根目录（自动导入）

把一个新的 `*.zip` 上传到：

```text
datasets/my_capture/<something>.zip
```

服务会尝试把它导入成一个新的 scene 目录（并把原 zip 移到 `seq0/_imports/` 下保留）。

> 该 zip 需要包含（或某个子目录包含）标准的 5 个原始输入：`calibration.json`、`data.jsonl`、`data.mov`、`frames2/`、`metadata.json`。

### 3.3 seq 下的 recording_*.zip（可选自动解压）

如果你还上传了双机位的 `recording_*.zip` 到 `seq0/`，并启用了 `--auto_extract_seq_zips`，服务会在 `raw1/raw2` 缺失时自动解压：

```text
datasets/my_capture/<SCENE>/seq0/
  recording_xxx.zip
  recording_yyy.zip
  raw1/  (自动生成)
  raw2/  (自动生成)
```

原 zip 会保留在 `seq0/` 下，不会删除。

---

## 4. systemd（推荐：用户级服务，无需 sudo）

下面给出一个可复制的模板。你只需要改两处：
1) `WorkingDirectory`：你的代码目录
2) `conda run -n ...`：你的 conda 路径/环境名（如果系统找不到 `conda`）

### 4.1 自动化服务（Step0/1/2）

创建文件：

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/embodmocap-scene-auto.service <<'UNIT'
[Unit]
Description=EmbodMocap Auto Step0-2 Builder
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/EmbodMocap_dev/embod_mocap
Restart=always
RestartSec=5

# 如果系统找不到 conda，把 conda 改成绝对路径，例如：
# ExecStart=%h/miniconda3/bin/conda run -n embodmocap python tools/auto_scene_mesh_service.py ...
ExecStart=conda run -n embodmocap python tools/auto_scene_mesh_service.py --data_root ../datasets/my_capture --config config_fast.yaml --xlsx_out seq_info_all.xlsx --auto_import_scene_zips --ensure_seq0 --auto_extract_seq_zips --poll_interval 30

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now embodmocap-scene-auto.service
```

查看日志：

```bash
journalctl --user -u embodmocap-scene-auto.service -f
```

### 4.2 Viser 服务

创建文件：

```bash
cat > ~/.config/systemd/user/embodmocap-viser.service <<'UNIT'
[Unit]
Description=EmbodMocap Viser Scene Mesh Viewer
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/EmbodMocap_dev/embod_mocap
Restart=always
RestartSec=5
ExecStart=conda run -n embodmocap python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --mesh_mode prefer_raw --auto_refresh_seconds 10 --host 127.0.0.1 --port 8080

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now embodmocap-viser.service
```

查看日志：

```bash
journalctl --user -u embodmocap-viser.service -f
```

---

## 5. 常见问题

1) **服务一直在重试某个 scene**  
   通常是输入缺少 `calibration.json/data.jsonl/data.mov/frames2/metadata.json` 或 SAI 失败。先看该 scene 下是否有 `error.txt`，再手工单跑一次 Step1/2 定位。

2) **Viser 下拉里看不到 scene**  
   该 viewer 默认只列出已经生成 `mesh_raw.ply` 或 `mesh_simplified.ply` 的 scene。确认 Step2 是否生成 mesh；必要时点一下 GUI 的 “Refresh Scenes”。
