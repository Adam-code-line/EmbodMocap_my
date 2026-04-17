# 自动化服务（systemd --user）运维命令速查：启动 / 停止 / 重启 / 查看日志

本文把项目里常用的**自动化部署脚本对应的 systemd 用户级服务**（`systemctl --user ...`）相关命令集中到一处，方便你在排查/手工重跑（例如先停掉自动化去重跑 Step 3）后再快速恢复服务。

> 适用场景：你在服务器上用 `systemd --user` 长期跑：
> - `tools/auto_spectacular_rec_service.py`（全流程 human Step0-15 自动化）
> - `tools/auto_scene_mesh_service.py`（scene mesh preview 的 Step0/1/2 自动化）
> - `tools/preview_scene_meshes_viser.py` / `tools/visualize_viser.py`（可视化服务）

---

## 0) 自动化服务清单与关系（按顺序）

下面按“数据流向”把常见自动化服务列出来，并说明它们之间的关联关系（你要做“停服务 → 手工重跑 Step3 → 再恢复自动化”时，建议按这个顺序停/启）：

1) `sdr-incoming-bridge.service` → `embod_mocap/tools/sdr_incoming_bridge.py`（上游：把后端 ZIP 送进 `_incoming/`）
- 输入：`DATA_ROOT/` 下你后端落盘的 ZIP（不要求在 `_incoming/`，也不要求文件名含 token）
- 输出：`DATA_ROOT/_incoming/recording_...__scene=...__type=...__seq=...__cam=...zip`
- 作用：把 ZIP 重命名/桥接成 EmbodMocap 自动化能识别的 token 命名格式（详见 `docs/拍摄上传命名对齐与自动化处理部署指南.md`）

2) `embodmocap-scene-auto.service` → `embod_mocap/tools/auto_spectacular_rec_service.py`（核心：自动 ingest + 自动跑 Step）
- 输入：`DATA_ROOT/_incoming/` 下 token 命名 ZIP
- 输出：自动整理到 `DATA_ROOT/<SCENE>/` 与 `DATA_ROOT/<SCENE>/<SEQ>/...`，并按条件自动跑：
  - scene-only：Step0-2（产出 `transforms.json`、`mesh_raw.ply/mesh_simplified.ply`）
  - human：当同一 `scene+seq` 的 A/B 视角齐全后，自动跑 Step0-15
- 关键特性（建议开启）：
  - `--lock_dir _locks`：scene 级加锁/串行化，避免同 scene 并行写互相覆盖
  - `--log_dir _logs/...`：把每个 scene 的每个 step 输出落盘，便于排障

2b) （可选替代）`embodmocap-scene-auto.service` → `embod_mocap/tools/auto_scene_mesh_service.py`（只做 scene mesh preview）
- 只自动跑 Step0/1/2，用于“场景 mesh 预览”场景；不包含 human Step0-15 的自动化
- 通常不需要与 `auto_spectacular_rec_service.py` 同时跑；如果必须同时跑，建议两者使用同一个 `--lock_dir` 来避免同 scene 并发

3) `embodmocap-viser.service` → `embod_mocap/tools/preview_scene_meshes_viser.py`（可视化：浏览 `DATA_ROOT/` 下场景 mesh）
- 输入：`mesh_raw.ply` / `mesh_simplified.ply`（以及可选 human 输出，如 `optim_params.npz`）
- 输出：Viser Web UI（用于预览与分享）
- 关系：依赖 2) 的产物，但可以先启动（没有产物时界面只是空/少）

4) `embodmocap-demo-viser8081.service` → `embod_mocap/tools/visualize_viser.py`（可选：按 xlsx 加载多场景/序列展示）
- 输入：xlsx（例如 `seq_info_all.xlsx` / demo 的 `release_demo.xlsx`）
- 输出：Viser Web UI

---

## 0.1) 建议先设置几个变量（可选）

```bash
export EMBOD_DIR="$HOME/EmbodMocap_dev/embod_mocap"
export DATA_ROOT="../datasets/my_capture"   # 相对 EMBOD_DIR
```

---

## 0.2) unit 名称与脚本映射（查看当前配置）

常用 unit 名称（用户级）：

- 桥接服务（可选）：`sdr-incoming-bridge.service`（把后端 ZIP 桥接到 `_incoming/`）
- 自动化主服务：`embodmocap-scene-auto.service`
  - 可能跑的是 `auto_scene_mesh_service.py`（只做 Step0-2）
  - 也可能跑的是 `auto_spectacular_rec_service.py`（全流程 Step0-15）
- 预览/可视化：`embodmocap-viser.service`
- demo viewer（可选）：`embodmocap-demo-viser8081.service`

你可以先确认当前 `embodmocap-scene-auto.service` 的 ExecStart：

```bash
systemctl --user cat embodmocap-scene-auto.service | sed -n '1,200p'
# 或只看 ExecStart
systemctl --user show embodmocap-scene-auto.service -p ExecStart --no-pager
```

---

## 1) （可选）新增桥接服务：`sdr-incoming-bridge.service`

什么时候需要：

- 你不是把 token 命名的 ZIP 直接上传到 `DATA_ROOT/_incoming/`，而是后端把 ZIP 落在了 `DATA_ROOT/<SCENE>/<SEQ>/...` 之类的结构里
- 或者 ZIP 文件名不包含 `__scene=...__type=...__seq=...__cam=...` 这些 token

它会跑 `embod_mocap/tools/sdr_incoming_bridge.py`，扫描 `DATA_ROOT/`（排除 `_incoming/`），读 ZIP 内 `upload_context.json` 来重建 token 文件名，然后把 ZIP 以 hardlink/symlink/copy 的方式“入队”到 `_incoming/`。

### 1.1 写入 systemd user unit

```bash
# 1) 找到 conda 绝对路径（systemd --user 建议用绝对路径）
command -v conda
CONDA_BASE="$(conda info --base)"
CONDA_EXE="$CONDA_BASE/bin/conda"
[ -x "$CONDA_EXE" ] || CONDA_EXE="$CONDA_BASE/condabin/conda"
echo "CONDA_EXE=$CONDA_EXE"
ls -l "$CONDA_EXE"

# 2) 写 unit
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/sdr-incoming-bridge.service" <<UNIT
[Unit]
Description=SDR incoming bridge (backend zips -> _incoming token zips)
After=network.target

[Service]
Type=simple
WorkingDirectory=$EMBOD_DIR
Restart=always
RestartSec=2
ExecStart=$CONDA_EXE run -n embodmocap python tools/sdr_incoming_bridge.py --data_root $DATA_ROOT --interval 2

[Install]
WantedBy=default.target
UNIT

# 3) 启动
systemctl --user daemon-reload
systemctl --user enable --now sdr-incoming-bridge.service
systemctl --user status sdr-incoming-bridge.service --no-pager
```

### 1.2 （推荐）让自动化主服务“等待/跟随”桥接服务

> 如果你只想手动控制，也可以不做这一步，直接两个服务都 `enable --now` 即可。

```bash
systemctl --user edit embodmocap-scene-auto.service
```

在 editor 里加入（或追加）：

```ini
[Unit]
Wants=sdr-incoming-bridge.service
After=sdr-incoming-bridge.service
```

然后重启：

```bash
systemctl --user daemon-reload
systemctl --user restart embodmocap-scene-auto.service
```

---

## 2) 停止 / 启动 / 重启（最常用）

### 2.1 停止（比如你要手工重跑 Step 3）

```bash
systemctl --user stop embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
```

如果你也部署了桥接服务（`sdr-incoming-bridge.service`），建议一起停掉，避免它继续往 `_incoming/` 里入队新 ZIP：

```bash
systemctl --user stop sdr-incoming-bridge.service 2>/dev/null || true
systemctl --user status sdr-incoming-bridge.service --no-pager || true
```

如果你也想一起停可视化：

```bash
systemctl --user stop embodmocap-viser.service 2>/dev/null || true
systemctl --user stop embodmocap-demo-viser8081.service 2>/dev/null || true
```

### 2.2 重启（你问的“停掉后怎么重启”）

```bash
systemctl --user start embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
```

如果你也用了桥接服务，按顺序启动更稳（先桥接，再自动化主服务）：

```bash
systemctl --user start sdr-incoming-bridge.service 2>/dev/null || true
systemctl --user restart embodmocap-scene-auto.service
```

更推荐（确保加载最新代码/环境后重新拉起）：

```bash
systemctl --user restart embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
```

### 2.3 服务异常后清理状态（常用）

```bash
systemctl --user reset-failed embodmocap-scene-auto.service 2>/dev/null || true
systemctl --user restart embodmocap-scene-auto.service
```

---

## 3) 查看日志：journalctl（实时/最近）

### 3.1 看最近 200 行

```bash
journalctl --user -u embodmocap-scene-auto.service -n 200 --no-pager
```

### 3.2 实时跟随

```bash
journalctl --user -u embodmocap-scene-auto.service -f
```

### 3.3 按时间查（排查某次失败很有用）

```bash
journalctl --user -u embodmocap-scene-auto.service --since "2026-04-17 00:00:00" --no-pager
```

桥接服务同理：

```bash
journalctl --user -u sdr-incoming-bridge.service -n 200 --no-pager
journalctl --user -u sdr-incoming-bridge.service -f
```

可视化服务同理：

```bash
journalctl --user -u embodmocap-viser.service -n 100 --no-pager
journalctl --user -u embodmocap-viser.service -f
```

---

## 4) 查看日志：落盘持久化日志（按 scene/step）

如果你的 `ExecStart` 里带了 `--log_dir ...`（新版自动化默认推荐打开），那么每个 scene/每个 step 的 `run_stages.py` 输出会被 tee 到文件，便于后续 grep。

### 4.1 full pipeline（auto_spectacular_rec_service）

默认路径：

```bash
ls -lah "$EMBOD_DIR/$DATA_ROOT/_logs/auto_spectacular_rec_service" | head
ls -lah "$EMBOD_DIR/$DATA_ROOT/_logs/auto_spectacular_rec_service/<SCENE_NAME>" | tail
```

### 4.2 scene mesh preview（auto_scene_mesh_service）

默认路径：

```bash
ls -lah "$EMBOD_DIR/$DATA_ROOT/_logs/auto_scene_mesh_service" | head
ls -lah "$EMBOD_DIR/$DATA_ROOT/_logs/auto_scene_mesh_service/<SCENE_NAME>" | tail
```

---

## 5) scene 级加锁（避免同 scene 并行互相覆盖）

新版自动化支持 `--lock_dir`，默认会在 `DATA_ROOT/_locks/` 下创建目录锁：

```bash
ls -lah "$EMBOD_DIR/$DATA_ROOT/_locks" | head
cat "$EMBOD_DIR/$DATA_ROOT/_locks/<SCENE_NAME>.lock/meta.json" 2>/dev/null || true
```

### 5.1 手工清理“残留锁”（谨慎）

正常情况下进程退出会自动释放锁；但如果你手工 `kill -9` 或机器崩溃，可能留下锁目录。

清理前先看 meta 里是谁持有（pid/hostname/started_at）：

```bash
cat "$EMBOD_DIR/$DATA_ROOT/_locks/<SCENE_NAME>.lock/meta.json"
```

确认没有同 scene 任务在跑后再删：

```bash
rm -rf "$EMBOD_DIR/$DATA_ROOT/_locks/<SCENE_NAME>.lock"
```

---

## 6) unit 改动后如何“重新部署”（daemon-reload）

如果你改了 `~/.config/systemd/user/embodmocap-scene-auto.service`（例如更新 ExecStart 参数），需要：

```bash
systemctl --user daemon-reload
systemctl --user restart embodmocap-scene-auto.service
systemctl --user status embodmocap-scene-auto.service --no-pager
```

如需开机/登录后自动拉起：

```bash
systemctl --user enable embodmocap-scene-auto.service
```

---

## 7) 不使用 systemd 时（手工前台启动/停止）

有时你需要在终端里手工跑一次（例如 `--run_once` 验证 ingest 或定位某次失败），可以直接运行脚本本体：

### 7.0 bridge（sdr_incoming_bridge.py）

```bash
cd "$EMBOD_DIR"

# 前台跑：Ctrl+C 停止（不断桥接入队到 _incoming/）
conda run -n embodmocap python tools/sdr_incoming_bridge.py \
  --data_root "$DATA_ROOT" \
  --interval 2
```

只跑一轮就退出（cron-friendly）：

```bash
conda run -n embodmocap python tools/sdr_incoming_bridge.py --data_root "$DATA_ROOT" --once
```

### 7.1 full pipeline（auto_spectacular_rec_service.py）

```bash
cd "$EMBOD_DIR"

# 前台跑：Ctrl+C 停止
conda run -n embodmocap python tools/auto_spectacular_rec_service.py \
  --data_root "$DATA_ROOT" \
  --incoming _incoming \
  --config config_fast.yaml \
  --conda "$(command -v conda)" \
  --env_main embodmocap \
  --env_sai embodmocap_sai150 \
  --mode skip \
  --lock_dir _locks \
  --log_dir _logs/auto_spectacular_rec_service
```

只跑一轮就退出：

```bash
conda run -n embodmocap python tools/auto_spectacular_rec_service.py \
  --data_root "$DATA_ROOT" --incoming _incoming --config config_fast.yaml \
  --conda "$(command -v conda)" --env_main embodmocap --env_sai embodmocap_sai150 \
  --mode skip --lock_dir _locks --log_dir _logs/auto_spectacular_rec_service \
  --run_once
```

### 7.2 scene mesh preview（auto_scene_mesh_service.py）

```bash
cd "$EMBOD_DIR"
conda run -n embodmocap python tools/auto_scene_mesh_service.py \
  --data_root "$DATA_ROOT" \
  --config config_fast.yaml \
  --xlsx_out seq_info_all.xlsx \
  --auto_import_scene_zips --ensure_seq0 --auto_extract_seq_zips \
  --poll_interval 30 \
  --conda "$(command -v conda)" \
  --mode skip \
  --lock_dir _locks \
  --log_dir _logs/auto_scene_mesh_service
```

### 7.3 手工停止（谨慎）

前台运行：直接 `Ctrl+C`。

后台/多终端误跑：先查再杀（建议按脚本名过滤）：

```bash
pgrep -af auto_spectacular_rec_service.py || true
pgrep -af auto_scene_mesh_service.py || true
pgrep -af sdr_incoming_bridge.py || true

# 确认后再 kill
# kill <PID>
```
