set -euo pipefail

export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
scene_path=${1:-}
view_path=${2:-}
focal=${3:-}
cx=${4:-}
cy=${5:-}
vocab_tree_path=${6:-}

if [ -z "$scene_path" ] || [ -z "$view_path" ]; then
    echo "Error: missing required args"
    echo "Usage: $0 <scene_path> <view_path> <focal> <cx> <cy> <vocab_tree_path>"
    exit 1
fi

if [ ! -d "$scene_path/colmap/sparse/0" ]; then
    echo "Error: missing sparse model: $scene_path/colmap/sparse/0"
    exit 1
fi

if [ ! -f "$scene_path/colmap/database.db" ]; then
    echo "Error: missing scene colmap database: $scene_path/colmap/database.db"
    exit 1
fi

rm -rf "$view_path/colmap"
mkdir -p "$view_path/colmap"

cp "$scene_path/colmap/database.db" "$view_path/colmap/database.db"

colmap feature_extractor \
         --database_path "$view_path/colmap/database.db" \
         --image_path "$view_path/images" \
         --image_list_path "$view_path/image-list.txt" \
         --ImageReader.single_camera 1 \
         --ImageReader.camera_model SIMPLE_PINHOLE \
         --ImageReader.camera_params "${focal},${cx},${cy}"
 

#  colmap exhaustive_matcher --database_path $view_path/colmap/database.db
 colmap sequential_matcher \
     --database_path "$view_path/colmap/database.db" \
     --SequentialMatching.overlap 10 \
     --SequentialMatching.loop_detection 0

 colmap vocab_tree_matcher \
     --database_path "$view_path/colmap/database.db" \
     --VocabTreeMatching.vocab_tree_path "$vocab_tree_path" \
     --VocabTreeMatching.match_list_path "$view_path/image-list.txt"

#  colmap vocab_tree_matcher \
#      --database_path $view_path/colmap/database.db \
#      --VocabTreeMatching.vocab_tree_path home/ubuntu/programs/colmap/vocab_tree_faiss_flickr100K_words32K.bin \
#      --VocabTreeMatching.match_list_path $view_path/image-list.txt

# Remap scene sparse image IDs to the copied database image IDs by image name.
# This avoids COLMAP crashes when scene database and sparse model ids drift.
input_model_txt="$view_path/colmap/input_model_txt"
input_model_bin="$view_path/colmap/input_model_bin"
mkdir -p "$input_model_txt" "$input_model_bin"

colmap model_converter \
    --input_path "$scene_path/colmap/sparse/0" \
    --output_path "$input_model_txt" \
    --output_type TXT

python - "$view_path/colmap/database.db" "$input_model_txt/images.txt" "$input_model_txt/points3D.txt" <<'PY'
import sqlite3
import sys

db_path, images_txt, points3d_txt = sys.argv[1:4]

conn = sqlite3.connect(db_path)
name_to_dbid = {name: int(iid) for iid, name in conn.execute("select image_id, name from images")}
conn.close()

old_to_new = {}
new_lines = []

with open(images_txt, "r", encoding="utf-8") as f:
    lines = f.readlines()

i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        new_lines.append(line)
        i += 1
        continue

    parts = stripped.split()
    if len(parts) < 10:
        new_lines.append(line)
        i += 1
        continue

    try:
        old_id = int(parts[0])
        int(parts[8])
    except ValueError:
        # Not a valid image header line; keep as-is.
        new_lines.append(line)
        i += 1
        continue

    image_name = parts[9]
    if image_name not in name_to_dbid:
        raise RuntimeError(
            f"Sparse model image '{image_name}' not found in database images table"
        )

    new_id = name_to_dbid[image_name]
    old_to_new[old_id] = int(new_id)
    parts[0] = str(int(new_id))
    new_lines.append(" ".join(parts) + "\n")

    i += 1
    if i < len(lines):
        # Keep POINTS2D line unchanged.
        new_lines.append(lines[i])
        i += 1

with open(images_txt, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

if old_to_new and points3d_txt:
    rewritten = []
    with open(points3d_txt, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                rewritten.append(raw)
                continue
            parts = line.split()
            if len(parts) <= 8:
                rewritten.append(raw)
                continue

            track = parts[8:]
            for t in range(0, len(track), 2):
                if t >= len(track):
                    break
                try:
                    old_image_id = int(track[t])
                except ValueError:
                    continue
                if old_image_id in old_to_new:
                    track[t] = str(old_to_new[old_image_id])

            rewritten.append(" ".join(parts[:8] + track) + "\n")

    with open(points3d_txt, "w", encoding="utf-8") as f:
        f.writelines(rewritten)

print(f"Remapped sparse model image IDs: {len(old_to_new)}")
PY

colmap model_converter \
    --input_path "$input_model_txt" \
    --output_path "$input_model_bin" \
    --output_type BIN

colmap image_registrator \
    --database_path "$view_path/colmap/database.db" \
    --input_path "$input_model_bin" \
    --output_path "$view_path/colmap"

#  colmap bundle_adjuster \
#      --input_path $view_path/colmap/ \
#      --output_path $view_path/colmap/\
#      --BundleAdjustment.max_num_iterations 100 \
#      --BundleAdjustment.function_tolerance 1e-9
     
 colmap model_converter \
     --input_path "$view_path/colmap" \
     --output_path "$view_path/colmap" \
     --output_type TXT
