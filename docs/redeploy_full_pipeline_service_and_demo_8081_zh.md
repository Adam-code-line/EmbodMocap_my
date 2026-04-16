# 重新部署自动化服务（human Step0-15）+ Demo 可视化改 8081（含公网直连/SSH）

本文给你两组**可直接复制运行**的命令：

1. 把 systemd user service：`~/.config/systemd/user/embodmocap-scene-auto.service` 的 `ExecStart=...auto_scene_mesh_service.py ...` 替换为**全流程** `auto_spectacular_rec_service.py`（human 自动跑 Step0-15）
2. 把 demo 的 `tools/visualize_viser.py` 可视化端口换到 **8081**，并给出「公网直连」与「SSH 端口转发」两种访问方式

---

## 0) 你需要先确认的路径/环境

- 代码目录（包含 `run_stages.py` 的那个）：`~/EmbodMocap_dev/embod_mocap`
- 数据目录（推荐结构）：`~/EmbodMocap_dev/datasets/my_capture`
- conda 环境名（默认约定）：
  - `embodmocap`（主流程）
  - `embodmocap_sai150`（Step1/Step5，spectacularAI）

---

## 1) 分段改 unit：把 `embodmocap-scene-auto.service` 切到全流程（human Step0-15）

> 如果你把所有命令一次性跑成“一整段脚本”，只要中间某条命令失败（尤其是 conda 路径探测），你的 shell 可能会退出，表现为 SSH 连接断开。  
> 下面改成“**一段一段执行**”，每段都可直接复制运行。

### 1.1 设置变量（在同一个 SSH 会话里执行）

```bash
EMBOD_DIR="$HOME/EmbodMocap_dev/embod_mocap"
DATA_ROOT="../datasets/my_capture"   # 相对 EMBOD_DIR（推荐）
```

### 1.2 检查目录是否存在

```bash
ls -ld "$EMBOD_DIR"
ls -ld "$EMBOD_DIR/$DATA_ROOT" || true
```

### 1.3 找到 conda 绝对路径（systemd --user 必须用绝对路径）

优先用当前 shell 里的 conda：

```bash
command -v conda
CONDA_BASE="$(conda info --base)"
CONDA_EXE="$CONDA_BASE/bin/conda"
[ -x "$CONDA_EXE" ] || CONDA_EXE="$CONDA_BASE/condabin/conda"
echo "CONDA_EXE=$CONDA_EXE"
ls -l "$CONDA_EXE"
```

如果你这一步 `conda` 就不在 PATH，手动设置一个常见路径（按你的机器实际情况改）：

```bash
CONDA_EXE="$HOME/miniconda3/bin/conda"
echo "CONDA_EXE=$CONDA_EXE"
ls -l "$CONDA_EXE"
```

### 1.4 创建所需目录（`_incoming` 是上传入口）

```bash
mkdir -p "$HOME/.config/systemd/user"
mkdir -p "$EMBOD_DIR/$DATA_ROOT/_incoming"
```

### 1.5 停止旧服务

```bash
systemctl --user stop embodmocap-scene-auto.service 2>/dev/null || true
systemctl --user reset-failed embodmocap-scene-auto.service 2>/dev/null || true
```

### 1.6 写入新的 unit（把 ExecStart 换成全流程那一行）

```bash
cat > "$HOME/.config/systemd/user/embodmocap-scene-auto.service" <<UNIT
[Unit]
Description=EmbodMocap Auto Ingest + Full Pipeline (human Step0-15)
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
ExecStart=$CONDA_EXE run -n embodmocap python tools/auto_spectacular_rec_service.py --data_root $DATA_ROOT --incoming _incoming --config config_fast.yaml --conda $CONDA_EXE --env_main embodmocap --env_sai embodmocap_sai150 --mode skip --poll_interval 30

[Install]
WantedBy=default.target
UNIT
```

### 1.7 重新加载并启动服务

```bash
systemctl --user daemon-reload
systemctl --user enable --now embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
```

### 1.8 查看日志（建议先看 200 行）

```bash
journalctl --user -u embodmocap-scene-auto.service -n 200 --no-pager
```

上传方式（提醒）：按命名规范把 zip 放到 `datasets/my_capture/_incoming/`，命名规范见：`docs/spectacular_rec_upload_naming_zh.md`。

---

## 2) Demo 可视化改用 8081（公网直连 / SSH 转发）

### 2.1 在服务器启动 demo viewer（端口 8081）

在服务器另开一个终端执行（仅本机访问用 `--host 127.0.0.1`；要公网直连用 `--host 0.0.0.0`）：

```bash
cd ~/EmbodMocap_dev/embod_mocap
conda run -n embodmocap python tools/visualize_viser.py \
  --xlsx ../datasets/release_demo.xlsx \
  --data_root ../datasets/dataset_demo \
  --stride 2 \
  --scene_mesh simple \
  --mesh_level 1 \
  --host 0.0.0.0 \
  --port 8081
```

> 注意：Viser 默认无鉴权。公网直连前请确认端口放行策略（例如只放行固定 IP）。
>
> 如果你本机已有东西占用 8081，把上面的 `--port 8081` 换成 `8082/8083/...`，并同步修改后续访问方式里的端口。

### 2.1B（可选）把 demo viewer 也做成 systemd user service（推荐长期跑）

> 这段会创建并启动：`~/.config/systemd/user/embodmocap-demo-viser8081.service`。

**(1/3) 确认变量（如果你按第 1 节走过，这里一般已经有 CONDA_EXE）**

```bash
EMBOD_DIR="${EMBOD_DIR:-$HOME/EmbodMocap_dev/embod_mocap}"
CONDA_EXE="${CONDA_EXE:-}"

if [ -z "$CONDA_EXE" ]; then
  CONDA_BASE="$(conda info --base)"
  CONDA_EXE="$CONDA_BASE/bin/conda"
  [ -x "$CONDA_EXE" ] || CONDA_EXE="$CONDA_BASE/condabin/conda"
fi

echo "[INFO] EMBOD_DIR=$EMBOD_DIR"
echo "[INFO] CONDA_EXE=$CONDA_EXE"
ls -l "$CONDA_EXE"
```

**(2/3) 写入 unit（8081，公网直连）**

```bash
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/embodmocap-demo-viser8081.service" <<UNIT
[Unit]
Description=EmbodMocap Demo Viser Viewer (8081)
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=5
ExecStart=$CONDA_EXE run -n embodmocap python tools/visualize_viser.py --xlsx ../datasets/release_demo.xlsx --data_root ../datasets/dataset_demo --stride 2 --scene_mesh simple --mesh_level 1 --host 0.0.0.0 --port 8081

[Install]
WantedBy=default.target
UNIT
```

**(3/3) 重新加载并启动 demo service**

```bash
systemctl --user daemon-reload
systemctl --user enable --now embodmocap-demo-viser8081.service
systemctl --user status embodmocap-demo-viser8081.service --no-pager
journalctl --user -u embodmocap-demo-viser8081.service -n 80 --no-pager
```

### 2.2 方案 A：公网 IP:8081 直连（无需 SSH）

**(1/2) 放行端口 8081（防火墙 + 云安全组）**

```bash
# Ubuntu/Debian（ufw）
sudo ufw allow 8081/tcp
sudo ufw status | grep 8081 || true
```

```bash
# CentOS/RHEL（firewalld）
sudo firewall-cmd --permanent --add-port=8081/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports | grep -E '(^| )8081/tcp( |$)' || true
```

并在云厂商控制台（安全组/防火墙）里允许入站 `TCP:8081`。

**(2/2) 访问地址**

```text
http://<你的公网IP>:8081
```

> 例子：如果你在 `spatial_data_recorder/.env` 里使用了 `UPLOAD_BASE_URL=http://1080.alpen-y.top:8080`，
> 那么 demo viewer 的公网访问通常就是：`http://1080.alpen-y.top:8081`（同域名 + 不同端口）。

### 2.3 方案 B：本地电脑做 SSH 端口转发（更安全）

在**本地电脑**执行（把 `<user>@<server>` 换成你的服务器登录信息）：

```bash
ssh -p 22 -Nf -L 8081:127.0.0.1:8081 <user>@<server>
```

然后本地浏览器打开：

```text
http://127.0.0.1:8081
```

如果你本地 `8081` 也被占用，用 `18081` 之类的端口：

```bash
ssh -p 22 -Nf -L 18081:127.0.0.1:8081 <user>@<server>
```

浏览器打开：

```text
http://127.0.0.1:18081
```
