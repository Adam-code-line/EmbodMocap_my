#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_ITEMS = [
    "calibration.json",
    "data.jsonl",
    "data.mov",
    "metadata.json",
    "frames2",
]


def run_command(cmd: List[str]) -> Tuple[int, str, str, bool]:
    try:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return cp.returncode, cp.stdout, cp.stderr, True
    except FileNotFoundError:
        return 127, "", "", False


def safe_file_size(path: str) -> Optional[int]:
    if not os.path.exists(path) or os.path.isdir(path):
        return None
    return os.path.getsize(path)


def count_files_recursive(root: str) -> Optional[int]:
    if not os.path.isdir(root):
        return None
    total = 0
    for _, _, files in os.walk(root):
        total += len([f for f in files if not f.startswith(".")])
    return total


def inspect_json_file(path: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "exists": os.path.exists(path),
        "valid_json": False,
        "top_keys": [],
        "error": None,
    }
    if not result["exists"]:
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        result["valid_json"] = True
        if isinstance(obj, dict):
            result["top_keys"] = sorted(list(obj.keys()))
        else:
            result["top_keys"] = [f"<non-dict:{type(obj).__name__}>"]
    except Exception as e:
        result["error"] = str(e)
    return result


def update_time_stats(stats: Dict[str, Any], key: str, value: Any) -> None:
    if not isinstance(value, (int, float)):
        return
    key_l = key.lower()
    if not ("time" in key_l or "stamp" in key_l or key_l in {"t", "ts", "timestamp"}):
        return

    if stats["time_min"] is None or value < stats["time_min"]:
        stats["time_min"] = value
    if stats["time_max"] is None or value > stats["time_max"]:
        stats["time_max"] = value
    stats["time_count"] += 1


def walk_obj_for_time(obj: Any, stats: Dict[str, Any], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            update_time_stats(stats, str(k), v)
            walk_obj_for_time(v, stats, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            walk_obj_for_time(v, stats, depth + 1)


def inspect_jsonl(path: str, max_lines: int = 0) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "exists": os.path.exists(path),
        "lines": 0,
        "non_empty_lines": 0,
        "parse_errors": 0,
        "parse_error_samples": [],
        "top_level_keys": Counter(),
        "text_hints": Counter(),
        "time_min": None,
        "time_max": None,
        "time_count": 0,
    }
    if not result["exists"]:
        return result

    hint_words = ["image", "frame", "depth", "imu", "gyro", "acc", "pose"]

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f, start=1):
            if max_lines > 0 and idx > max_lines:
                break
            result["lines"] += 1
            line = line.strip()
            if not line:
                continue
            result["non_empty_lines"] += 1

            lower_line = line.lower()
            for w in hint_words:
                if w in lower_line:
                    result["text_hints"][w] += 1

            try:
                obj = json.loads(line)
            except Exception:
                result["parse_errors"] += 1
                if len(result["parse_error_samples"]) < 5:
                    result["parse_error_samples"].append(idx)
                continue

            if isinstance(obj, dict):
                for k in obj.keys():
                    result["top_level_keys"][str(k)] += 1
            walk_obj_for_time(obj, result)

    return result


def probe_mov(path: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "exists": os.path.exists(path),
        "ffprobe_available": False,
        "ffprobe_ok": False,
        "probe_error": None,
        "codec_name": None,
        "width": None,
        "height": None,
        "avg_frame_rate": None,
        "duration": None,
        "nb_frames": None,
    }
    if not result["exists"]:
        return result

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    code, out, err, found = run_command(cmd)
    result["ffprobe_available"] = found
    if not found:
        return result

    if code != 0:
        result["probe_error"] = (err or out).strip()
        return result

    try:
        data = json.loads(out)
    except Exception as e:
        result["probe_error"] = f"ffprobe json parse error: {e}"
        return result

    streams = data.get("streams", []) if isinstance(data, dict) else []
    v_stream = None
    for s in streams:
        if isinstance(s, dict) and s.get("codec_type") == "video":
            v_stream = s
            break

    fmt = data.get("format", {}) if isinstance(data, dict) else {}
    if isinstance(v_stream, dict):
        result["codec_name"] = v_stream.get("codec_name")
        result["width"] = v_stream.get("width")
        result["height"] = v_stream.get("height")
        result["avg_frame_rate"] = v_stream.get("avg_frame_rate")
        result["nb_frames"] = v_stream.get("nb_frames")
        result["duration"] = v_stream.get("duration") or fmt.get("duration")
    else:
        result["duration"] = fmt.get("duration")

    result["ffprobe_ok"] = True
    return result


def ffmpeg_decode_test(path: str) -> Dict[str, Any]:
    result = {
        "exists": os.path.exists(path),
        "ffmpeg_available": False,
        "decode_ok": None,
        "decode_error": None,
    }
    if not result["exists"]:
        return result

    cmd = ["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-f", "null", "-"]
    code, out, err, found = run_command(cmd)
    result["ffmpeg_available"] = found
    if not found:
        return result

    result["decode_ok"] = (code == 0)
    if code != 0:
        result["decode_error"] = (err or out).strip()
    return result


def inspect_scene(scene_path: str, max_jsonl_lines: int) -> Dict[str, Any]:
    scene = {
        "path": scene_path,
        "exists": os.path.isdir(scene_path),
        "required": {},
        "frames2_count": None,
        "calibration": {},
        "metadata": {},
        "jsonl": {},
        "mov_probe": {},
        "mov_decode": {},
    }

    if not scene["exists"]:
        return scene

    for item in REQUIRED_ITEMS:
        p = os.path.join(scene_path, item)
        scene["required"][item] = {
            "exists": os.path.exists(p),
            "is_dir": os.path.isdir(p),
            "size": safe_file_size(p),
        }

    scene["frames2_count"] = count_files_recursive(os.path.join(scene_path, "frames2"))
    scene["calibration"] = inspect_json_file(os.path.join(scene_path, "calibration.json"))
    scene["metadata"] = inspect_json_file(os.path.join(scene_path, "metadata.json"))
    scene["jsonl"] = inspect_jsonl(os.path.join(scene_path, "data.jsonl"), max_lines=max_jsonl_lines)
    scene["mov_probe"] = probe_mov(os.path.join(scene_path, "data.mov"))
    scene["mov_decode"] = ffmpeg_decode_test(os.path.join(scene_path, "data.mov"))
    return scene


def to_float_or_none(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def compare_scenes(target: Dict[str, Any], demo: Dict[str, Any]) -> List[str]:
    issues: List[str] = []

    if not target.get("exists"):
        issues.append("target scene path does not exist or is not a directory")
        return issues
    if not demo.get("exists"):
        issues.append("demo scene path does not exist or is not a directory")
        return issues

    for item in REQUIRED_ITEMS:
        if not target["required"][item]["exists"]:
            issues.append(f"target missing required item: {item}")

    t_jsonl = target["jsonl"]
    d_jsonl = demo["jsonl"]
    if t_jsonl.get("parse_errors", 0) > 0:
        samples = t_jsonl.get("parse_error_samples", [])
        issues.append(f"target data.jsonl has parse errors: {t_jsonl['parse_errors']} lines, samples={samples}")

    t_decode = target["mov_decode"]
    if t_decode.get("ffmpeg_available") and t_decode.get("decode_ok") is False:
        issues.append("target data.mov cannot decode first frame via ffmpeg")

    t_probe = target["mov_probe"]
    if t_probe.get("ffprobe_available") and not t_probe.get("ffprobe_ok"):
        issues.append("target data.mov ffprobe failed")

    t_lines = t_jsonl.get("non_empty_lines") or 0
    d_lines = d_jsonl.get("non_empty_lines") or 0
    if d_lines > 0 and t_lines < max(100, int(d_lines * 0.3)):
        issues.append(f"target data.jsonl lines much smaller than demo ({t_lines} vs {d_lines})")

    t_frames2 = target.get("frames2_count") or 0
    d_frames2 = demo.get("frames2_count") or 0
    if d_frames2 > 0 and t_frames2 < max(20, int(d_frames2 * 0.3)):
        issues.append(f"target frames2 count much smaller than demo ({t_frames2} vs {d_frames2})")

    t_duration = to_float_or_none(target["mov_probe"].get("duration"))
    d_duration = to_float_or_none(demo["mov_probe"].get("duration"))
    if t_duration is not None and d_duration is not None and t_duration < max(2.0, d_duration * 0.3):
        issues.append(f"target video duration much shorter than demo ({t_duration:.2f}s vs {d_duration:.2f}s)")

    d_keys = set(k for k, c in demo["jsonl"].get("top_level_keys", {}).items() if c > 10)
    t_keys = set(k for k, c in target["jsonl"].get("top_level_keys", {}).items() if c > 10)
    missing_keys = sorted(list(d_keys - t_keys))
    if missing_keys:
        preview = ",".join(missing_keys[:8])
        issues.append(f"target data.jsonl appears to miss frequent key groups seen in demo: {preview}")

    return issues


def print_scene(scene: Dict[str, Any], title: str) -> None:
    print(f"\n===== {title} =====")
    print(f"path: {scene['path']}")
    print(f"exists: {scene['exists']}")
    if not scene["exists"]:
        return

    print("required items:")
    for item in REQUIRED_ITEMS:
        info = scene["required"][item]
        print(
            f"  - {item}: exists={info['exists']} is_dir={info['is_dir']} size={info['size']}"
        )

    print(f"frames2 file count: {scene['frames2_count']}")

    cali = scene["calibration"]
    print(
        "calibration.json: "
        f"valid_json={cali.get('valid_json')} top_keys={','.join(cali.get('top_keys', [])[:15])}"
    )

    meta = scene["metadata"]
    print(
        "metadata.json: "
        f"valid_json={meta.get('valid_json')} top_keys={','.join(meta.get('top_keys', [])[:15])}"
    )

    j = scene["jsonl"]
    top_keys = j.get("top_level_keys", Counter())
    top_keys_str = ", ".join([f"{k}:{c}" for k, c in top_keys.most_common(12)])
    hint_str = ", ".join([f"{k}:{c}" for k, c in j.get("text_hints", Counter()).most_common()])
    print(
        "data.jsonl: "
        f"lines={j.get('lines')} non_empty={j.get('non_empty_lines')} "
        f"parse_errors={j.get('parse_errors')} "
        f"time_count={j.get('time_count')} time_min={j.get('time_min')} time_max={j.get('time_max')}"
    )
    print(f"data.jsonl top keys: {top_keys_str}")
    print(f"data.jsonl text hints: {hint_str}")

    mp = scene["mov_probe"]
    print(
        "data.mov probe: "
        f"ffprobe_available={mp.get('ffprobe_available')} ffprobe_ok={mp.get('ffprobe_ok')} "
        f"codec={mp.get('codec_name')} size={mp.get('width')}x{mp.get('height')} "
        f"fps={mp.get('avg_frame_rate')} duration={mp.get('duration')} nb_frames={mp.get('nb_frames')}"
    )
    if mp.get("probe_error"):
        print(f"data.mov probe_error: {mp.get('probe_error')}")

    md = scene["mov_decode"]
    print(
        "data.mov decode: "
        f"ffmpeg_available={md.get('ffmpeg_available')} decode_ok={md.get('decode_ok')}"
    )
    if md.get("decode_error"):
        print(f"data.mov decode_error: {md.get('decode_error')}")


def print_verdict(issues: List[str]) -> None:
    print("\n===== Verdict =====")
    if not issues:
        print("No hard mismatch detected by static checks.")
        print("If target still fails while demo passes, likely causes are:")
        print("  1) target motion/content quality causes zero valid map output")
        print("  2) target timestamps are legal JSON but semantically inconsistent")
        print("  3) edge-case incompatibility between this target capture and current SDK")
        return

    print("Potential blockers found:")
    for i, issue in enumerate(issues, start=1):
        print(f"  {i}. {issue}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare target scene vs demo scene for SAI step1 diagnostics."
    )
    parser.add_argument("--target", required=True, help="target scene path")
    parser.add_argument("--demo", required=True, help="demo scene path")
    parser.add_argument(
        "--max-jsonl-lines",
        type=int,
        default=0,
        help="read first N jsonl lines (0 means all)",
    )
    args = parser.parse_args()

    target = inspect_scene(args.target, max_jsonl_lines=args.max_jsonl_lines)
    demo = inspect_scene(args.demo, max_jsonl_lines=args.max_jsonl_lines)

    print_scene(target, "Target Scene")
    print_scene(demo, "Demo Scene")

    issues = compare_scenes(target, demo)
    print_verdict(issues)


if __name__ == "__main__":
    main()
