seq_path=$1
view_name=$2
down_scale=$3
vertical=$4
if [ -z "$vertical" ]; then
    vertical=0
fi
vf="scale=iw/${down_scale}:ih/${down_scale}"
if [ "$vertical" = "1" ]; then
    vf="${vf},transpose=1"
fi
images_dir="${seq_path}/${view_name}/images"
mkdir -p "${images_dir}"

# Ensure deterministic outputs when rerunning Step 4 in overwrite mode.
rm -f "${images_dir}/${view_name}_"*.jpg

ffmpeg -y -i "${seq_path}/${view_name}/data.mov" -r 30 -vf "${vf}" -q:v 5 -start_number 0 "${images_dir}/${view_name}_%04d.jpg"
