"""
使用 Viser 浏览 DATA_ROOT 下多个 scene 的场景 mesh（Step2 输出）。

目标：
    - 不依赖 optim_params.npz，仅预览 scene 级 mesh。
    - （可选）若 scene/seq 下存在 optim_params.npz，则可在同一个 Viser 服务中预览“带人的渲染”（SMPL + 场景）。
    - 支持在 Viser GUI 下拉选择不同录制（scene_folder）。
    - 默认优先展示 mesh_raw.ply（如果不存在则回退 mesh_simplified.ply）。
    - 尝试使用 Viser 自带的分享（share）能力（若当前 viser 版本支持）。

示例：
    python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --port 8080

    # 指定默认 scene（启动后默认加载该 scene）
    python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --default_scene recording_2026-04-15_23-33-13

    # 若要更流畅的人体预览，可调低采样（减少帧数/顶点数）
    python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --human_stride 2 --human_max_frames 600 --human_mesh_level 1
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import trimesh
import viser
import viser.transforms as tf

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class SceneEntry:
    name: str
    path: Path
    mesh_raw: Optional[Path]
    mesh_simplified: Optional[Path]
    transforms_json: Optional[Path]


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except Exception:
        return path.expanduser()


def _find_scene_entry(scene_dir: Path) -> Optional[SceneEntry]:
    if not scene_dir.is_dir():
        return None

    mesh_raw = scene_dir / "mesh_raw.ply"
    mesh_simplified = scene_dir / "mesh_simplified.ply"
    transforms_json = scene_dir / "transforms.json"

    has_any_mesh = mesh_raw.exists() or mesh_simplified.exists()
    if not has_any_mesh:
        return None

    return SceneEntry(
        name=scene_dir.name,
        path=_safe_resolve(scene_dir),
        mesh_raw=_safe_resolve(mesh_raw) if mesh_raw.exists() else None,
        mesh_simplified=_safe_resolve(mesh_simplified) if mesh_simplified.exists() else None,
        transforms_json=_safe_resolve(transforms_json) if transforms_json.exists() else None,
    )


def scan_scenes(data_root: Path, scene_glob: str = "*") -> Dict[str, SceneEntry]:
    data_root = _safe_resolve(data_root)
    entries: Dict[str, SceneEntry] = {}
    for scene_dir in sorted(data_root.glob(scene_glob)):
        entry = _find_scene_entry(scene_dir)
        if entry is None:
            continue
        entries[entry.name] = entry
    return entries


def choose_mesh_path(entry: SceneEntry, mesh_mode: str) -> Optional[Path]:
    raw = entry.mesh_raw
    simplified = entry.mesh_simplified

    if mesh_mode == "prefer_raw":
        return raw or simplified
    if mesh_mode == "prefer_simplified":
        return simplified or raw
    if mesh_mode == "raw_only":
        return raw
    if mesh_mode == "simplified_only":
        return simplified
    raise ValueError(f"Unsupported mesh_mode: {mesh_mode}")


def _await_if_needed(value):
    if not inspect.isawaitable(value):
        return value

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(value)

    if loop.is_running():
        return None
    return loop.run_until_complete(value)


def try_get_share_url(server: viser.ViserServer) -> Optional[str]:
    """
    Best-effort: viser 的 share API 在不同版本中可能不同。
    我们尽量兼容常见命名；如果不可用则返回 None。
    """

    candidates = [
        ("request_share_url", True),
        ("get_share_url", True),
        ("share_url", False),
        ("share_link", False),
    ]

    for attr_name, is_callable in candidates:
        if not hasattr(server, attr_name):
            continue
        attr = getattr(server, attr_name)
        try:
            value = attr() if (is_callable and callable(attr)) else attr
            value = _await_if_needed(value)
        except Exception:
            continue
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _load_trimesh(mesh_path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(str(mesh_path))
    if isinstance(mesh, trimesh.Scene):
        geoms = list(mesh.geometry.values())
        if not geoms:
            raise ValueError(f"Empty trimesh.Scene loaded from {mesh_path}")
        mesh = trimesh.util.concatenate(geoms)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Unexpected mesh type: {type(mesh)} from {mesh_path}")
    return mesh


def _discover_seq_optim(scene_path: Path) -> List[Tuple[str, Path]]:
    """Discover seq* folders with optim_params.npz under a scene directory."""
    seq_items: List[Tuple[str, Path]] = []
    if not scene_path.exists() or not scene_path.is_dir():
        return seq_items

    for child in scene_path.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("seq"):
            continue
        optim_path = child / "optim_params.npz"
        if optim_path.exists():
            seq_items.append((child.name, _safe_resolve(optim_path)))

    def _sort_key(item: Tuple[str, Path]):
        name = item[0]
        suffix = name[3:]
        if suffix.isdigit():
            return (0, int(suffix))
        return (1, name)

    seq_items.sort(key=_sort_key)
    return seq_items


def _try_load_smpl_model():
    """Best-effort lazy loader for SMPL model used by human demo."""
    try:
        from embod_mocap.human.configs import BMODEL
        from embod_mocap.human.smpl import SMPL

        body_model_dir = Path(BMODEL.FLDR)
        if not body_model_dir.exists():
            raise FileNotFoundError(
                f"SMPL assets not found: {body_model_dir}. "
                f"Please run: bash tools/download_body_models.sh (repo root)"
            )

        body_model = SMPL(
            model_path=BMODEL.FLDR,
            gender="neutral",
            extra_joints_regressor=BMODEL.JOINTS_REGRESSOR_EXTRA,
            create_transl=False,
        )
        return body_model, None
    except Exception as exc:
        return None, str(exc)


def _load_motion_data(optim_params_path: Path) -> Dict:
    """Load required arrays from optim_params.npz for SMPL visualization."""
    import numpy as np

    optim_params = np.load(str(optim_params_path), allow_pickle=True)

    required = [
        "transl",
        "global_orient",
        "body_pose",
        "betas",
        "K1",
        "K2",
        "R1",
        "R2",
        "T1",
        "T2",
    ]
    missing = [k for k in required if k not in optim_params]
    if missing:
        raise KeyError(f"optim_params is missing keys: {missing}")

    transl = optim_params["transl"]
    return {
        "transl": transl,
        "global_orient": optim_params["global_orient"],
        "body_pose": optim_params["body_pose"],
        "betas": optim_params["betas"],
        "K1": optim_params["K1"],
        "K2": optim_params["K2"],
        "R1": optim_params["R1"],
        "R2": optim_params["R2"],
        "T1": optim_params["T1"],
        "T2": optim_params["T2"],
        "num_frames": int(len(transl)),
    }


def _compute_smpl_vertices(body_model, transl, global_orient, body_pose, betas):
    """Compute SMPL vertices (numpy) for all selected frames."""
    import numpy as np
    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    body_model = body_model.to(device)

    num_frames = int(len(transl))

    transl_t = torch.from_numpy(np.asarray(transl)).float().to(device)  # [T, 3]
    global_orient_t = torch.from_numpy(np.asarray(global_orient)).float().to(device)  # [T, 1, 3, 3]
    body_pose_t = torch.from_numpy(np.asarray(body_pose)).float().to(device)  # [T, 23, 3, 3]
    betas_t = torch.from_numpy(np.asarray(betas)).float().to(device)  # [1, 10] or [T, 10]

    if betas_t.shape[0] == 1:
        betas_t = betas_t.repeat(num_frames, 1)

    transl_t = transl_t.view(-1, 3)
    global_orient_t = global_orient_t.view(-1, 1, 3, 3)
    body_pose_t = body_pose_t.view(-1, 23, 3, 3)

    with torch.no_grad():
        output = body_model(
            transl=transl_t,
            global_orient=global_orient_t,
            body_pose=body_pose_t,
            betas=betas_t,
            pose2rot=False,
        )
        vertices = output.vertices.detach().cpu().numpy()

    faces = getattr(body_model, "faces", None)
    if faces is None:
        raise RuntimeError("SMPL model does not expose faces.")
    return vertices, faces


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse multiple scene meshes with Viser (mesh_raw/mesh_simplified).")
    parser.add_argument("--data_root", required=True, help="Dataset root that contains scene folders.")
    parser.add_argument("--scene_glob", default="*", help="Glob pattern under data_root to find scenes (default: '*').")
    parser.add_argument("--host", default="127.0.0.1", help="Viser server host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8080, help="Viser server port (default: 8080).")
    parser.add_argument(
        "--auto_refresh_seconds",
        type=float,
        default=0.0,
        help="Auto rescan scenes list every N seconds (0 disables).",
    )
    parser.add_argument(
        "--default_scene",
        default=None,
        help="Default scene folder name. If provided and exists, load it on start.",
    )
    parser.add_argument(
        "--mesh_mode",
        default="prefer_raw",
        choices=["prefer_raw", "prefer_simplified", "raw_only", "simplified_only"],
        help="Mesh selection policy (default: prefer_raw).",
    )
    parser.add_argument(
        "--human_stride",
        type=int,
        default=2,
        help="Frame stride for human demo (optim_params.npz). Larger is faster.",
    )
    parser.add_argument(
        "--human_max_frames",
        type=int,
        default=600,
        help="Maximum frames for human demo; -1 means all.",
    )
    parser.add_argument(
        "--human_mesh_level",
        type=int,
        default=1,
        choices=[0, 1, 2],
        help="SMPL mesh downsampling level for human demo: 0=full, 1=downsample, 2=coarser.",
    )
    parser.add_argument(
        "--print_share_url",
        action="store_true",
        help="Try to print share URL on start (if supported by viser version).",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    scenes = scan_scenes(data_root, scene_glob=args.scene_glob)
    scene_names: List[str] = sorted(scenes.keys())

    if not scene_names:
        print(f"[WARN] No scenes found under: {_safe_resolve(data_root)}")
        print("[HINT] Please run Step2 first to generate mesh_raw.ply / mesh_simplified.ply.")
        scene_names = ["-"]

    default_scene = args.default_scene if (args.default_scene in scenes) else scene_names[0]

    server = viser.ViserServer(host=args.host, port=args.port)
    server.scene.set_up_direction("+z")

    current_mesh_handle = None
    current_scene_name = None

    human_body_model = None
    human_body_model_error = None
    human_mesh_sampler = None
    human_seq_map: Dict[str, Path] = {}
    human_loaded_scene: Optional[str] = None
    human_loaded_seq: Optional[str] = None
    human_frame_nodes = []
    human_mesh_handles = []
    human_cam1_handle = None
    human_cam2_handle = None
    human_num_frames = 0
    human_current_frame = 0
    human_is_playing = False
    human_next_step_t = time.time()

    def update_scene(scene_name: str, mesh_mode: str) -> None:
        nonlocal current_mesh_handle, current_scene_name

        if scene_name == "-" or scene_name not in scenes:
            return

        entry = scenes[scene_name]
        mesh_path = choose_mesh_path(entry, mesh_mode)

        # Update GUI text first so users get immediate feedback.
        gui_scene_path.value = str(entry.path)
        gui_transforms.value = "OK" if entry.transforms_json is not None else "MISSING"
        gui_mesh_path.value = str(mesh_path) if mesh_path is not None else "-"

        if mesh_path is None:
            print(f"[WARN] No mesh found for scene={scene_name} under {entry.path}")
            return

        print(f"[INFO] Loading mesh: {mesh_path}")
        t0 = time.time()
        mesh = _load_trimesh(mesh_path)
        dt = time.time() - t0
        print(f"[INFO] Loaded mesh in {dt:.2f}s: vertices={len(mesh.vertices)}, faces={len(mesh.faces)}")

        if current_mesh_handle is not None:
            try:
                current_mesh_handle.remove()
            except Exception:
                pass
            current_mesh_handle = None

        # Prefer preserving vertex colors if present.
        has_vertex_colors = (
            hasattr(mesh.visual, "vertex_colors")
            and mesh.visual.vertex_colors is not None
            and len(mesh.visual.vertex_colors) == len(mesh.vertices)
        )

        if has_vertex_colors:
            current_mesh_handle = server.scene.add_mesh_trimesh(
                name="/scene/mesh",
                mesh=mesh,
                wxyz=(1.0, 0.0, 0.0, 0.0),
                position=(0.0, 0.0, 0.0),
            )
        else:
            current_mesh_handle = server.scene.add_mesh_simple(
                name="/scene/mesh",
                vertices=mesh.vertices,
                faces=mesh.faces,
                color=(200, 200, 200),
                wireframe=False,
            )

        current_scene_name = scene_name
        try:
            current_mesh_handle.visible = bool(gui_show_scene_mesh.value)
        except Exception:
            pass
        print(f"[INFO] Showing scene={scene_name} (mesh_mode={mesh_mode})")

    def _clear_human_nodes() -> None:
        nonlocal human_frame_nodes, human_mesh_handles, human_cam1_handle, human_cam2_handle
        nonlocal human_num_frames, human_current_frame, human_is_playing, human_loaded_scene, human_loaded_seq

        for node in human_frame_nodes:
            try:
                node.remove()
            except Exception:
                pass
        human_frame_nodes = []
        human_mesh_handles = []

        if human_cam1_handle is not None:
            try:
                human_cam1_handle.remove()
            except Exception:
                pass
            human_cam1_handle = None
        if human_cam2_handle is not None:
            try:
                human_cam2_handle.remove()
            except Exception:
                pass
            human_cam2_handle = None

        human_num_frames = 0
        human_current_frame = 0
        human_is_playing = False
        human_loaded_scene = None
        human_loaded_seq = None

        gui_human_frame.disabled = True
        gui_human_frame.min = 0.0
        gui_human_frame.max = 1.0
        gui_human_frame.value = 0.0
        gui_human_play_pause.name = "Play"
        gui_human_play_pause.disabled = True

    def _apply_human_visibility() -> None:
        show_smpl = bool(gui_human_show_smpl.value)
        show_cameras = bool(gui_human_show_cameras.value)

        for h in human_mesh_handles:
            try:
                h.visible = show_smpl
            except Exception:
                pass
        if human_cam1_handle is not None:
            try:
                human_cam1_handle.visible = show_cameras
            except Exception:
                pass
        if human_cam2_handle is not None:
            try:
                human_cam2_handle.visible = show_cameras
            except Exception:
                pass

    def _set_human_frame(frame_idx: int) -> None:
        nonlocal human_current_frame

        if human_num_frames <= 0:
            return
        frame_idx = int(max(0, min(human_num_frames - 1, frame_idx)))
        if frame_idx == human_current_frame:
            return

        try:
            human_frame_nodes[human_current_frame].visible = False
        except Exception:
            pass
        try:
            human_frame_nodes[frame_idx].visible = True
        except Exception:
            pass
        human_current_frame = frame_idx

    def _refresh_human_sequences(scene_name: Optional[str], keep_selection: bool = True) -> None:
        nonlocal human_seq_map

        if scene_name is None or scene_name == "-" or scene_name not in scenes:
            human_seq_map = {}
            gui_human_seq.options = ["-"]
            gui_human_seq.value = "-"
            gui_human_optim_path.value = "-"
            gui_human_status.value = "No valid scene selected."
            return

        entry = scenes[scene_name]
        seq_items = _discover_seq_optim(entry.path)
        human_seq_map = {name: path for name, path in seq_items}
        options = list(human_seq_map.keys()) or ["-"]

        current = gui_human_seq.value
        gui_human_seq.options = options
        if keep_selection and current in options:
            gui_human_seq.value = current
        else:
            gui_human_seq.value = options[0]

        if gui_human_seq.value in human_seq_map:
            gui_human_optim_path.value = str(human_seq_map[gui_human_seq.value])
            gui_human_load.disabled = False
        else:
            gui_human_optim_path.value = "-"
            gui_human_load.disabled = True

        if options == ["-"]:
            gui_human_status.value = "No optim_params.npz found under this scene (run Step15 first)."
        else:
            gui_human_status.value = f"Found {len(human_seq_map)} seq(s) with optim_params.npz."

    def _ensure_body_model_loaded() -> bool:
        nonlocal human_body_model, human_body_model_error

        if human_body_model is not None:
            return True
        if human_body_model_error is not None:
            return False

        gui_human_status.value = "Loading SMPL model... (first time may take a while)"
        model, err = _try_load_smpl_model()
        human_body_model = model
        human_body_model_error = err
        if human_body_model is None:
            gui_human_status.value = f"Failed to load SMPL model: {human_body_model_error}"
            return False
        gui_human_status.value = "SMPL model loaded."
        return True

    def _maybe_get_mesh_sampler(mesh_level: int):
        nonlocal human_mesh_sampler
        if mesh_level <= 0:
            return None
        if human_mesh_sampler is not None:
            return human_mesh_sampler
        try:
            from embod_mocap.utils.mesh_sampler import SMPLMeshSampler

            human_mesh_sampler = SMPLMeshSampler()
            return human_mesh_sampler
        except Exception as exc:
            gui_human_status.value = f"Warning: SMPLMeshSampler unavailable, fallback to full mesh. ({exc})"
            return None

    def _load_human_sequence(scene_name: str, seq_name: str) -> None:
        nonlocal human_num_frames, human_current_frame, human_loaded_scene, human_loaded_seq
        nonlocal human_cam1_handle, human_cam2_handle

        if scene_name not in scenes:
            gui_human_status.value = "Invalid scene."
            return
        if seq_name not in human_seq_map:
            gui_human_status.value = "Invalid sequence (optim_params.npz not found)."
            return
        if not _ensure_body_model_loaded():
            return

        optim_path = human_seq_map[seq_name]
        gui_human_optim_path.value = str(optim_path)
        gui_human_status.value = f"Loading motion: {optim_path}"

        try:
            motion = _load_motion_data(optim_path)
        except Exception as exc:
            gui_human_status.value = f"Failed to load optim_params.npz: {exc}"
            return

        total_frames = int(motion["num_frames"])
        stride = int(max(1, int(gui_human_stride.value)))
        max_frames = int(gui_human_max_frames.value)
        if max_frames <= 0:
            max_frames = -1
        max_frames_effective = total_frames if max_frames == -1 else min(total_frames, max_frames)
        frame_indices = list(range(0, max_frames_effective, stride))
        if not frame_indices:
            frame_indices = [0]

        # Compute SMPL vertices for sampled frames.
        try:
            import numpy as np

            gui_human_status.value = f"Computing SMPL vertices... (frames={len(frame_indices)}/{total_frames})"
            verts, faces = _compute_smpl_vertices(
                human_body_model,
                motion["transl"][frame_indices],
                motion["global_orient"][frame_indices],
                motion["body_pose"][frame_indices],
                motion["betas"],
            )

            mesh_level = int(gui_human_mesh_level.value)
            sampler = _maybe_get_mesh_sampler(mesh_level)
            if sampler is not None and mesh_level > 0:
                num_v_before = int(verts.shape[1])
                verts = sampler.downsample(verts, from_level=0, to_level=mesh_level)
                ds_faces = sampler.get_faces(level=mesh_level)
                if ds_faces is not None:
                    faces = ds_faces
                num_v_after = int(verts.shape[1])
                print(f"[INFO] Downsampled SMPL mesh: {num_v_before} -> {num_v_after} vertices (mesh_level={mesh_level})")

            verts = np.asarray(verts)
            faces = np.asarray(faces)
        except Exception as exc:
            gui_human_status.value = f"Failed to compute SMPL vertices: {exc}"
            return

        # Clear previous nodes and build new ones.
        _clear_human_nodes()

        human_num_frames = int(len(frame_indices))
        human_current_frame = 0
        human_loaded_scene = scene_name
        human_loaded_seq = seq_name

        human_frame_nodes.clear()
        human_mesh_handles.clear()

        for i in range(human_num_frames):
            frame_node = server.scene.add_frame(f"/human/frames/{i}", show_axes=False)
            frame_node.visible = i == 0
            human_frame_nodes.append(frame_node)

            mesh_handle = server.scene.add_mesh_simple(
                name=f"/human/frames/{i}/smpl",
                vertices=verts[i],
                faces=faces,
                color=(100, 150, 200),
                opacity=1.0,
                wireframe=False,
            )
            human_mesh_handles.append(mesh_handle)

        # Add camera frustums (static, using the first sampled frame).
        try:
            frame0 = int(frame_indices[0])
            R1 = motion["R1"][frame0]
            T1 = motion["T1"][frame0]
            K1 = motion["K1"]

            import numpy as np

            c2w1 = np.eye(4)
            c2w1[:3, :3] = R1
            c2w1[:3, 3] = T1
            camera_center1 = c2w1[:3, 3]
            camera_rotation1 = c2w1[:3, :3]
            q1 = tf.SO3.from_matrix(camera_rotation1).wxyz
            fov1 = 2 * np.arctan(K1[1, 2] / K1[1, 1])
            aspect1 = K1[0, 0] / K1[1, 1]

            human_cam1_handle = server.scene.add_camera_frustum(
                name="/human/camera1",
                fov=float(fov1),
                aspect=float(aspect1),
                wxyz=q1,
                position=tuple(camera_center1.tolist()),
                scale=0.1,
                color=(255, 0, 0),
            )

            R2 = motion["R2"][frame0]
            T2 = motion["T2"][frame0]
            K2 = motion["K2"]

            c2w2 = np.eye(4)
            c2w2[:3, :3] = R2
            c2w2[:3, 3] = T2
            camera_center2 = c2w2[:3, 3]
            camera_rotation2 = c2w2[:3, :3]
            q2 = tf.SO3.from_matrix(camera_rotation2).wxyz
            fov2 = 2 * np.arctan(K2[1, 2] / K2[1, 1])
            aspect2 = K2[0, 0] / K2[1, 1]

            human_cam2_handle = server.scene.add_camera_frustum(
                name="/human/camera2",
                fov=float(fov2),
                aspect=float(aspect2),
                wxyz=q2,
                position=tuple(camera_center2.tolist()),
                scale=0.1,
                color=(0, 255, 0),
            )
        except Exception as exc:
            print(f"[WARN] Failed to add camera frustums: {exc}")

        gui_human_frame.disabled = False if human_num_frames > 1 else True
        gui_human_frame.min = 0.0
        gui_human_frame.max = float(max(1, human_num_frames - 1))
        gui_human_frame.value = 0.0
        gui_human_play_pause.disabled = human_num_frames <= 1
        gui_human_play_pause.name = "Play"

        _apply_human_visibility()
        gui_human_status.value = (
            f"Loaded human demo: scene={scene_name}, seq={seq_name}, frames={human_num_frames} "
            f"(stride={stride}, max_frames={'all' if max_frames == -1 else max_frames})"
        )

    def refresh_scenes(force_reload_current: bool) -> bool:
        nonlocal scenes, scene_names
        scenes = scan_scenes(data_root, scene_glob=args.scene_glob)
        scene_names = sorted(scenes.keys()) or ["-"]

        gui_scene_selector.options = scene_names
        selected_before = gui_scene_selector.value
        if selected_before not in scene_names:
            gui_scene_selector.value = scene_names[0]

        selected_after = gui_scene_selector.value
        selection_changed = selected_after != selected_before
        if selection_changed or force_reload_current:
            update_scene(selected_after, gui_mesh_mode.value)
        _refresh_human_sequences(selected_after, keep_selection=True)
        return selection_changed

    with server.gui.add_folder("Scene Mesh Preview"):
        gui_scene_selector = server.gui.add_dropdown("Scene", options=scene_names, initial_value=default_scene)
        gui_mesh_mode = server.gui.add_dropdown(
            "Mesh Mode",
            options=["prefer_raw", "prefer_simplified", "raw_only", "simplified_only"],
            initial_value=args.mesh_mode,
        )
        gui_show_scene_mesh = server.gui.add_checkbox("Show Scene Mesh", True)
        gui_scene_path = server.gui.add_text("Scene Path", initial_value="-", disabled=True)
        gui_mesh_path = server.gui.add_text("Mesh File", initial_value="-", disabled=True)
        gui_transforms = server.gui.add_text("transforms.json", initial_value="-", disabled=True)

    with server.gui.add_folder("Human Demo (SMPL + Scene)"):
        gui_human_seq = server.gui.add_dropdown("Sequence", options=["-"], initial_value="-")
        gui_human_optim_path = server.gui.add_text("optim_params.npz", initial_value="-", disabled=True)
        gui_human_status = server.gui.add_text("Status", initial_value="Select a scene to scan optim_params.npz", disabled=True)

        gui_human_stride = server.gui.add_slider(
            "Stride",
            min=1.0,
            max=30.0,
            step=1.0,
            initial_value=float(max(1, int(args.human_stride))),
        )
        default_max_frames = 0 if int(args.human_max_frames) == -1 else int(args.human_max_frames)
        gui_human_max_frames = server.gui.add_slider(
            "Max Frames (0=all)",
            min=0.0,
            max=5000.0,
            step=50.0,
            initial_value=float(max(0, default_max_frames)),
        )
        gui_human_mesh_level = server.gui.add_dropdown(
            "SMPL Mesh Level",
            options=["0", "1", "2"],
            initial_value=str(int(args.human_mesh_level)),
        )

        gui_human_show_smpl = server.gui.add_checkbox("Show SMPL", True)
        gui_human_show_cameras = server.gui.add_checkbox("Show Cameras", True)

        gui_human_load = server.gui.add_button("Load Human", disabled=True)
        gui_human_unload = server.gui.add_button("Unload Human", disabled=False)

        gui_human_frame = server.gui.add_slider(
            "Frame",
            min=0.0,
            max=1.0,
            step=1.0,
            initial_value=0.0,
            disabled=True,
        )
        gui_human_play_pause = server.gui.add_button("Play", disabled=True)
        gui_human_fps = server.gui.add_slider("FPS", min=1.0, max=60.0, step=1.0, initial_value=30.0)

    with server.gui.add_folder("Actions"):
        gui_refresh = server.gui.add_button("Refresh Scenes", disabled=False)
        gui_share_btn = server.gui.add_button("Get Share URL", disabled=False)
        gui_share_url = server.gui.add_text("Share URL", initial_value="-", disabled=True)

    @gui_scene_selector.on_update
    def _(_) -> None:
        update_scene(gui_scene_selector.value, gui_mesh_mode.value)
        _clear_human_nodes()
        _refresh_human_sequences(gui_scene_selector.value, keep_selection=False)

    @gui_mesh_mode.on_update
    def _(_) -> None:
        update_scene(gui_scene_selector.value, gui_mesh_mode.value)

    @gui_show_scene_mesh.on_update
    def _(_) -> None:
        if current_mesh_handle is None:
            return
        try:
            current_mesh_handle.visible = bool(gui_show_scene_mesh.value)
        except Exception:
            pass

    @gui_refresh.on_click
    def _(_) -> None:
        refresh_scenes(force_reload_current=True)

    @gui_share_btn.on_click
    def _(_) -> None:
        url = try_get_share_url(server)
        if url is None:
            url = "(share not supported by this viser version)"
        gui_share_url.value = url
        print(f"[INFO] Share URL: {url}")

    @gui_human_seq.on_update
    def _(_) -> None:
        if gui_human_seq.value in human_seq_map:
            gui_human_optim_path.value = str(human_seq_map[gui_human_seq.value])
            gui_human_load.disabled = False
        else:
            gui_human_optim_path.value = "-"
            gui_human_load.disabled = True

    @gui_human_show_smpl.on_update
    def _(_) -> None:
        _apply_human_visibility()

    @gui_human_show_cameras.on_update
    def _(_) -> None:
        _apply_human_visibility()

    @gui_human_load.on_click
    def _(_) -> None:
        if current_scene_name is None:
            gui_human_status.value = "No scene selected."
            return
        if gui_human_seq.value not in human_seq_map:
            gui_human_status.value = "No valid sequence selected."
            return
        _load_human_sequence(current_scene_name, gui_human_seq.value)

    @gui_human_unload.on_click
    def _(_) -> None:
        _clear_human_nodes()
        gui_human_status.value = "Unloaded human demo."

    @gui_human_frame.on_update
    def _(_) -> None:
        try:
            v = float(gui_human_frame.value)
        except Exception:
            return
        _set_human_frame(int(round(v)))

    @gui_human_play_pause.on_click
    def _(_) -> None:
        nonlocal human_is_playing, human_next_step_t
        if human_num_frames <= 1:
            return
        human_is_playing = not human_is_playing
        gui_human_play_pause.name = "Pause" if human_is_playing else "Play"
        human_next_step_t = time.time()

    print(f"Viser server running on remote: http://{args.host}:{args.port}")
    print("If using SSH port-forwarding, open local: http://127.0.0.1:18080")

    if args.print_share_url:
        url = try_get_share_url(server)
        if url is not None:
            gui_share_url.value = url
            print(f"[INFO] Share URL: {url}")
        else:
            print("[INFO] Share URL not available in this viser version (or share not configured).")

    # Initial load.
    update_scene(gui_scene_selector.value, gui_mesh_mode.value)
    _refresh_human_sequences(gui_scene_selector.value, keep_selection=False)

    last_refresh_t = time.time()
    while True:
        now = time.time()

        if human_is_playing and human_num_frames > 1:
            fps = gui_human_fps.value
            if fps is None or not isinstance(fps, (int, float)) or fps <= 0:
                fps = 30.0
            step_dt = 1.0 / float(fps)
            if now >= human_next_step_t:
                cur = gui_human_frame.value
                cur_i = 0 if cur is None else int(cur)
                nxt = (cur_i + 1) % human_num_frames
                gui_human_frame.value = float(nxt)
                human_next_step_t = now + step_dt
            sleep_dt = max(0.0, min(0.05, human_next_step_t - now))
        else:
            sleep_dt = 0.2

        time.sleep(sleep_dt)
        if args.auto_refresh_seconds <= 0:
            continue
        if time.time() - last_refresh_t < args.auto_refresh_seconds:
            continue
        last_refresh_t = time.time()
        try:
            refresh_scenes(force_reload_current=False)
        except Exception as exc:
            print(f"[WARN] Auto refresh failed: {exc}")


if __name__ == "__main__":
    main()
