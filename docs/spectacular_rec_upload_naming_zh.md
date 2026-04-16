# Spectacular Rec ZIP 上传命名规范（Scene / Human / 双目）

本文档目标：让别人只要按统一的文件命名把 **Spectacular Rec 导出的 `recording_*.zip`** 上传到指定目录，系统就能：

- **区分** “只拍场景（scene-only）” vs “带人拍摄（human）”
- 自动整理成 `datasets/my_capture/` 推荐结构
- scene-only：按之前一样自动跑 **Step0-2**（建图 + mesh 预览）
- human：自动跑完 **Step0-15** 主流程（含双 conda 的 Step1/Step5 分流）

> 约定：这里的 “双目/双机位” 都指 **两个视角（raw1/raw2）**。  
> 你的 zip 里仍然必须是 Spectacular Rec 的原始 5 件套：`calibration.json`、`data.jsonl`、`data.mov`、`frames2/`、`metadata.json`。

---

## 1. 上传目录（强烈推荐）

把要处理的 zip 上传到数据根目录下的收件箱（inbox）：

```text
datasets/my_capture/_incoming/
```

自动化服务会扫描 `_incoming/`，解析命名后搬运到正确位置；这样可以避免把 `*.zip` 直接丢到 `my_capture/` 根目录时，被旧脚本误当成 “scene 包” 导入。

---

## 2. 文件名格式（Key=Value + `__` 分隔）

统一格式：

```text
recording_<任意原始部分>__scene=<SCENE>__type=<TYPE>[__seq=<SEQ>][__cam=<CAM>][__stereo=1].zip
```

- 分隔符固定用双下划线：`__`
- 扩展信息用 `key=value` 形式；顺序不强制（建议按本文示例顺序）
- **必须以 `.zip` 结尾**

### 2.1 必填字段

1) `scene=<SCENE>`

- 表示目标场景文件夹名，最终落盘为：

```text
datasets/my_capture/<SCENE>/
```

- `SCENE` 只能使用：字母/数字/下划线/短横/点号（建议不要空格、中文）
- 推荐格式：`scene_YYYYMMDD_HHMMSS_<place>`  
  示例：`scene_20260416_102030_livingroom1`

2) `type=<TYPE>`

- 只能取：
  - `scene`：只拍场景（无人的建图数据）
  - `human`：带人拍摄（需要跑 Step0-15）

### 2.2 human 类型额外必填字段

当 `type=human` 时必须再提供：

1) `seq=<SEQ>`

- 只能取 `seq0`、`seq1`、`seq2` ...（与主流程一致）

2) `cam=<CAM>`

用于明确双目/双机位的左右视角（保证 raw1/raw2 归属稳定）：

- 推荐只用：`A` 和 `B`
  - `cam=A` → 归为 **raw1**
  - `cam=B` → 归为 **raw2**
- 也允许：`L/R`（等价于 A/B）

> 重要：同一个 `<SCENE> + <SEQ>` 必须上传 **两份** zip：一份 `cam=A`，一份 `cam=B`。  
> 否则自动化不会触发完整的 Step0-15（因为 Step4 需要两视角输入）。

### 2.3 可选字段（仅在你需要时用）

1) `stereo=1`

- 表示这是一个 **“双目打包 zip（bundle）”**：单个 zip 里包含两个视角的 payload。
- 自动化会把它解包成两个 `recording_*/` 目录，再交给 Step4 自动整理到 `raw1/raw2`。

> 如果你平时就是两台手机各导出一个 `recording_*.zip`，不要用 `stereo=1`。

2) `v1_start=<int>` / `v2_start=<int>`（高级选项）

- 用于覆盖 Step6 所需的同步索引。未提供时，自动化会给 human 序列填一个保守默认值（例如 `0/0`），保证流程能跑通。

---

## 3. 命名示例（建议直接照抄改时间戳）

### 3.1 只拍场景（scene-only）

上传 1 个 zip：

```text
recording_2026-04-16_10-20-30__scene=scene_20260416_102030_livingroom1__type=scene.zip
```

### 3.2 带人拍摄（human，seq0，双目两文件）

同一个 take（`seq0`）上传 2 个 zip（A/B 各一个）：

```text
recording_2026-04-16_10-45-00__scene=scene_20260416_102030_livingroom1__type=human__seq=seq0__cam=A.zip
recording_2026-04-16_10-45-00__scene=scene_20260416_102030_livingroom1__type=human__seq=seq0__cam=B.zip
```

### 3.3 带人拍摄（human，多 take）

```text
recording_2026-04-16_10-45-00__scene=scene_20260416_102030_livingroom1__type=human__seq=seq0__cam=A.zip
recording_2026-04-16_10-45-00__scene=scene_20260416_102030_livingroom1__type=human__seq=seq0__cam=B.zip

recording_2026-04-16_11-02-10__scene=scene_20260416_102030_livingroom1__type=human__seq=seq1__cam=A.zip
recording_2026-04-16_11-02-10__scene=scene_20260416_102030_livingroom1__type=human__seq=seq1__cam=B.zip
```

### 3.4 单文件双目打包（bundle）

```text
recording_2026-04-16_10-45-00__scene=scene_20260416_102030_livingroom1__type=human__seq=seq0__stereo=1.zip
```

---

## 4. 自动整理后的目标结构（my_capture 推荐布局）

以 `scene_20260416_102030_livingroom1` 为例，最终会被组织成：

```text
datasets/my_capture/
└── scene_20260416_102030_livingroom1/
    ├── calibration.json
    ├── data.jsonl
    ├── data.mov
    ├── frames2/
    ├── metadata.json
    ├── transforms.json              (Step1 输出)
    ├── mesh_raw.ply                 (Step2 输出)
    ├── mesh_simplified.ply          (Step2 输出)
    ├── seq0/
    │   ├── recording_...cam=A.zip   (上传的原始 zip；后续 Step4 自动解压成 raw1/)
    │   ├── recording_...cam=B.zip   (上传的原始 zip；后续 Step4 自动解压成 raw2/)
    │   ├── raw1/ ...                (Step4 自动生成)
    │   └── raw2/ ...
    └── seq1/
        └── ...
```

---

## 5. 处理逻辑（你上传后系统会做什么）

1) `type=scene`
- 自动导入为一个 `<SCENE>/` 目录
- 自动跑：**Step0-2**
- 可用 `tools/preview_scene_meshes_viser.py` 或 `tools/visualize_viser.py` 预览 mesh

2) `type=human`
- 自动放入 `<SCENE>/<SEQ>/` 目录
- 当同一 `<SCENE> + <SEQ>` 的 **A/B 两个视角都齐全** 后，自动跑：**Step0-15**

> 注意：Step1/Step5 通常在 `embodmocap_sai150` 环境跑，其余步骤在 `embodmocap` 主环境跑（详见 `docs/pipeline_operator_runbook_zh.md`）。

---

## 6. Viser 端口冲突的小贴士（8080 → 8081）

如果你本机 `8080` 已经被占用（例如你自己的数据可视化服务正在用 8080），直接把 demo / 预览换到别的端口即可：

```bash
cd embod_mocap
python tools/visualize_viser.py --xlsx ../datasets/release_demo.xlsx --data_root ../datasets/dataset_demo --stride 2 --scene_mesh simple --mesh_level 1 --port 8081
```

如果你是 SSH 端口转发导致冲突，改本地端口也可以（远程仍是 8080）：

```bash
ssh -p 22 -L 18081:127.0.0.1:8080 <user>@<server>
```

---

## 7. 启动自动化服务（参考命令）

在服务器上运行（建议在 `embodmocap` 主环境里启动它）：

```bash
cd embod_mocap
conda run -n embodmocap python tools/auto_spectacular_rec_service.py \
  --data_root ../datasets/my_capture \
  --config config_fast.yaml \
  --conda conda \
  --env_main embodmocap \
  --env_sai embodmocap_sai150 \
  --mode skip
```

只想“导入并整理目录，不自动跑 Step1-15”时加：

```bash
--no_auto_run
```

