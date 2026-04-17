# Step0-2 场景 Mesh 自动化 + Viser 预览（服务化）

本页目标：你把新的录制数据（scene 文件夹或 zip 包）上传到 `DATA_ROOT=../datasets/my_capture` 后，不用手工跑命令，后台服务会自动：

1.（可选）导入 `DATA_ROOT/` 根目录下的新 zip 为一个 scene
2. 自动生成/覆盖 Step0 总表 `seq_info_all.xlsx`
3. 自动跑 Step1（`transforms.json`）与 Step2（`mesh_raw.ply`/`mesh_simplified.ply`）
4. 通过 Viser 在浏览器里下拉选择不同 scene 并查看 mesh（优先 `mesh_raw.ply`）

> 说明：本文默认介绍 **Step0/1/2**（场景建图预览）的服务化。  
> 如果你要按命名规范上传 Spectacular Rec 的 zip，并自动跑带人的 **Step0-15**，请使用 `tools/auto_spectacular_rec_service.py`（见 1.1B 与第 3 节）。

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

### 1.1B 启动全流程自动化（Spectacular Rec 命名上传 + human Step0-15）

在服务器执行（建议先看命名规范：`docs/spectacular_rec_upload_naming_zh.md`）：

```bash
cd ~/EmbodMocap_dev/embod_mocap

# 该脚本会：
# - 扫描 DATA_ROOT/_incoming 下新上传的 zip（按文件名解析 scene/type/seq/cam）
# - scene-only：自动补跑 Step1/2（transforms + mesh）
# - human：当同一 scene+seq 的双视角齐全后，自动跑 Step1 + Step2-4 + Step5 + Step6-15
conda run -n embodmocap python tools/auto_spectacular_rec_service.py \
  --data_root ../datasets/my_capture \
  --incoming _incoming \
  --config config_fast.yaml \
  --conda conda \
  --env_main embodmocap \
  --env_sai embodmocap_sai150 \
  --mode skip \
  --poll_interval 30
```

常用开关：
- 只想“整理目录/写 xlsx”，不想自动跑流程：加 `--no_auto_run`
- 只跑场景 mesh（跳过 human）：加 `--skip_human_steps`

### 1.2 启动 Viser 预览（可在 GUI 下拉切换 scene）

在服务器另开一个终端执行：

```bash
cd ~/EmbodMocap_dev/embod_mocap
conda run -n embodmocap python tools/preview_scene_meshes_viser.py \
  --data_root ../datasets/my_capture \
  --mesh_mode prefer_raw \
  --auto_refresh_seconds 10 \
  --host 127.0.0.1 \
  --port 8080 \
  --print_share_url
```

> 提示（已扩展）：同一个 `preview_scene_meshes_viser.py` 现在同时支持两类预览：
> 1) **仅场景 Mesh**：查看 `mesh_raw.ply` / `mesh_simplified.ply`（不依赖 `optim_params.npz`）。
> 2) **带人的渲染（SMPL + 场景）**：如果 `scene/seq*/optim_params.npz` 存在，可在 GUI 的 `Human Demo (SMPL + Scene)` 里选择 `Sequence` 并点击 `Load Human`，然后用 `Frame`/`Play` 进行播放。
>
> Human Demo 前提：
> - `optim_params.npz` 已生成（通常 Step15 后才有）
> - SMPL 资产已下载到仓库根目录的 `body_models/smpl`（可执行 `bash embod_mocap/tools/download_body_models.sh`）
>
> 性能建议：如果很卡，可重启时加参数例如：`--human_stride 2 --human_max_frames 600 --human_mesh_level 1`。

如果你的 `viser` 版本支持分享，你会在终端/日志里看到类似 `[INFO] Share URL: ...` 的链接；也可以在 GUI 的 `Actions -> Get Share URL` 按钮点击生成。  
注意：share 链接可能会因**服务重启/会话过期**变成 404；如果要一个更“稳定”的入口，建议用下面的“公网 IP:端口直连”（把 host 改成 `0.0.0.0` 并放行端口）。

---

## 2. 外部访问 Viser（公网直连 / SSH 端口转发）

### 2.1 方案 A：公网 IP + 端口直连（无需 SSH，最简单）

适用场景：你们服务器有公网 IP（或已做端口映射），并且你愿意在防火墙/安全组放行端口。

> 你已经部署了 `embodmocap-viser.service` 的话，按下面 **三段** 复制运行即可（默认端口 8080）：
> 1) 改监听地址 -> 2) 放行端口 -> 3) 发访问链接

**(1/4) 把 Viser 监听地址改为 0.0.0.0**  
- 前台手动启动：把 `--host 127.0.0.1` 改成 `--host 0.0.0.0` 即可。  
- 已用 systemd 跑 `embodmocap-viser.service`（推荐）：用下面命令一键替换并重启。

```bash
VISER_UNIT="$HOME/.config/systemd/user/embodmocap-viser.service"

# 如果原来是 --host 127.0.0.1，就替换为 0.0.0.0（让外部能访问）
sed -i 's/--host 127\.0\.0\.1/--host 0.0.0.0/g' "$VISER_UNIT"

systemctl --user daemon-reload
systemctl --user restart embodmocap-viser.service
systemctl --user status embodmocap-viser.service --no-pager
```

> 想恢复“仅本机访问”，把 `0.0.0.0` 改回 `127.0.0.1` 并关闭端口即可。

**(2/4) 放行端口（防火墙 + 云安全组）**  
以 `8080` 为例（如果你改了端口，把 8080 换成你的端口）：

```bash
# Ubuntu/Debian（ufw）
sudo ufw allow 8080/tcp
sudo ufw status | grep 8080 || true
```

```bash
# CentOS/RHEL（firewalld）
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports | grep -E '(^| )8080/tcp( |$)' || true
```

并在云厂商控制台（安全组/防火墙）里允许入站 `TCP:8080`。

> 注意：Viser 默认无鉴权。请按需放行端口（例如只放行固定 IP）。

**(3/4) 确认服务真的在监听**

```bash
ss -lntp | grep ':8080' || true
journalctl --user -u embodmocap-viser.service -n 50 --no-pager
```

**(4/4) 让别人用浏览器打开**

```text
http://<你的公网IP>:8080
```

> 例子：如果你常用的公网域名是 `1080.alpen-y.top`（例如在 `spatial_data_recorder/.env` 里用过），
> 那么这里的访问链接就是：`http://1080.alpen-y.top:8080`。

### 2.2 方案 B：本地电脑访问（SSH 端口转发，更安全）

在你的本地电脑执行（推荐后台）：

```bash
ssh -p 22 -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

然后本地浏览器打开：

```text
http://127.0.0.1:18080
```

> 如果你把 Viser 服务端口改成了 `8081`（例如避免与 demo 的可视化冲突），记得同步改 SSH 转发：
>
> `ssh -p 22 -L 18081:127.0.0.1:8081 <user>@<server>`

---

## 3. 数据上传约定（推荐）

自动化服务支持两种常用输入方式：

> 如果你希望按“命名规范 + 自动跑 Step0-15（带人）”的方式上传，请改用：
> - 命名规范：`docs/spectacular_rec_upload_naming_zh.md`
> - 服务脚本：`embod_mocap/tools/auto_spectacular_rec_service.py`
> - 上传目录：`datasets/my_capture/_incoming/`
>
> ⚠️ 注意：带 `__scene=...__type=...` 这种 token 的 zip **不要**直接丢到 `DATA_ROOT/` 根目录，
> 否则可能被 `--auto_import_scene_zips` 误导入成奇怪的 scene 名。请统一放到 `_incoming/`。

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

### 4.0 一键生成并启动（推荐：自动探测 conda 绝对路径）

`systemd --user` 默认不会加载你的 `.bashrc/.zshrc`，所以服务里写 `ExecStart=conda ...` 很容易报：
`Failed at step EXEC spawning conda` / `status=203/EXEC`。

下面脚本会自动探测 `conda` 的绝对路径，然后写入并启动两个 user service（Step0-2 自动化 + Viser）：

```bash
set -e

EMBOD_DIR="$HOME/EmbodMocap_dev/embod_mocap"     # 需要的话改这里
DATA_ROOT="../datasets/my_capture"              # 需要的话改这里（相对 EMBOD_DIR）
VISER_PORT="8080"

# 1) 找 conda 绝对路径（优先用 conda info --base；不行就猜常见安装位置）
CONDA_EXE=""
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
  [ -x "$CONDA_BASE/bin/conda" ] && CONDA_EXE="$CONDA_BASE/bin/conda"
  [ -z "$CONDA_EXE" ] && [ -x "$CONDA_BASE/condabin/conda" ] && CONDA_EXE="$CONDA_BASE/condabin/conda"
fi
if [ -z "$CONDA_EXE" ]; then
  for p in "$HOME/miniconda3/bin/conda" "$HOME/Miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/Miniforge3/bin/conda" "$HOME/mambaforge/bin/conda" "$HOME/Mambaforge/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/Anaconda3/bin/conda" "/opt/conda/bin/conda"; do
    [ -x "$p" ] && CONDA_EXE="$p" && break
  done
fi
if [ -z "$CONDA_EXE" ]; then
  echo "ERROR: 找不到 conda。请手动把 CONDA_EXE=/abs/path/to/conda 然后重跑本段脚本。" >&2
  exit 1
fi
echo "[INFO] Using conda: $CONDA_EXE"

if [ ! -d "$EMBOD_DIR" ]; then
  echo "ERROR: 找不到代码目录: $EMBOD_DIR （按需修改 EMBOD_DIR）" >&2
  exit 1
fi

# 2) 停服务，避免一直重启刷日志
systemctl --user stop embodmocap-scene-auto.service embodmocap-viser.service 2>/dev/null || true
systemctl --user reset-failed embodmocap-scene-auto.service embodmocap-viser.service 2>/dev/null || true

mkdir -p "$HOME/.config/systemd/user"

# 3) 写入并启动 Step0/1/2 自动化服务
cat > "$HOME/.config/systemd/user/embodmocap-scene-auto.service" <<UNIT
[Unit]
Description=EmbodMocap Auto Step0-2 Builder
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
# 注意：auto_scene_mesh_service.py 内部还会调用 conda 跑 Step1/2，所以这里同时传 --conda
# 仅场景 mesh（Step0-2）：
ExecStart=$CONDA_EXE run -n embodmocap python tools/auto_scene_mesh_service.py --data_root $DATA_ROOT --config config_fast.yaml --xlsx_out seq_info_all.xlsx --auto_import_scene_zips --ensure_seq0 --auto_extract_seq_zips --poll_interval 30 --conda $CONDA_EXE --lock_dir _locks --log_dir _logs/auto_scene_mesh_service
# 全流程（Spectacular Rec 命名上传 + human Step0-15）替换为：
# ExecStart=$CONDA_EXE run -n embodmocap python tools/auto_spectacular_rec_service.py --data_root $DATA_ROOT --incoming _incoming --config config_fast.yaml --conda $CONDA_EXE --env_main embodmocap --env_sai embodmocap_sai150 --mode skip --poll_interval 30
#
# 全流程（Spectacular Rec 命名上传 + human Step0-15）：把上面 ExecStart 替换为下面这一行：
# ExecStart=$CONDA_EXE run -n embodmocap python tools/auto_spectacular_rec_service.py --data_root $DATA_ROOT --incoming _incoming --config config_fast.yaml --conda $CONDA_EXE --env_main embodmocap --env_sai embodmocap_sai150 --mode skip --poll_interval 30

[Install]
WantedBy=default.target
UNIT

# 4) 写入并启动 Viser 服务
cat > "$HOME/.config/systemd/user/embodmocap-viser.service" <<UNIT
[Unit]
Description=EmbodMocap Viser Scene Mesh Viewer
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
# 默认仅本机访问：--host 127.0.0.1；如果要公网直连，把它改成 0.0.0.0（并放行端口）
ExecStart=$CONDA_EXE run -n embodmocap python tools/preview_scene_meshes_viser.py --data_root $DATA_ROOT --mesh_mode prefer_raw --auto_refresh_seconds 10 --host 127.0.0.1 --port $VISER_PORT

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now embodmocap-scene-auto.service embodmocap-viser.service
systemctl --user status embodmocap-scene-auto.service embodmocap-viser.service --no-pager
```

查看日志（需要时）：`journalctl --user -u embodmocap-scene-auto.service -f` / `journalctl --user -u embodmocap-viser.service -f`

#### 4.0.1 分段执行（避免一次性跑整段脚本）

如果你担心一次性启动自动化服务会瞬间触发大量 Step1/2 任务导致 SSH 断连，可以按下面 **分段** 来做（建议先只启动 Viser，确认没问题后再启动自动化服务）。

**(1/7) 设置变量 + 自动找到 conda 绝对路径**

```bash
EMBOD_DIR="$HOME/EmbodMocap_dev/embod_mocap"     # 需要的话改这里
DATA_ROOT="../datasets/my_capture"              # 需要的话改这里（相对 EMBOD_DIR）
VISER_PORT="8080"

CONDA_EXE=""
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
  [ -x "$CONDA_BASE/bin/conda" ] && CONDA_EXE="$CONDA_BASE/bin/conda"
  [ -z "$CONDA_EXE" ] && [ -x "$CONDA_BASE/condabin/conda" ] && CONDA_EXE="$CONDA_BASE/condabin/conda"
fi
if [ -z "$CONDA_EXE" ]; then
  for p in "$HOME/miniconda3/bin/conda" "$HOME/Miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/Miniforge3/bin/conda" "$HOME/mambaforge/bin/conda" "$HOME/Mambaforge/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/Anaconda3/bin/conda" "/opt/conda/bin/conda"; do
    [ -x "$p" ] && CONDA_EXE="$p" && break
  done
fi

echo "[INFO] EMBOD_DIR=$EMBOD_DIR"
echo "[INFO] DATA_ROOT=$DATA_ROOT"
echo "[INFO] CONDA_EXE=$CONDA_EXE"
ls -l "$CONDA_EXE"
```

**(2/7) 停止旧服务（避免一直重启刷日志）**

```bash
systemctl --user stop embodmocap-scene-auto.service embodmocap-viser.service 2>/dev/null || true
systemctl --user reset-failed embodmocap-scene-auto.service embodmocap-viser.service 2>/dev/null || true
mkdir -p "$HOME/.config/systemd/user"
```

**(3/7) 写入 Step0-2 自动化 service**

```bash
cat > "$HOME/.config/systemd/user/embodmocap-scene-auto.service" <<UNIT
[Unit]
Description=EmbodMocap Auto Step0-2 Builder
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
ExecStart=$CONDA_EXE run -n embodmocap python tools/auto_scene_mesh_service.py --data_root $DATA_ROOT --config config_fast.yaml --xlsx_out seq_info_all.xlsx --auto_import_scene_zips --ensure_seq0 --auto_extract_seq_zips --poll_interval 30 --conda $CONDA_EXE --lock_dir _locks --log_dir _logs/auto_scene_mesh_service

[Install]
WantedBy=default.target
UNIT
```

**(4/7) 写入 Viser service**

```bash
cat > "$HOME/.config/systemd/user/embodmocap-viser.service" <<UNIT
[Unit]
Description=EmbodMocap Viser Scene Mesh Viewer
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
# 默认仅本机访问：--host 127.0.0.1；如果要公网直连，把它改成 0.0.0.0（并放行端口）
ExecStart=$CONDA_EXE run -n embodmocap python tools/preview_scene_meshes_viser.py --data_root $DATA_ROOT --mesh_mode prefer_raw --auto_refresh_seconds 10 --host 127.0.0.1 --port $VISER_PORT

[Install]
WantedBy=default.target
UNIT
```

**(5/7) 让 systemd 重新加载 unit**

```bash
systemctl --user daemon-reload
```

**(6/7) 先启动 Viser（推荐）**

```bash
systemctl --user enable --now embodmocap-viser.service
systemctl --user status embodmocap-viser.service --no-pager
journalctl --user -u embodmocap-viser.service -n 50 --no-pager
```

**(7/7) 再启动自动化服务（建议先 start，确认稳定后再 enable）**

```bash
systemctl --user start embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
journalctl --user -u embodmocap-scene-auto.service -n 100 --no-pager

# 确认没问题后，再设置开机/登录自启
systemctl --user enable embodmocap-scene-auto.service
```

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
# 注意：auto_scene_mesh_service.py 内部还会调用 conda 跑 Step1/2，所以建议同时传 --conda（同一个绝对路径）
ExecStart=conda run -n embodmocap python tools/auto_scene_mesh_service.py --data_root ../datasets/my_capture --config config_fast.yaml --xlsx_out seq_info_all.xlsx --auto_import_scene_zips --ensure_seq0 --auto_extract_seq_zips --poll_interval 30 --conda conda --lock_dir _locks --log_dir _logs/auto_scene_mesh_service
# 全流程（Spectacular Rec 命名上传 + human Step0-15）替换为：
# ExecStart=conda run -n embodmocap python tools/auto_spectacular_rec_service.py --data_root ../datasets/my_capture --incoming _incoming --config config_fast.yaml --conda conda --env_main embodmocap --env_sai embodmocap_sai150 --mode skip --poll_interval 30

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
# 默认仅本机访问：--host 127.0.0.1；如果要公网直连，把它改成 0.0.0.0（并放行端口）
ExecStart=conda run -n embodmocap python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --mesh_mode prefer_raw --auto_refresh_seconds 10 --host 127.0.0.1 --port 8080
# 如果你希望服务启动时就打印 share 链接，额外加： --print_share_url

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

#### 4.2.1 让服务启动时自动打印 Share URL（发给别人直接用）

前提：你的 `viser` 版本需要支持 share（本仓库的 `preview_scene_meshes_viser.py` 已内置 `--print_share_url` 与 GUI 的 `Get Share URL` 按钮）。

如果你已经用 systemd 跑起来了，按下面指令给 `ExecStart` 追加 `--print_share_url`，然后重启服务即可：

```bash
VISER_UNIT="$HOME/.config/systemd/user/embodmocap-viser.service"
grep -q -- '--print_share_url' "$VISER_UNIT" || \
  sed -i '/^ExecStart=.*preview_scene_meshes_viser\.py/ s/$/ --print_share_url/' "$VISER_UNIT"

systemctl --user daemon-reload
systemctl --user restart embodmocap-viser.service

# 从日志里取 share 链接，发给别人即可
journalctl --user -u embodmocap-viser.service -n 200 --no-pager | grep -E "Share URL|share"
```

#### 4.2.2 让别人用「公网 IP:端口」直接访问（无需 SSH / share）

> 前提：你们机器确实有公网 IP（或已做端口映射），并且愿意在防火墙/云安全组放行端口。  
> 注意：Viser 默认无鉴权。请按需放行端口（例如只放行固定 IP）。

**(1/3) 修改 unit：让 Viser 监听 0.0.0.0（对外提供服务）**

```bash
VISER_UNIT="$HOME/.config/systemd/user/embodmocap-viser.service"

sed -i 's/--host 127\.0\.0\.1/--host 0.0.0.0/g' "$VISER_UNIT"

systemctl --user daemon-reload
systemctl --user restart embodmocap-viser.service
systemctl --user status embodmocap-viser.service --no-pager
```

**(2/3) 放行端口（以 8080 为例）**

```bash
# Ubuntu/Debian（ufw）
sudo ufw allow 8080/tcp
sudo ufw status | grep 8080 || true
```

并在云厂商控制台（安全组/防火墙）里允许入站 `TCP:8080`。

**(3/3) 发给别人访问地址**

```text
http://<你的公网IP>:8080
```

---

## 5. 常见问题

1) **服务一直在重试某个 scene**  
   通常是输入缺少 `calibration.json/data.jsonl/data.mov/frames2/metadata.json` 或 SAI 失败。先看该 scene 下是否有 `error.txt`，再手工单跑一次 Step1/2 定位。

2) **Viser 下拉里看不到 scene**  
   该 viewer 默认只列出已经生成 `mesh_raw.ply` 或 `mesh_simplified.ply` 的 scene。确认 Step2 是否生成 mesh；必要时点一下 GUI 的 “Refresh Scenes”。

3) **systemd 报错：`Failed at step EXEC spawning conda` / `status=203/EXEC`**  
   这是因为 `systemd --user` 默认不加载你的 shell 启动脚本，导致 `conda` 不在 PATH。解决方式：把 service 里的 `ExecStart=conda ...` 改成 `ExecStart=/abs/path/to/conda ...`，并且（对自动化服务）同时传 `--conda /abs/path/to/conda`。推荐直接用上面的「4.0 一键生成并启动」脚本。
