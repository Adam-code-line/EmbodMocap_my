# 拍摄软件（data_recorder_backend）与 Spectacular Rec 手动上传：落盘目录、数据结构与 EmbodMocap 自动化触发全流程说明

本文把两条常见数据来源的“上传 → 落盘目录 → 入队 `_incoming/` → 自动化触发 → 产物落盘”的链路讲清楚，方便你在服务器上定位：

- ZIP 到底存到了哪里？
- 为什么自动化没有触发/触发了但没跑到某一步？
- 为什么需要（或不需要）`sdr_incoming_bridge.py`？

本文涉及的关键代码/脚本：

- 你的上传后端：`data_recorder_backend/src/storage.js`（决定 ZIP 最终保存在哪里、目录层级是什么）
- 桥接入队：`embod_mocap/tools/sdr_incoming_bridge.py`（把后端落盘 ZIP 映射到 `DATA_ROOT/_incoming/` 的 token 文件名 ZIP）
- 自动化主服务：`embod_mocap/tools/auto_spectacular_rec_service.py`（只扫描 `_incoming/`，按文件名 token 决定跑 scene-only/human 流程）
- 运维命令速查：`docs/automation_services_ops_zh.md`

---

## 0. 关键术语与目录约定

### 0.1 `DATA_ROOT`（EmbodMocap 数据集根目录）

`DATA_ROOT` 是 EmbodMocap 侧约定的数据根目录，典型示例：

```bash
export DATA_ROOT=../datasets/my_capture
```

在 `DATA_ROOT` 下，**自动化触发队列**固定为：

```text
DATA_ROOT/_incoming/
```

> `auto_spectacular_rec_service.py` **只扫描这个目录**。

### 0.2 `<SCENE>` / `<SEQ>`（EmbodMocap 的场景与序列目录）

自动化处理后，落盘结构通常会变成：

```text
DATA_ROOT/
  _incoming/                      # 入队目录（触发点）
  _locks/                         # scene 级锁（避免并发覆盖）
  _logs/                          # 自动化落盘日志
  <SCENE>/                        # 场景目录（scene-only 输出在这里）
    transforms.json
    mesh_raw.ply / mesh_simplified.ply
    colmap/...
    <SEQ>/                        # 带人序列目录
      recording_*.zip             # ingest 后归档的原始 zip（human）
      raw1/ raw2/                 # Step4 抽帧输出
      v1/ v2/                     # Step6/8/.. 输出
```

---

## 1. 两条数据来源（你现在同时在用的两种上传方式）

### 1.1 方式 A：你的拍摄软件 → `data_recorder_backend`（后端接收 ZIP）

特点：

- ZIP **不会直接进入** `DATA_ROOT/_incoming/`
- ZIP 的文件名也**不会**是 EmbodMocap 需要的 token 格式（原因见第 2 节）
- 因此要想触发 EmbodMocap 自动化，通常需要桥接脚本：`sdr_incoming_bridge.py`

### 1.2 方式 B：Spectacular Rec 手动上传 ZIP（你自己 scp/网盘/拖拽到服务器）

特点：

- 你可以直接把 ZIP 放进 `DATA_ROOT/_incoming/`
- 只要文件名满足 token 规范，`auto_spectacular_rec_service.py` 会自动识别并触发
- **不需要** `data_recorder_backend`，也不需要桥接脚本

---

## 2. 方式 A 的落盘规则：`data_recorder_backend/src/storage.js` 具体保存到哪里？

`storage.js` 的核心逻辑是：上传的 ZIP 会先写入 staging（`.part`），然后原子重命名到 final path。

### 2.1 ZIP 最终保存路径（final path）

在 `buildStoragePaths(...)` 中，final path 由以下字段拼出来：

```text
<uploadRootDir>/<captureName>/<sceneName>/<seqName>/<sessionBaseName>.zip
```

对应代码要点（语义）：

- `uploadRootDir`：后端配置项 `config.uploadRootDir`
- `captureName`：请求字段 `captureName`（或使用 `config.datasetCaptureName` 默认值）
- `sceneName`：请求字段 `sceneName`（为空则从 `sessionName` 的时间戳推导，或用当前时间生成）
- `seqName`：请求字段 `seqName`（或使用 `config.datasetSeqName` 默认值）
- `sessionBaseName`：`sessionName` 去掉 `.zip` 后缀再加回 `.zip`

因此后端落盘目录（示例）类似：

```text
UPLOAD_ROOT/
  my_capture/                     # captureName
    scene_0014/                   # sceneName
      seq0/                       # seqName
        2026-04-17_01-23-45.zip    # sessionName
```

### 2.2 为什么后端落盘的 ZIP 文件名一般不可能直接满足 EmbodMocap token 格式？

`storage.js` 里对 `sessionName` 有严格字符集限制（只允许字母/数字/点/下划线/横杠），而 EmbodMocap token 文件名包含 `=`（例如 `__scene=...`），这类文件名无法通过后端校验。

结论：

- **后端落盘 ZIP 的文件名通常不会包含 `__scene=...__type=...` token**
- 即使你的客户端上传时携带了 `upload_context.json`，也需要桥接脚本来“重建 token 文件名”

### 2.3 后端是否会解压 ZIP？

`storage.js` 提供了 `extractSceneFilesFromZip({ zipPath, sceneDir })`，其行为是：

- 只提取一小部分“允许的场景根文件”（如 `calibration.json / data.jsonl / data.mov / metadata.json / upload_context.json`）
- 以及 `frames2/` 子树
- 其它路径会被忽略（安全防护）

是否真的执行了解压，取决于后端上层路由有没有调用该函数；但**即便后端解压了**，EmbodMocap 的自动化触发仍然是以 `_incoming/` 为入口（见第 4 节）。

---

## 3. 方式 B（Spectacular Rec 手动上传）应该上传到哪里？目录长什么样？

你手动上传时，直接把 ZIP 放到：

```text
DATA_ROOT/_incoming/
```

并且文件名要满足 token 格式（auto service 只看文件名，不看你“存放到哪里”以外的目录结构）：

```text
recording_<任意>__scene=<SCENE>__type=<scene|human>[__seq=seq0][__cam=A|B].zip
```

示例：

```text
# scene-only（只需要 1 个 zip）
recording_2026-04-16_10-20-30__scene=scene_0014__type=scene.zip

# human（同一 scene+seq 必须 A/B 两个 zip 都到齐）
recording_2026-04-16_10-45-00__scene=scene_0014__type=human__seq=seq0__cam=A.zip
recording_2026-04-16_10-45-00__scene=scene_0014__type=human__seq=seq0__cam=B.zip
```

上传方式常见两种：

- `scp` 到 `DATA_ROOT/_incoming/`
- 或你自己的 HTTP 上传服务把 multipart 的 `file` 按原始文件名保存到 `DATA_ROOT/_incoming/<filename>`

---

## 4. “怎么触发自动化脚本”：触发点只有一个——`DATA_ROOT/_incoming/`

### 4.1 桥接脚本（方式 A 必需）：`embod_mocap/tools/sdr_incoming_bridge.py`

桥接脚本解决的问题：后端把 ZIP 放在了 `UPLOAD_ROOT/<capture>/<scene>/<seq>/...`，而 EmbodMocap 自动化只扫 `_incoming/`。

桥接脚本的做法：

1. 扫描 `--data_root` 指定的目录树，寻找 `.zip`（排除 `_incoming/` 子树）
2. 如果 ZIP 文件名已经是 token 格式（含 `__scene=...__type=...`），就直接用它
3. 否则读取 ZIP 内的 `upload_context.json`，用里面的字段重建 token 文件名：
   - `sceneName` → `scene=...`
   - `captureType` → `type=scene|human`
   - 若 `type=human`：还必须有 `seqName` 与 `cam=A|B`，否则不会入队（避免误触发）
4. 把 ZIP “入队”到：`DATA_ROOT/_incoming/<tokenized_name>.zip`
   - 默认 `--link_method auto`：优先 hardlink（不额外占空间），失败再 symlink，最后 copy
5. 用 state 文件避免重复入队：`DATA_ROOT/.sdr_incoming_bridge_state.json`

> 结论：方式 A 触发自动化的链路是：  
> **data_recorder_backend 落盘** → **bridge 入队 `_incoming/`** → **auto service 扫描 `_incoming/` 触发**

### 4.2 自动化主服务：`embod_mocap/tools/auto_spectacular_rec_service.py`

该服务的触发逻辑非常明确：

- 只扫描：`DATA_ROOT/_incoming/*.zip`
- 只根据“文件名 token”决定走什么流程
- 会等待文件稳定（默认 `--stable_seconds`），避免读到上传中途文件

入队后发生什么（概览）：

1) 对 `type=scene`：

- 解包 raw inputs 到：`DATA_ROOT/<SCENE>/`（scene 根目录）
- 把原始 zip 归档到：`DATA_ROOT/<SCENE>/seq0/_imports/`
- 然后自动跑 scene-only 的步骤（例如 Step1/2；具体取决于服务参数与 xlsx 生成逻辑）

2) 对 `type=human`：

- 把 zip 移动到：`DATA_ROOT/<SCENE>/<SEQ>/recording_*.zip`
- 后续 Step4 会自动解压到 `raw1/ raw2/`
- 当同一 `scene+seq` 的 A/B 视角齐全时，自动跑 human 的全流程步骤（Step0-15）

为了避免“同一个 scene 并发覆盖导致半成品产物”（例如你遇到的 Step3 半成品数据库问题），推荐打开：

- `--lock_dir _locks`：scene 级加锁/串行化
- `--log_dir _logs/...`：每个 scene/每个 step 输出落盘，便于排障

---

## 5. 如何快速确认“现在 ZIP 在哪一层、自动化有没有触发”

### 5.1 看后端落盘（方式 A）

后端落盘根目录由后端配置决定（`uploadRootDir`）。典型地你会看到：

```text
UPLOAD_ROOT/<captureName>/<sceneName>/<seqName>/<session>.zip
```

如果 bridge 开着，最终还会看到：

```text
DATA_ROOT/_incoming/recording_...__scene=...__type=...zip
```

### 5.2 看 `_incoming` 是否在增长/被消费

```bash
ls -lah "$DATA_ROOT/_incoming" | tail
ls -lah "$DATA_ROOT/_incoming/_bad" 2>/dev/null || true
```

- `_incoming` 里 ZIP 会被自动化“消费”（移动/归档），所以目录变空是正常的
- `_bad` 里有 ZIP：说明文件名 token 不合法或缺字段

### 5.3 看服务日志

直接参考：

- `docs/automation_services_ops_zh.md`

---

## 6. 推荐的“最少扯皮”部署组合（把链路串起来）

推荐以 `systemd --user` 跑常驻服务：

1) `sdr-incoming-bridge.service`（可选，方式 A 需要）
2) `embodmocap-scene-auto.service`（核心：auto_spectacular_rec_service）
3) `embodmocap-viser.service`（可选：预览）

并让主服务 `Wants/After sdr-incoming-bridge.service`，确保桥接先跑起来（详见 `docs/automation_services_ops_zh.md`）。

