export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
scene_path=$1
if [ -z "$scene_path" ]; then
    echo "Error: scene_path is required"
    exit 1
fi

if [ ! -d "$scene_path/colmap/sparse/0" ]; then
    echo "Error: missing sparse model at $scene_path/colmap/sparse/0"
    exit 1
fi

if [ ! -d "$scene_path/images" ]; then
    echo "Error: missing scene images dir at $scene_path/images"
    exit 1
fi

if [ -d "$scene_path/colmap/images" ]; then
    rm -r "$scene_path/colmap/images"
fi
if [ -d "$scene_path/colmap/dense" ]; then
    rm -r "$scene_path/colmap/dense"
fi
if [ -f "$scene_path/colmap/database.db" ]; then
    rm "$scene_path/colmap/database.db"
fi

mkdir -p "$scene_path/colmap/images"
mkdir -p "$scene_path/colmap/dense"

tmp_txt_dir=$(mktemp -d)
trap 'rm -rf "$tmp_txt_dir"' EXIT

# Export sparse model to TXT and preserve image order by image_id.
colmap model_converter \
    --input_path "$scene_path/colmap/sparse/0" \
    --output_path "$tmp_txt_dir" \
    --output_type TXT

python - "$tmp_txt_dir/images.txt" "$scene_path/colmap/image-list.txt" <<'PY'
import sys
from pathlib import Path

images_txt = sys.argv[1]
out_list = sys.argv[2]

ordered = []
with open(images_txt, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            image_id = int(parts[0])
            int(parts[8])
        except ValueError:
            continue
        image_name = parts[9]
        # images.txt alternates with a 2D-points line; only keep true header lines.
        suffix = Path(image_name).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png"}:
            continue
        ordered.append((image_id, image_name))

ordered.sort(key=lambda x: x[0])
seen = set()
final_names = []
for _, name in ordered:
    if name in seen:
        continue
    seen.add(name)
    final_names.append(name)

with open(out_list, "w", encoding="utf-8") as f:
    for name in final_names:
        f.write(name + "\n")

print(f"Prepared image-list with {len(final_names)} entries")
PY

if [ ! -s "$scene_path/colmap/image-list.txt" ]; then
    echo "Error: generated image-list is empty: $scene_path/colmap/image-list.txt"
    exit 1
fi

missing=0
while IFS= read -r image_name; do
    [ -z "$image_name" ] && continue
    src="$scene_path/images/$image_name"
    dst="$scene_path/colmap/images/$image_name"
    if [ ! -f "$src" ]; then
        echo "Error: sparse model references missing scene image: $src"
        missing=1
        continue
    fi
    cp "$src" "$dst"
done < "$scene_path/colmap/image-list.txt"

if [ "$missing" -ne 0 ]; then
    echo "Error: one or more sparse model images are missing in scene/images"
    exit 1
fi

colmap feature_extractor \
     --database_path "$scene_path/colmap/database.db" \
     --image_path "$scene_path/colmap/images" \
     --image_list_path "$scene_path/colmap/image-list.txt" \
     --SiftExtraction.use_gpu 0

 colmap exhaustive_matcher \
     --database_path "$scene_path/colmap/database.db" \
     --SiftMatching.use_gpu 0
 
 colmap point_triangulator \
     --database_path "$scene_path/colmap/database.db" \
     --image_path "$scene_path/colmap/images" \
     --input_path "$scene_path/colmap/sparse/0" \
     --output_path "$scene_path/colmap/sparse/0" \
     --clear_points 1

## added by claude
 colmap bundle_adjuster \
     --input_path "$scene_path/colmap/sparse/0" \
     --output_path "$scene_path/colmap/sparse/0" \
     --BundleAdjustment.refine_extrinsics 0
 
#  colmap image_undistorter \
#      --image_path $scene_path/colmap/images \
#      --input_path $scene_path/colmap/sparse/0 \
#      --output_path $scene_path/colmap/dense
 
#  colmap patch_match_stereo \
#      --workspace_path $scene_path/colmap/dense
 
#  colmap stereo_fusion \
#      --workspace_path $scene_path/colmap/dense\
#      --output_path $scene_path/colmap/dense/fused.ply