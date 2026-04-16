"""
使用 Viser 浏览 DATA_ROOT 下多个 scene 的场景 mesh（Step2 输出）。

目标：
    - 不依赖 optim_params.npz，仅预览 scene 级 mesh。
    - 支持在 Viser GUI 下拉选择不同录制（scene_folder）。
    - 默认优先展示 mesh_raw.ply（如果不存在则回退 mesh_simplified.ply）。
    - 尝试使用 Viser 自带的分享（share）能力（若当前 viser 版本支持）。

示例：
    python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --port 8080

    # 指定默认 scene（启动后默认加载该 scene）
    python tools/preview_scene_meshes_viser.py --data_root ../datasets/my_capture --default_scene recording_2026-04-15_23-33-13
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import trimesh
import viser


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse multiple scene meshes with Viser (mesh_raw/mesh_simplified).")
    parser.add_argument("--data_root", required=True, help="Dataset root that contains scene folders.")
    parser.add_argument("--scene_glob", default="*", help="Glob pattern under data_root to find scenes (default: '*').")
    parser.add_argument("--host", default="127.0.0.1", help="Viser server host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8080, help="Viser server port (default: 8080).")
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
        print(f"[INFO] Showing scene={scene_name} (mesh_mode={mesh_mode})")

    with server.gui.add_folder("Scene Mesh Preview"):
        gui_scene_selector = server.gui.add_dropdown("Scene", options=scene_names, initial_value=default_scene)
        gui_mesh_mode = server.gui.add_dropdown(
            "Mesh Mode",
            options=["prefer_raw", "prefer_simplified", "raw_only", "simplified_only"],
            initial_value=args.mesh_mode,
        )
        gui_scene_path = server.gui.add_text("Scene Path", initial_value="-", disabled=True)
        gui_mesh_path = server.gui.add_text("Mesh File", initial_value="-", disabled=True)
        gui_transforms = server.gui.add_text("transforms.json", initial_value="-", disabled=True)

    with server.gui.add_folder("Actions"):
        gui_refresh = server.gui.add_button("Refresh Scenes", disabled=False)
        gui_share_btn = server.gui.add_button("Get Share URL", disabled=False)
        gui_share_url = server.gui.add_text("Share URL", initial_value="-", disabled=True)

    @gui_scene_selector.on_update
    def _(_) -> None:
        update_scene(gui_scene_selector.value, gui_mesh_mode.value)

    @gui_mesh_mode.on_update
    def _(_) -> None:
        update_scene(gui_scene_selector.value, gui_mesh_mode.value)

    @gui_refresh.on_click
    def _(_) -> None:
        nonlocal scenes, scene_names
        scenes = scan_scenes(data_root, scene_glob=args.scene_glob)
        scene_names = sorted(scenes.keys()) or ["-"]
        gui_scene_selector.options = scene_names
        if gui_scene_selector.value not in scene_names:
            gui_scene_selector.value = scene_names[0]
        update_scene(gui_scene_selector.value, gui_mesh_mode.value)

    @gui_share_btn.on_click
    def _(_) -> None:
        url = try_get_share_url(server)
        if url is None:
            url = "(share not supported by this viser version)"
        gui_share_url.value = url
        print(f"[INFO] Share URL: {url}")

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

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
