# scene_20260413_161617 在服务器 Step1 失败排障记录

## 最终结论

本次失败已经可以确定为：

1. 不是 xlsx 字段问题（step1 不依赖 `v1_start`/`v2_start`）。
2. 不是数据目录缺文件或权限问题（核心文件齐全，且可写）。
3. 不是“默认模式才失败”的问题（`default` 与 `--mono` 都失败，退出码均为 1）。
4. 不是 PATH 串环境问题（`sai-cli` 与 Python 均绑定到同一个 conda 环境）。

因此当前最可能是服务器侧 SAI 运行时兼容性/依赖问题，或 Linux 下该数据在当前 SDK 版本上的映射异常。

## 新增证据（本轮定位）

### 1) 数据与权限

- `calibration.json` / `data.jsonl` / `data.mov` / `metadata.json` 均存在。
- `frames2` 文件数：`126`。
- `touch/rm` 测试通过，目录可写。

### 2) CLI 与 Python 环境绑定

```bash
which sai-cli
type -a sai-cli
head -n 1 "$(which sai-cli)"
python -c "import sys, spectacularAI; print(sys.executable); print(spectacularAI.__file__)"
```

结果显示：

- `sai-cli` 位于 `/home/wubin/miniconda3/envs/embodmocap/bin/sai-cli`
- shebang 为 `/home/wubin/miniconda3/envs/embodmocap/bin/python3.11`
- Python 可执行同样在该环境

说明不存在“命令走系统 Python、脚本走 conda Python”的错绑。

### 3) 版本信息

- `spectacularAI`：`1.35.0`
- `pip show sai-cli`：未找到单独包

这不一定异常。很多项目把 CLI 入口作为 `spectacularAI` 的 console script 暴露，而不是独立 `sai-cli` wheel。

### 4) 直接复现（含退出码）

```bash
sai-cli process $SCENE $SCENE --key_frame_distance 0.1
# exit code = 1

sai-cli process $SCENE $SCENE --mono --key_frame_distance 0.1
# exit code = 1
```

两次都输出：

- `Selected device type: ios-tof`
- `Mapping failed: no output generated`

### 5) 日志开关可见性

`sai-cli process -h | grep -Ei "debug|verbose|log|trace"` 无结果，CLI 未直接暴露 debug/verbose 参数。

## 代码路径说明

step1 由 [embod_mocap/run_stages.py](../embod_mocap/run_stages.py) 调用 [embod_mocap/processor/sai.sh](../embod_mocap/processor/sai.sh)，当前 `sai.sh` 仅执行：

```bash
sai-cli process ${1} ${1} --key_frame_distance ${2:-0.05}
```

## 根因判断（按概率）

1. 服务器运行时依赖与本地不一致（系统库、解码链路、驱动/动态库）。
2. `spectacularAI==1.35.0` 在当前 Linux 环境对该采集数据触发映射失败。
3. 数据本身边界问题（概率较低；同数据在本地通过）。

> 注：`xformers` 的 `FutureWarning` 与本次 Step1 失败无直接关系。

## 建议处置

### A. 先做 A/B 诊断（最快）

在服务器上用官方 demo 数据单独跑一次 `sai-cli process`：

- 若 demo 也失败：优先判定为服务器环境问题。
- 若 demo 成功、仅该 scene 失败：倾向于“数据与当前 SDK 版本组合问题”。

#### 一键 A/B 脚本（可直接执行）

在 `~/EmbodMocap_dev/embod_mocap` 下执行：

```bash
cat > ./tools/run_sai_ab.sh <<'BASH'
#!/usr/bin/env bash
set -u
set -o pipefail

# 用法：
#   bash tools/run_sai_ab.sh <target_scene> [demo_scene] [log_root]
# 示例：
#   bash tools/run_sai_ab.sh ../datasets/my_capture/scene_20260413_161617 ../datasets/dataset_demo/scene_demo ../logs

TARGET_SCENE="${1:-../datasets/my_capture/scene_20260413_161617}"
DEMO_SCENE="${2:-}"
LOG_ROOT="${3:-../logs}"

TS="$(date +%F_%H%M%S)"
OUT_DIR="${LOG_ROOT}/sai_ab_${TS}"
mkdir -p "${OUT_DIR}"

LAST_CODE=0

run_case() {
	local label="$1"
	local scene="$2"
	shift 2

	local log_file="${OUT_DIR}/${label}.log"

	{
		echo "===== CASE: ${label} ====="
		echo "date=$(date)"
		echo "scene=${scene}"
		echo "which_sai=$(which sai-cli 2>/dev/null || true)"
		python - <<'PY'
import sys
try:
		import spectacularAI
		print("python=", sys.executable)
		print("spectacularAI=", getattr(spectacularAI, "__version__", "unknown"))
		print("spectacularAI_module=", spectacularAI.__file__)
except Exception as e:
		print("python=", sys.executable)
		print("spectacularAI_import_error=", e)
PY
		ls -lh "${scene}/calibration.json" "${scene}/data.jsonl" "${scene}/data.mov" "${scene}/metadata.json" 2>/dev/null || true
		find "${scene}/frames2" -type f 2>/dev/null | wc -l | awk '{print "frames2_count=" $1}'
		echo "cmd=sai-cli process \"${scene}\" \"${scene}\" $*"
	} | tee "${log_file}"

	set +e
	sai-cli process "${scene}" "${scene}" "$@" 2>&1 | tee -a "${log_file}"
	local code=${PIPESTATUS[0]}
	set -e

	echo "exit_code=${code}" | tee -a "${log_file}"
	echo "${label}=${code}" >> "${OUT_DIR}/codes.txt"
	LAST_CODE=${code}
}

echo "Logs will be written to: ${OUT_DIR}"

run_case target_default "${TARGET_SCENE}" --key_frame_distance 0.1
target_default=${LAST_CODE}

run_case target_mono "${TARGET_SCENE}" --mono --key_frame_distance 0.1
target_mono=${LAST_CODE}

demo_default=-1
demo_mono=-1

if [[ -n "${DEMO_SCENE}" && -d "${DEMO_SCENE}" ]]; then
	run_case demo_default "${DEMO_SCENE}" --key_frame_distance 0.1
	demo_default=${LAST_CODE}

	run_case demo_mono "${DEMO_SCENE}" --mono --key_frame_distance 0.1
	demo_mono=${LAST_CODE}
else
	echo "DEMO scene not provided or not found, skip demo A/B" | tee -a "${OUT_DIR}/summary.txt"
fi

{
	echo "===== SUMMARY ====="
	echo "target_default=${target_default}"
	echo "target_mono=${target_mono}"
	echo "demo_default=${demo_default}"
	echo "demo_mono=${demo_mono}"

	if [[ ${demo_default} -eq 1 || ${demo_mono} -eq 1 ]]; then
		echo "判读：demo 也失败，优先排查服务器环境/依赖问题。"
	elif [[ ${demo_default} -eq 0 && ${target_default} -eq 1 ]]; then
		echo "判读：demo 成功但目标 scene 失败，倾向数据与当前 SDK 组合问题。"
	elif [[ ${target_default} -eq 0 || ${target_mono} -eq 0 ]]; then
		echo "判读：目标 scene 至少一条链路成功，可继续流程。"
	else
		echo "判读：信息不足，请结合日志末尾报错进一步分析。"
	fi
} | tee "${OUT_DIR}/summary.txt"

echo "Done. See: ${OUT_DIR}"
BASH

chmod +x ./tools/run_sai_ab.sh
```

执行：

```bash
# 推荐：带 demo 做完整 A/B
bash ./tools/run_sai_ab.sh ../datasets/my_capture/scene_20260413_161617 ../datasets/dataset_demo/<你的demo场景目录> ../logs

# 仅测目标 scene
bash ./tools/run_sai_ab.sh ../datasets/my_capture/scene_20260413_161617
```

产物：

- `../logs/sai_ab_时间戳/target_default.log`
- `../logs/sai_ab_时间戳/target_mono.log`
- `../logs/sai_ab_时间戳/demo_default.log`（若提供 demo）
- `../logs/sai_ab_时间戳/demo_mono.log`（若提供 demo）
- `../logs/sai_ab_时间戳/summary.txt`

### B. 做版本对齐对照

把本地可运行环境与服务器同时记录并对齐：

```bash
python -c "import sys; print(sys.version)"
pip show spectacularAI
python -c "import spectacularAI; print(spectacularAI.__file__)"
```

必要时尝试升级/降级 `spectacularAI` 做二分验证。

### C. 补齐原生依赖可见性

导出 `spectacularAI` 包内 `.so` 依赖并检查缺库（`ldd ... | grep 'not found'`），用于定位动态库问题。

### D. 流程脚本建议

由于 `mono` 也失败，当前不建议仅做 `default -> mono` 回退作为最终修复。应先完成 A/B 与版本对齐，再决定是否做脚本层兜底。

## 当前状态

- 该 scene 在服务器上 Step1 仍 blocked。
- Step2-5 暂不能继续（Step2 依赖 Step1 产物如 `transforms.json`）。
