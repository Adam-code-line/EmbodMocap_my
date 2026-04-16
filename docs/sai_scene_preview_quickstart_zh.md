# Sai CLI 场景预览快速命令

## 1. 适用场景

本页只解决一件事：

拿到一个 `SCENE` 后，直接通过 SSH 转发到本地浏览器，查看 `sai-cli` 处理后得到的场景渲染结果。

特点：

1. 只看场景，不看人体。
2. 只需要修改一个变量：`SCENE`。
3. 如果场景 mesh 还没生成，会先补跑最小构建（Step1-2）。
4. 启动 Viser 后可在 GUI 下拉中切换不同录制（只会列出已生成 mesh 的 scene）。

参考来源：

1. `docs/pipeline_operator_runbook_zh.md` 第 7 节“仅看场景构建预览”。
2. `docs/scene_20260414_152817_single_build_zh.md` 的单场景执行方式。

## 2. 使用方法

下面一共 3 段命令：

1. 第 1 段在你的本地电脑执行。
2. 第 2 段登录服务器。
3. 第 3 段在服务器执行。

你只需要改这里这一行：

```bash
export SCENE=scene_20260414_152817
```

## 3. 最终版命令块

### 3.1 本地电脑：建立端口转发

```bash
ssh -p 22 -Nf -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```
  
如果你想前台观察连接状态，改用：

```bash
ssh -p 22 -L 18080:127.0.0.1:8080 wubin@1080.alpen-y.top
```

### 3.2 本地电脑：登录服务器

```bash
ssh -p 22 wubin@1080.alpen-y.top
```

### 3.3 服务器：只改 `SCENE` 后整段执行

```bash
cd ~/EmbodMocap_dev/embod_mocap

export DATA_ROOT=../datasets/my_capture
export SCENE=recording_2026-04-15_23-33-13
export XLSX_ALL=seq_info_all.xlsx
export XLSX_ONE=seq_info_${SCENE}.xlsx
export CFG=config_fast.yaml

conda activate embodmocap
python run_stages.py "$XLSX_ALL" --data_root "$DATA_ROOT" --steps 0

python - <<'PY'
import os
import pandas as pd

src = os.environ["XLSX_ALL"]
dst = os.environ["XLSX_ONE"]
scene = os.environ["SCENE"]

xl = pd.ExcelFile(src)
df = pd.concat([pd.read_excel(src, sheet_name=s) for s in xl.sheet_names], ignore_index=True)
out = df.loc[df["scene_folder"].astype(str).str.strip() == scene].copy()

if out.empty:
    raise SystemExit(f"No rows found for {scene} in {src}")

out.to_excel(dst, index=False)
print(f"Saved {dst}, rows={len(out)}")
print(out[["scene_folder", "seq_name"]].drop_duplicates().to_string(index=False))
PY

conda activate embodmocap_sai150
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 1 --mode overwrite --force_all

conda activate embodmocap
python run_stages.py "$XLSX_ONE" --data_root "$DATA_ROOT" --config "$CFG" --steps 2 --mode overwrite --force_all

# 启动 Viser：在 GUI 里选择不同录制（scene），默认优先展示 mesh_raw.ply
# - 你仍然只需要改 `SCENE`：上面保证该 scene 的 Step1-2 产物存在
# - 其他已生成 mesh 的录制也会出现在下拉列表里，可直接切换预览
python tools/preview_scene_meshes_viser.py \
  --data_root "$DATA_ROOT" \
  --default_scene "$SCENE" \
  --mesh_mode prefer_raw \
  --port 8080
```

## 4. 本地浏览器地址

```text
http://127.0.0.1:18080
```

## 5. 直接用 MeshLab 看原始高清 mesh

如果你不想看浏览器里的简化预览，而是想直接看更真实的原始场景 mesh，优先使用：

```text
$DATA_ROOT/$SCENE/mesh_raw.ply
```

这个文件通常比 `mesh_simplified.ply` 更大、更完整，也更适合在 MeshLab 里查看细节。

### 5.1 服务器上先确认原始 mesh 是否存在

```bash
cd ~/EmbodMocap_dev/embod_mocap
export DATA_ROOT=../datasets/my_capture
export SCENE=scene_20260414_172022

test -f "$DATA_ROOT/$SCENE/mesh_raw.ply" && echo "[OK] mesh_raw.ply" || echo "[MISSING] mesh_raw.ply"
```

如果缺少 `mesh_raw.ply`，说明当前 scene 还没有生成原始场景 mesh，先回到上面的 Step1-2 命令重新执行。

### 5.2 本地电脑：把原始 mesh 拉到本地

这一段必须在你的本地电脑执行，不要在 `ssh -p 22 wubin@1080.alpen-y.top` 登录进去后的服务器终端里执行。

如果你是在本地 Linux / macOS / WSL 终端里操作，用下面这段：

```bash
export SCENE=scene_20260414_152817
mkdir -p ~/Downloads/embod_mesh

scp -P 22 \
  wubin@1080.alpen-y.top:~/EmbodMocap_dev/datasets/my_capture/${SCENE}/mesh_raw.ply \
  ~/Downloads/embod_mesh/${SCENE}_mesh_raw.ply
```

下载完成后，你本地会得到：

```text
~/Downloads/embod_mesh/${SCENE}_mesh_raw.ply
```

### 5.3 如果你的本地电脑是 Windows，直接下载到 `Downloads`

如果你是在 Windows PowerShell 里操作，推荐用下面这段，这样文件会明确下载到你当前 Windows 用户的下载目录：

```powershell
$env:SCENE="scene_20260414_152817"
$dstDir="$HOME\Downloads\embod_mesh"
New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

scp -P 22 "wubin@1080.alpen-y.top:~/EmbodMocap_dev/datasets/my_capture/$env:SCENE/mesh_raw.ply" "$dstDir\$env:SCENE`_mesh_raw.ply"

Write-Host "Downloaded to: $dstDir\$env:SCENE`_mesh_raw.ply"
```

下载完成后，文件通常在：

```text
C:\Users\你的用户名\Downloads\embod_mesh\scene_xxx_mesh_raw.ply
```

你也可以直接在 PowerShell 里打印绝对路径：

```powershell
$env:SCENE="scene_20260414_152817"
Write-Host "$HOME\Downloads\embod_mesh\$env:SCENE`_mesh_raw.ply"
```

### 5.4 本地电脑：用 MeshLab 打开

如果你的 `meshlab` 已经在 PATH 中：

```bash
export SCENE=scene_20260414_172022
meshlab ~/Downloads/embod_mesh/${SCENE}_mesh_raw.ply
```

如果 `meshlab` 不在 PATH 中，就直接在文件管理器里双击这个 `.ply` 文件，或在 MeshLab 里手动 `File -> Import Mesh` 打开它。

如果你是在 Windows 上使用 MeshLab，最直接的做法是：

1. 打开 `C:\Users\你的用户名\Downloads\embod_mesh`
2. 找到 `scene_xxx_mesh_raw.ply`
3. 右键选择“打开方式”，用 MeshLab 打开

如果你已经知道 MeshLab 的安装路径，也可以在 PowerShell 里直接打开：

```powershell
$env:SCENE="scene_20260414_152817"
$meshPath="$HOME\Downloads\embod_mesh\$env:SCENE`_mesh_raw.ply"
& "C:\Program Files\VCG\MeshLab\meshlab.exe" $meshPath
```

### 5.5 只想知道服务器上的原始 mesh 路径

```bash
cd ~/EmbodMocap_dev/embod_mocap
export DATA_ROOT=../datasets/my_capture
export SCENE=scene_20260414_172022
echo "$DATA_ROOT/$SCENE/mesh_raw.ply"
```

## 6. 结果判定

看到场景 mesh 正常加载，就说明“仅场景预览”已成功。

注意：

1. 这个模式不依赖 `optim_params.npz`。
2. 这个模式不会显示人体。
3. 服务器上最后那个 Python 预览进程必须保持运行，终端不能关。

## 7. 常见问题

### 7.1 提示 `No rows found for ...`

说明 `Step0` 生成的总表里没有这个 `SCENE`，先检查：

1. `SCENE` 是否写错。
2. `DATA_ROOT` 是否指向正确采集目录。
3. 该 scene 是否真的在 `my_capture` 下。

### 7.2 提示 `No mesh found under ...`

说明 Step2 后仍未产出：

1. `mesh_simplified.ply`，或
2. `mesh_raw.ply`

优先检查 Step1、Step2 日志是否实际成功执行。

### 7.3 浏览器打不开

按顺序检查：

1. 本地 SSH 转发命令是否已执行。
2. 服务器上的预览脚本是否仍在运行。
3. 本地打开的是否是 `http://127.0.0.1:18080`。

### 7.4 `scp` 下载 `mesh_raw.ply` 很慢

这是正常现象，原始 mesh 文件通常比较大。

可先做两件事：

1. 确认磁盘空间足够。
2. 耐心等待下载完成后再用 MeshLab 打开。

### 7.5 我想确认文件到底下载到本地哪了

如果你在 Linux / macOS / WSL 里执行下载命令，文件一般在：

```text
~/Downloads/embod_mesh/${SCENE}_mesh_raw.ply
```

如果你在 Windows PowerShell 里执行下载命令，文件一般在：

```text
C:\Users\你的用户名\Downloads\embod_mesh\scene_xxx_mesh_raw.ply
```

可直接用下面命令打印本地绝对路径。

Linux / macOS / WSL：

```bash
export SCENE=scene_20260414_152817
echo ~/Downloads/embod_mesh/${SCENE}_mesh_raw.ply
```

Windows PowerShell：

```powershell
$env:SCENE="scene_20260414_152817"
Write-Host "$HOME\Downloads\embod_mesh\$env:SCENE`_mesh_raw.ply"
```
