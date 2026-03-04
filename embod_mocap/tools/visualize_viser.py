"""
Visualize SMPL motion and scene mesh with viser.
Supports timeline scrubbing, camera display, and static scene rendering.

Usage:
    python visualize_viser.py path/to/seq0
    
    python visualize_viser.py path/to/seq0 --port 8888
    
    python visualize_viser.py path/to/seq0 --max_frames 100
    
    python visualize_viser.py path/to/seq0 --stride 5
    
    python visualize_viser.py path/to/seq0 --max_frames 500 --stride 10 --port 8080

Arguments:
    seq_path: sequence folder path (contains optim_params.npz)
    --port: viser server port (default 8080)
    --max_frames: maximum loaded frame count (default: all frames)
    --stride: frame stride (default 1, load every frame)
    
Examples:
    python visualize_viser.py datasets/dataset_raw/0505_capture/0505apartment1/seq0
    
    python visualize_viser.py datasets/dataset_raw/0505_capture/0505apartment1/seq0 --stride 10
"""
import argparse
import numpy as np
import viser
import viser.transforms as tf
import time
import trimesh
from pathlib import Path


def load_smpl_model():
    """Load the SMPL model."""
    import sys
    from pathlib import Path
    
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    
    from embod_mocap.human.configs import BMODEL
    from embod_mocap.human.smpl import SMPL
    
    body_model = SMPL(
        model_path=BMODEL.FLDR,
        gender='neutral',
        extra_joints_regressor=BMODEL.JOINTS_REGRESSOR_EXTRA,
        create_transl=False,
    )
    return body_model


def load_data(seq_path, mesh_path):
    """Load optim_params.npz and the scene mesh."""
    import trimesh
    
    optim_params = np.load(seq_path, allow_pickle=True)
    
    transl = optim_params['transl']  # [T, 3]
    global_orient = optim_params['global_orient']  # [T, 1, 3, 3]
    body_pose = optim_params['body_pose']  # [T, 23, 3, 3]
    betas = optim_params['betas']  # [T, 10]
    
    K1 = optim_params['K1']  # [3, 3]
    K2 = optim_params['K2']  # [3, 3]
    R1 = optim_params['R1']  # [T, 3, 3]
    R2 = optim_params['R2']  # [T, 3, 3]
    T1 = optim_params['T1']  # [T, 3]
    T2 = optim_params['T2']  # [T, 3]
    
    mesh_path = Path(mesh_path)
    mesh_simplified_path = mesh_path.parent / 'mesh_simplified.ply'
    
    if not mesh_simplified_path.exists():
        print(f"Warning: {mesh_simplified_path} not found, using mesh_raw.ply")
        mesh_simplified_path = mesh_path
    
    print(f"Loading mesh from: {mesh_simplified_path}")
    scene_mesh = trimesh.load(str(mesh_simplified_path))
    
    vertices = scene_mesh.vertices
    faces = scene_mesh.faces
    
    vertex_colors = None
    if hasattr(scene_mesh.visual, 'vertex_colors') and scene_mesh.visual.vertex_colors is not None:
        vertex_colors = scene_mesh.visual.vertex_colors[:, :3]  # RGB only, drop alpha
        print(f"Loaded mesh with {len(vertices)} vertices and vertex colors")
    else:
        print(f"Loaded mesh with {len(vertices)} vertices (no colors)")
    
    return {
        'transl': transl,
        'global_orient': global_orient,
        'body_pose': body_pose,
        'betas': betas,
        'K1': K1, 'K2': K2,
        'R1': R1, 'R2': R2,
        'T1': T1, 'T2': T2,
        'scene_vertices': vertices,
        'scene_faces': faces,
        'scene_colors': vertex_colors,
        'num_frames': len(transl),
    }


def compute_smpl_vertices(body_model, transl, global_orient, body_pose, betas):
    """Compute SMPL vertices."""
    import torch
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    body_model = body_model.to(device)
    
    num_frames = len(transl)
    
    transl = torch.from_numpy(transl).float().to(device)  # [T, 3]
    global_orient = torch.from_numpy(global_orient).float().to(device)  # [T, 1, 3, 3]
    body_pose = torch.from_numpy(body_pose).float().to(device)  # [T, 23, 3, 3]
    betas = torch.from_numpy(betas).float().to(device)  # [1, 10] or [T, 10]
    
    if betas.shape[0] == 1:
        betas = betas.repeat(num_frames, 1)  # [T, 10]
    
    # Reshape
    transl = transl.view(-1, 3)
    global_orient = global_orient.view(-1, 1, 3, 3)
    body_pose = body_pose.view(-1, 23, 3, 3)
    
    with torch.no_grad():
        output = body_model(
            transl=transl,
            global_orient=global_orient,
            body_pose=body_pose,
            betas=betas,
            pose2rot=False,
        )
        vertices = output.vertices.cpu().numpy()
    
    return vertices, body_model.faces


class MotionSceneViewer:
    def __init__(self, data, body_model, port=8080, max_frames=None, stride=1, high_quality=False):
        self.server = viser.ViserServer(port=port)
        self.server.scene.set_up_direction("+z")
        self.data = data
        self.body_model = body_model
        self.high_quality = high_quality
        
        total_frames = data['num_frames']
        
        if max_frames == -1:
            max_frames = total_frames
        
        frame_indices = list(range(0, min(max_frames, total_frames), stride))
        self.frame_indices = frame_indices
        self.num_frames = len(frame_indices)
        
        print(f"Loading {self.num_frames} frames (max_frames={max_frames}, stride={stride}, total={total_frames})")
        
        scene_vertices = data['scene_vertices']
        scene_min = scene_vertices.min(axis=0)
        scene_max = scene_vertices.max(axis=0)
        scene_center = (scene_min + scene_max) / 2
        scene_size = np.linalg.norm(scene_max - scene_min)
        
        print(f"Scene bounds: min={scene_min}, max={scene_max}")
        print(f"Scene center: {scene_center}")
        print(f"Scene size: {scene_size}")
        
        print("Computing SMPL vertices...")
        self.smpl_vertices, self.smpl_faces = compute_smpl_vertices(
            body_model,
            data['transl'][frame_indices],
            data['global_orient'][frame_indices],
            data['body_pose'][frame_indices],
            data['betas'],
        )
        print(f"Computed {len(self.smpl_vertices)} frames")
        
        self.add_scene_mesh()
        
        self.add_grid_floor()
        
        if self.high_quality:
            self.setup_lighting()
        
        transl = data['transl'][frame_indices]
        transl_min = transl.min(axis=0)
        transl_max = transl.max(axis=0)
        transl_center = (transl_min + transl_max) / 2
        transl_range = np.linalg.norm(transl_max - transl_min)
        
        print(f"Human motion bounds: min={transl_min}, max={transl_max}")
        print(f"Human motion center: {transl_center}")
        print(f"Human motion range: {transl_range}")
        
        camera_distance = transl_range * 1.2
        camera_height = transl_range * 0.8
        
        camera_position = np.array([
            transl_center[0],
            transl_center[1] - camera_distance,
            transl_center[2] + camera_height
        ])
        
        look_at = transl_center
        
        print(f"Setting camera at: {camera_position}, looking at: {look_at}")
        
        @self.server.on_client_connect
        def _(client: viser.ClientHandle) -> None:
            client.camera.position = camera_position
            client.camera.look_at = look_at
        
        self.setup_gui()
        
        self.frame_nodes = []
        self.mesh_handles = []
        self.cam1_handles = []
        self.cam2_handles = []
        
        self.create_frames()
    
    def add_scene_mesh(self):
        """Add static scene mesh (does not change over time)."""
        vertices = self.data['scene_vertices']
        faces = self.data['scene_faces']
        vertex_colors = self.data['scene_colors']
        
        print(f"Adding scene mesh with {len(vertices)} vertices and {len(faces)} faces")
        
        if vertex_colors is not None:
            import trimesh
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            mesh.visual.vertex_colors = vertex_colors
            self.server.scene.add_mesh_trimesh(
                name="/scene/mesh",
                mesh=mesh,
                wxyz=(1.0, 0.0, 0.0, 0.0),
                position=(0.0, 0.0, 0.0),
            )
            print("Scene mesh loaded with vertex colors")
        else:
            self.server.scene.add_mesh_simple(
                name="/scene/mesh",
                vertices=vertices,
                faces=faces,
                color=(200, 200, 200),
                wireframe=False,
            )
            print("Scene mesh loaded with default color")
    
    def add_grid_floor(self):
        """Add a grid floor."""
        scene_vertices = self.data['scene_vertices']
        floor_z = scene_vertices[:, 2].min()
        
        scene_x_min = scene_vertices[:, 0].min()
        scene_x_max = scene_vertices[:, 0].max()
        scene_y_min = scene_vertices[:, 1].min()
        scene_y_max = scene_vertices[:, 1].max()
        
        scene_x_range = scene_x_max - scene_x_min
        scene_y_range = scene_y_max - scene_y_min
        
        x_margin = scene_x_range * 0.2
        y_margin = scene_y_range * 0.2
        
        x_min = scene_x_min - x_margin
        x_max = scene_x_max + x_margin
        y_min = scene_y_min - y_margin
        y_max = scene_y_max + y_margin
        
        grid_spacing = 0.5
        
        x_min = np.floor(x_min / grid_spacing) * grid_spacing
        x_max = np.ceil(x_max / grid_spacing) * grid_spacing
        y_min = np.floor(y_min / grid_spacing) * grid_spacing
        y_max = np.ceil(y_max / grid_spacing) * grid_spacing
        
        print(f"Grid floor range: x=[{x_min:.2f}, {x_max:.2f}], y=[{y_min:.2f}, {y_max:.2f}]")
        
        x_lines = np.arange(x_min, x_max + grid_spacing, grid_spacing)
        for x in x_lines:
            start = np.array([x, y_min, floor_z])
            end = np.array([x, y_max, floor_z])
            self.server.scene.add_spline_catmull_rom(
                name=f"/grid/x_{x:.2f}",
                positions=np.array([start, end]),
                color=(150, 150, 150),
                line_width=1.0,
            )
        
        y_lines = np.arange(y_min, y_max + grid_spacing, grid_spacing)
        for y in y_lines:
            start = np.array([x_min, y, floor_z])
            end = np.array([x_max, y, floor_z])
            self.server.scene.add_spline_catmull_rom(
                name=f"/grid/y_{y:.2f}",
                positions=np.array([start, end]),
                color=(150, 150, 150),
                line_width=1.0,
            )
        
        print(f"Added grid floor at z={floor_z:.2f} (scene min z)")
    
    def setup_lighting(self):
        """Configure high-quality lighting and shadows."""
        print("Setting up high-quality lighting and shadows...")
        
        self.server.scene.configure_default_lights(enabled=True, cast_shadow=True)
        
        scene_vertices = self.data['scene_vertices']
        scene_center = scene_vertices.mean(axis=0)
        scene_min = scene_vertices.min(axis=0)
        scene_max = scene_vertices.max(axis=0)
        scene_size = np.linalg.norm(scene_max - scene_min)
        
        main_light_dir = scene_center + np.array([scene_size * 0.3, -scene_size * 0.3, scene_size * 0.8])
        self.server.scene.add_light_directional(
            name="/lighting/main",
            color=(255, 250, 240),
            intensity=2.0,  # 2.5 * 0.8 = 2.0
            cast_shadow=True,
            wxyz=self.compute_light_direction(main_light_dir, scene_center),
        )
        
        fill_light_dir = scene_center + np.array([-scene_size * 0.5, scene_size * 0.3, scene_size * 0.5])
        self.server.scene.add_light_directional(
            name="/lighting/fill",
            color=(200, 220, 255),
            intensity=0.8,  # 1.0 * 0.8 = 0.8
            cast_shadow=False,
            wxyz=self.compute_light_direction(fill_light_dir, scene_center),
        )
        
        light_height = scene_max[2] - 0.5
        
        self.server.scene.add_light_point(
            name="/lighting/point1",
            position=(scene_center[0], scene_center[1], light_height),
            color=(255, 245, 230),
            intensity=16.0,  # 20.0 * 0.8 = 16.0
            cast_shadow=True,
        )
        
        self.server.scene.add_light_point(
            name="/lighting/point2",
            position=(scene_min[0] + scene_size * 0.3, scene_min[1] + scene_size * 0.3, light_height),
            color=(255, 240, 220),
            intensity=12.0,  # 15.0 * 0.8 = 12.0
            cast_shadow=True,
        )
        
        self.server.scene.add_light_point(
            name="/lighting/point3",
            position=(scene_max[0] - scene_size * 0.3, scene_max[1] - scene_size * 0.3, light_height),
            color=(255, 240, 220),
            intensity=12.0,  # 15.0 * 0.8 = 12.0
            cast_shadow=True,
        )
        
        print("High-quality lighting configured: 2 directional lights + 3 point lights with shadows")
    
    def compute_light_direction(self, light_pos, target_pos):
        """Compute quaternion that points a light toward target."""
        import viser.transforms as tf
        
        direction = target_pos - light_pos
        direction = direction / np.linalg.norm(direction)
        
        default_dir = np.array([0, 0, -1])
        
        v = np.cross(default_dir, direction)
        s = np.linalg.norm(v)
        c = np.dot(default_dir, direction)
        
        if s < 1e-6:
            if c > 0:
                return (1.0, 0.0, 0.0, 0.0)
            else:
                return (0.0, 1.0, 0.0, 0.0)
        
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))
        
        return tf.SO3.from_matrix(R).wxyz
    
    def setup_gui(self):
        """Set up GUI controls."""
        gui_reset_up = self.server.gui.add_button(
            "Reset up direction",
            hint="Set the camera control 'up' direction to the current camera's 'up'.",
        )
        
        @gui_reset_up.on_click
        def _(event: viser.GuiEvent) -> None:
            client = event.client
            assert client is not None
            client.camera.up_direction = tf.SO3(client.camera.wxyz) @ np.array([0.0, 0.0, 1.0])
        
        self.gui_show_smpl = self.server.gui.add_checkbox("Show SMPL", True)
        
        @self.gui_show_smpl.on_update
        def _(_) -> None:
            self.smpl_handle.visible = self.gui_show_smpl.value
        
        self.gui_show_cameras = self.server.gui.add_checkbox("Show Cameras", True)
        
        @self.gui_show_cameras.on_update
        def _(_) -> None:
            self.cam1_handle.visible = self.gui_show_cameras.value
            self.cam2_handle.visible = self.gui_show_cameras.value
        
        self.camsize_slider = self.server.gui.add_slider(
            "Camera Size",
            min=0.01,
            max=0.5,
            step=0.01,
            initial_value=0.1,
        )
        
        @self.camsize_slider.on_update
        def _(_) -> None:
            self.cam1_handle.scale = self.camsize_slider.value
            self.cam2_handle.scale = self.camsize_slider.value
    
    def create_frames(self):
        """Create SMPL meshes and cameras for all frames."""
        self.server.scene.add_frame("/frames", show_axes=False)
        
        self.frame_nodes = []
        self.mesh_handles = []
        
        for i in range(self.num_frames):
            frame_node = self.server.scene.add_frame(f"/frames/{i}", show_axes=False)
            frame_node.visible = (i == 0)
            self.frame_nodes.append(frame_node)
            
            mesh_handle = self.server.scene.add_mesh_simple(
                name=f"/frames/{i}/smpl",
                vertices=self.smpl_vertices[i],
                faces=self.smpl_faces,
                color=(100, 150, 200),
                opacity=1.0,
                wireframe=False,
            )
            self.mesh_handles.append(mesh_handle)
        
        frame_idx = self.frame_indices[0]
        
        R1 = self.data['R1'][frame_idx]
        T1 = self.data['T1'][frame_idx]
        K1 = self.data['K1']
        
        c2w1 = np.eye(4)
        c2w1[:3, :3] = R1
        c2w1[:3, 3] = T1
        
        camera_center1 = c2w1[:3, 3]
        camera_rotation1 = c2w1[:3, :3]
        
        q1 = tf.SO3.from_matrix(camera_rotation1).wxyz
        fov1 = 2 * np.arctan(K1[1, 2] / K1[1, 1])
        aspect1 = K1[0, 0] / K1[1, 1]
        
        self.cam1_handle = self.server.scene.add_camera_frustum(
            name="/camera1",
            fov=fov1,
            aspect=aspect1,
            wxyz=q1,
            position=camera_center1,
            scale=0.1,
            color=(255, 0, 0),
        )
        
        R2 = self.data['R2'][frame_idx]
        T2 = self.data['T2'][frame_idx]
        K2 = self.data['K2']
        
        c2w2 = np.eye(4)
        c2w2[:3, :3] = R2
        c2w2[:3, 3] = T2
        
        camera_center2 = c2w2[:3, 3]
        camera_rotation2 = c2w2[:3, :3]
        
        q2 = tf.SO3.from_matrix(camera_rotation2).wxyz
        fov2 = 2 * np.arctan(K2[1, 2] / K2[1, 1])
        aspect2 = K2[0, 0] / K2[1, 1]
        
        self.cam2_handle = self.server.scene.add_camera_frustum(
            name="/camera2",
            fov=fov2,
            aspect=aspect2,
            wxyz=q2,
            position=camera_center2,
            scale=0.1,
            color=(0, 255, 0),
        )
    
    def update_frame(self, display_frame_idx):
        """Update to a target frame."""
        frame_idx = self.frame_indices[display_frame_idx]
        
        for i, frame_node in enumerate(self.frame_nodes):
            frame_node.visible = (i == display_frame_idx)
        
        R1 = self.data['R1'][frame_idx]
        T1 = self.data['T1'][frame_idx]
        
        c2w1 = np.eye(4)
        c2w1[:3, :3] = R1
        c2w1[:3, 3] = T1
        
        camera_center1 = c2w1[:3, 3]
        camera_rotation1 = c2w1[:3, :3]
        
        q1 = tf.SO3.from_matrix(camera_rotation1).wxyz
        self.cam1_handle.wxyz = q1
        self.cam1_handle.position = camera_center1
        
        R2 = self.data['R2'][frame_idx]
        T2 = self.data['T2'][frame_idx]
        
        c2w2 = np.eye(4)
        c2w2[:3, :3] = R2
        c2w2[:3, 3] = T2
        
        camera_center2 = c2w2[:3, 3]
        camera_rotation2 = c2w2[:3, :3]
        
        q2 = tf.SO3.from_matrix(camera_rotation2).wxyz
        self.cam2_handle.wxyz = q2
        self.cam2_handle.position = camera_center2
    
    def animate(self):
        """Animation playback control."""
        with self.server.gui.add_folder("Playback"):
            gui_timestep = self.server.gui.add_slider(
                "Frame",
                min=0,
                max=self.num_frames - 1,
                step=1,
                initial_value=0,
                disabled=False,
            )
            gui_next_frame = self.server.gui.add_button("Next Frame", disabled=False)
            gui_prev_frame = self.server.gui.add_button("Prev Frame", disabled=False)
            gui_playing = self.server.gui.add_checkbox("Playing", False)
            gui_framerate = self.server.gui.add_slider(
                "FPS", min=1, max=60, step=1, initial_value=30
            )
        
        @gui_next_frame.on_click
        def _(_) -> None:
            gui_timestep.value = (gui_timestep.value + 1) % self.num_frames
        
        @gui_prev_frame.on_click
        def _(_) -> None:
            gui_timestep.value = (gui_timestep.value - 1) % self.num_frames
        
        @gui_playing.on_update
        def _(_) -> None:
            gui_timestep.disabled = gui_playing.value
            gui_next_frame.disabled = gui_playing.value
            gui_prev_frame.disabled = gui_playing.value
        
        @gui_timestep.on_update
        def _(_) -> None:
            self.update_frame(gui_timestep.value)
        
        while True:
            if gui_playing.value:
                gui_timestep.value = (gui_timestep.value + 1) % self.num_frames
            
            time.sleep(1.0 / gui_framerate.value)
    
    def run(self):
        """Run visualization."""
        print(f"Viser server running at http://localhost:8080")
        print(f"Total frames: {self.num_frames}")
        self.animate()


def main():
    parser = argparse.ArgumentParser(description="Visualize SMPL motion + scene mesh with viser")
    parser.add_argument('seq_path', type=str, help='Path to sequence folder (e.g., .../scene/seq0)')
    parser.add_argument('--port', type=int, default=8080, help='Viser server port (default: 8080)')
    parser.add_argument('--max_frames', type=int, default=-1, help='Maximum frames to visualize (default: -1, all frames)')
    parser.add_argument('--stride', type=int, default=1, help='Frame stride (default: 1, load every frame)')
    parser.add_argument('--hq', action='store_true', help='Enable high-quality rendering with multiple lights and shadows')
    args = parser.parse_args()
    
    seq_path = Path(args.seq_path)
    
    optim_params_path = seq_path / 'optim_params.npz'
    if not optim_params_path.exists():
        print(f"Error: {optim_params_path} not found!")
        return
    
    scene_path = seq_path.parent
    mesh_path = scene_path / 'mesh_raw.ply'
    if not mesh_path.exists():
        print(f"Error: {mesh_path} not found!")
        return
    
    print(f"Loading motion from: {optim_params_path}")
    print(f"Loading scene from: {mesh_path}")
    
    data = load_data(str(optim_params_path), str(mesh_path))
    
    print("Loading SMPL model...")
    body_model = load_smpl_model()
    
    viewer = MotionSceneViewer(data, body_model, port=args.port, max_frames=args.max_frames, stride=args.stride, high_quality=args.hq)
    
    viewer.run()


if __name__ == '__main__':
    main()
