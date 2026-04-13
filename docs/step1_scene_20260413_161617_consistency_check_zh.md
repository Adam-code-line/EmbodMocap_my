# scene_20260413_161617 本地/服务器一致性复核（补充说明）

## 目的

针对 Step1 持续失败，补充验证“是否为数据不一致或命令误用导致”。

## 复核结论

1. 本地与服务器的核心输入文件字节级一致（SHA256 完全相同）。
2. 本地与服务器的 `data.mov` 关键流信息一致（codec、分辨率、帧率、帧数、时长一致）。
3. 服务器 `AttributeError: module 'spectacularAI' has no attribute 'version'` 属于查询方式错误，不是运行时故障。
4. 当前最重要新增线索是版本差异：本地可用环境为 `spectacularAI==1.50.0`，服务器历史记录为 `1.35.0`。在短序列边界样本上，这一版本差异有较高概率导致“本地可过、服务器不过”。

## 证据明细

### A. SHA256 对齐（本地与服务器一致）

- calibration.json
  - `56f90b37061b4b685c3b0e13b9b12d5b09b9dcef00e79117c18ada2f1a9f5c6d`
- data.jsonl
  - `d07b323f1266fe2aaa59d89e77eda8665d88ee3e69bcca8d84c0e87e150a6371`
- data.mov
  - `a558c3748386f89e7de2abcba7516f5c1ea707d5c5074b3342c8f07d67cb2f58`
- metadata.json
  - `ccd33b0b6edce42f812f13564ea9372c5eb6a6267b6a066986dd5635de841123`

### B. ffprobe 对齐（本地与服务器一致）

- codec_name: `h264`
- width: `1920`
- height: `1440`
- avg_frame_rate: `37800/1259`
- nb_frames: `126`
- duration: `4.196667`

### C. spectacularAI 查询报错说明

你在服务器执行的命令中使用了：

```bash
print(spectacularAI.version)
print(spectacularAI.file)
```

这两个属性在该模块中不存在，所以抛出 `AttributeError`，这不代表 SAI 运行异常。

建议改为：

```bash
python -c "import sys,platform,spectacularAI; from importlib.metadata import version; print(sys.version); print(platform.platform()); print(version('spectacularAI')); print(spectacularAI.__file__)"
```

## 补充判断

结合主文档中的参数扫描与 A/B 结论，可将问题收敛为：

1. 不是数据损坏或文件不一致。
2. 不是 Step1 参数配置错误。
3. 更可能是“短时长边界样本 + SDK 版本鲁棒性差异”共同作用。

其中，`4.196667s / 126 帧` 的序列本身可观测性边界较明显，旧版本 SDK 更容易触发 `Mapping failed: no output generated`。

## 建议动作（按优先级）

1. 在服务器新建隔离环境做版本 A/B（优先对齐到本地可用版本）。
2. 若版本对齐后仍失败，直接同步本地 Step1 产物（`transforms.json` + `images/` + `sparse_pc.ply` + transforms 中引用的深度路径）。
3. 中长期按采集规范重录：15-30 秒、明显平移、尽量形成回环。
