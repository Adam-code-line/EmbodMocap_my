import sys
import json
import os
import re
import numpy as np
import argparse
from scipy.spatial.transform import Rotation as R
from embod_mocap.processor.base import export_cameras_to_ply, run_cmd, write_warning_to_log


def compute_extrinsic_matrix(position, orientation):
    """
    Compute the camera extrinsic matrix from position and quaternion orientation.

    Parameters:
    - position: dict with keys "x", "y", "z" representing the translation vector.
    - orientation: dict with keys "w", "x", "y", "z" representing the quaternion.

    Returns:
    - extrinsic_matrix: A 4x4 numpy array representing the camera extrinsic matrix.
    """
    # Extract quaternion in (x, y, z, w) order as required by scipy
    quaternion = [
        orientation["x"],
        orientation["y"],
        orientation["z"],
        orientation["w"],
    ]
    
    # Convert quaternion to a 3x3 rotation matrix
    rotation = R.from_quat(quaternion)
    rotation_matrix = rotation.as_matrix()  # Get the 3x3 rotation matrix

    # Extract translation vector from position
    translation_vector = np.array([
        position["x"],
        position["y"],
        position["z"],
    ])

    # Construct the 4x4 extrinsic matrix
    extrinsic_matrix = np.eye(4)  # Start with an identity matrix
    extrinsic_matrix[:3, :3] = rotation_matrix  # Set the rotation matrix
    extrinsic_matrix[:3, 3] = translation_vector  # Set the translation vector

    return extrinsic_matrix

def read_jsonl_to_numpy(file_path):
    data = {
        "timestamps": [],
        "frame_id": []
    }

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line.strip())
            if "frames" not in record:
                continue
            if "time" not in record or "number" not in record:
                continue
            data["timestamps"].append(float(record["time"]))
            data["frame_id"].append(int(record["number"]))

    data["timestamps"] = np.asarray(data["timestamps"], dtype=np.float64)
    data["frame_id"] = np.asarray(data["frame_id"], dtype=np.int64)
    return data


def load_intrinsics(raw_dir, down_scale):
    with open(os.path.join(raw_dir, "calibration.json"), "r", encoding="utf-8") as f:
        calibration = json.load(f)

    focal = calibration["cameras"][0]["focalLengthX"] / down_scale
    cx = calibration["cameras"][0]["principalPointX"] / down_scale
    cy = calibration["cameras"][0]["principalPointY"] / down_scale

    return np.array(
        [[focal, 0, cx, 0],
         [0, focal, cy, 0],
         [0, 0, 1, 0],
         [0, 0, 0, 1]],
        dtype=np.float64,
    )


def nearest_frame_id(target_time, frame_timestamps, frame_ids):
    if frame_timestamps.size == 0:
        raise RuntimeError("No frame timestamps found in data.jsonl")

    idx = int(np.searchsorted(frame_timestamps, target_time))
    if idx <= 0:
        return int(frame_ids[0])
    if idx >= frame_timestamps.size:
        return int(frame_ids[-1])

    prev_idx = idx - 1
    next_idx = idx
    if abs(frame_timestamps[next_idx] - target_time) < abs(frame_timestamps[prev_idx] - target_time):
        return int(frame_ids[next_idx])
    return int(frame_ids[prev_idx])


def extract_frame_id_from_path(file_path):
    match = re.search(r"(\d+)(?=\.[^.]+$)", str(file_path))
    if not match:
        return None
    return int(match.group(1))


def infer_frame_ids_from_process_output(raw_frame_ids, process_frame_ids):
    total = len(process_frame_ids)
    if total == 0:
        return []

    if raw_frame_ids.size == 0:
        return list(range(total))

    available_ids = [int(fid) for fid in raw_frame_ids.tolist()]
    available_set = set(available_ids)
    parsed_ids = [fid for fid in process_frame_ids if fid is not None]

    best_offset = 0
    best_hits = -1
    if parsed_ids:
        for candidate_offset in (0, -1, 1):
            hits = sum(1 for fid in parsed_ids if (fid + candidate_offset) in available_set)
            if hits > best_hits:
                best_hits = hits
                best_offset = candidate_offset

    default_ids = available_ids[:total]
    if len(default_ids) < total:
        start = default_ids[-1] + 1 if default_ids else 0
        default_ids.extend(list(range(start, start + (total - len(default_ids)))))

    inferred = []
    for idx, fid in enumerate(process_frame_ids):
        if fid is None:
            inferred.append(int(default_ids[idx]))
        else:
            inferred.append(int(fid + best_offset))

    return inferred


def timestamps_from_frame_ids(frame_ids, raw_frame_ids, raw_timestamps):
    if raw_frame_ids.size == 0:
        return np.arange(len(frame_ids), dtype=np.float64)

    id_to_time = {
        int(fid): float(ts)
        for fid, ts in zip(raw_frame_ids.tolist(), raw_timestamps.tolist())
    }

    timestamps = []
    for frame_id in frame_ids:
        if frame_id in id_to_time:
            timestamps.append(id_to_time[frame_id])
            continue

        nearest_idx = int(np.argmin(np.abs(raw_frame_ids - frame_id)))
        timestamps.append(float(raw_timestamps[nearest_idx]))

    return np.asarray(timestamps, dtype=np.float64)


def load_smooth_trajectory(jsonl_file, frame_info):
    poses = []
    timestamps = []
    with open(jsonl_file, "r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line.strip())
            if "position" not in record or "orientation" not in record or "time" not in record:
                continue
            poses.append(compute_extrinsic_matrix(record["position"], record["orientation"]))
            timestamps.append(float(record["time"]))

    if not poses:
        raise RuntimeError(f"No valid camera poses found in {jsonl_file}")

    frame_ids = [
        nearest_frame_id(ts, frame_info["timestamps"], frame_info["frame_id"])
        for ts in timestamps
    ]

    return (
        np.stack(poses, axis=0),
        np.asarray(timestamps, dtype=np.float64),
        np.asarray(frame_ids, dtype=np.int64),
    )


def load_process_trajectory(transforms_file, frame_info):
    with open(transforms_file, "r", encoding="utf-8") as file:
        transforms = json.load(file)

    frames = transforms.get("frames", [])
    if not frames:
        raise RuntimeError(f"No frames found in {transforms_file}")

    poses = []
    process_frame_ids = []
    for frame in frames:
        matrix = np.asarray(frame.get("transform_matrix", []), dtype=np.float64)
        if matrix.shape != (4, 4):
            continue
        poses.append(matrix)
        process_frame_ids.append(extract_frame_id_from_path(frame.get("file_path", "")))

    if not poses:
        raise RuntimeError(f"No valid transform_matrix entries found in {transforms_file}")

    frame_ids = infer_frame_ids_from_process_output(frame_info["frame_id"], process_frame_ids)
    timestamps = timestamps_from_frame_ids(frame_ids, frame_info["frame_id"], frame_info["timestamps"])

    return (
        np.stack(poses, axis=0),
        timestamps,
        np.asarray(frame_ids, dtype=np.int64),
    )


def save_camera_outputs(raw_dir, K, poses, timestamps, frame_ids):
    np.savez(
        os.path.join(raw_dir, "cameras_sai.npz"),
        K=K,
        timestamps=np.asarray(timestamps, dtype=np.float64),
        frame_ids=np.asarray(frame_ids, dtype=np.int64),
        R=poses[:, :3, :3],
        T=poses[:, :3, 3],
    )
    export_cameras_to_ply(poses, os.path.join(raw_dir, "cameras_sai.ply"))


def process_view(seq_folder, view_name, down_scale, log_file, use_process_fallback=True, fallback_key_frame_distance=0.1):
    raw_dir = os.path.join(seq_folder, view_name)
    data_jsonl = os.path.join(raw_dir, "data.jsonl")
    if not os.path.exists(data_jsonl):
        raise RuntimeError(f"Missing input file: {data_jsonl}")

    frame_info = read_jsonl_to_numpy(data_jsonl)
    if frame_info["frame_id"].size == 0:
        raise RuntimeError(f"No frame records found in {data_jsonl}")

    K = load_intrinsics(raw_dir, down_scale)
    smooth_jsonl = os.path.join(raw_dir, "cameras_sai.jsonl")
    if os.path.exists(smooth_jsonl):
        os.remove(smooth_jsonl)

    run_cmd(f"sai-cli smooth {raw_dir}/ {smooth_jsonl}")

    if os.path.exists(smooth_jsonl) and os.path.getsize(smooth_jsonl) > 0:
        try:
            poses, timestamps, frame_ids = load_smooth_trajectory(smooth_jsonl, frame_info)
            save_camera_outputs(raw_dir, K, poses, timestamps, frame_ids)
            print(f"Smoothing camera for {seq_folder} {view_name} succeeded via sai-cli smooth")
            return
        except Exception as exc:
            warning = f"Smooth output parse failed for {raw_dir}: {exc}"
            print(warning)
            write_warning_to_log(log_file, warning)
    else:
        warning = f"sai-cli smooth produced no output for {raw_dir}"
        print(warning)
        write_warning_to_log(log_file, warning)

    if not use_process_fallback:
        raise RuntimeError(f"Smoothing failed for {raw_dir} and process fallback is disabled")

    kfd_candidates = []
    for candidate in (fallback_key_frame_distance, 0.1, 0.15):
        candidate = float(candidate)
        if candidate not in kfd_candidates:
            kfd_candidates.append(candidate)

    transforms_file = os.path.join(raw_dir, "transforms.json")
    selected_kfd = None
    for kfd in kfd_candidates:
        warning = (
            f"Fallback enabled: rerun camera solve with sai-cli process for {raw_dir} "
            f"(key_frame_distance={kfd})"
        )
        print(warning)
        write_warning_to_log(log_file, warning)

        if os.path.exists(transforms_file):
            os.remove(transforms_file)

        run_cmd(f"sai-cli process {raw_dir}/ {raw_dir}/ --key_frame_distance {kfd}")
        if os.path.exists(transforms_file):
            selected_kfd = kfd
            break

    if selected_kfd is None:
        raise RuntimeError(
            f"Fallback failed: {transforms_file} was not generated "
            f"(tried key_frame_distance={kfd_candidates})"
        )

    poses, timestamps, frame_ids = load_process_trajectory(transforms_file, frame_info)
    save_camera_outputs(raw_dir, K, poses, timestamps, frame_ids)
    print(
        f"Smoothing camera for {seq_folder} {view_name} succeeded via process fallback "
        f"(key_frame_distance={selected_kfd})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Slice views from two videos.")
    parser.add_argument(
        "input_folder",
        type=str,
        help="Path to the sequence folder containing two videos.",
    )
    parser.add_argument(
        "--down_scale",
        type=int,
        default=2,
        help="Downscale factor for the input images",
    )
    parser.add_argument(
        "--proc_v1",
        action="store_true",
        help="Whether to process v1",
    )
    parser.add_argument(
        "--proc_v2",
        action="store_true",
        help="Whether to process v2",
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default=None,
        help="Path to the log file",
    )
    parser.add_argument(
        "--process_fallback",
        dest="process_fallback",
        action="store_true",
        help="Enable fallback to sai-cli process when sai-cli smooth fails",
    )
    parser.add_argument(
        "--no_process_fallback",
        dest="process_fallback",
        action="store_false",
        help="Disable fallback to sai-cli process when sai-cli smooth fails",
    )
    parser.add_argument(
        "--fallback_key_frame_distance",
        type=float,
        default=0.1,
        help="key_frame_distance used when process fallback is triggered",
    )
    parser.set_defaults(process_fallback=True)
    args = parser.parse_args()
    seq_folder = args.input_folder

    has_error = False

    if args.proc_v1:
        try:
            process_view(
                seq_folder=args.input_folder,
                view_name="raw1",
                down_scale=args.down_scale,
                log_file=args.log_file,
                use_process_fallback=args.process_fallback,
                fallback_key_frame_distance=args.fallback_key_frame_distance,
            )
        except Exception as exc:
            has_error = True
            message = f"Smoothing camera for {seq_folder} v1 failed: {exc}"
            print(message)
            write_warning_to_log(args.log_file, message)
    else:
        print(f"Skip smoothing camera for raw1")

    if args.proc_v2:
        try:
            process_view(
                seq_folder=args.input_folder,
                view_name="raw2",
                down_scale=args.down_scale,
                log_file=args.log_file,
                use_process_fallback=args.process_fallback,
                fallback_key_frame_distance=args.fallback_key_frame_distance,
            )
        except Exception as exc:
            has_error = True
            message = f"Smoothing camera for {seq_folder} v2 failed: {exc}"
            print(message)
            write_warning_to_log(args.log_file, message)
    else:
        print(f"Skip smoothing camera for raw2")

    if has_error:
        sys.exit(1)
