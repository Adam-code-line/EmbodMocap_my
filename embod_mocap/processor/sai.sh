#!/usr/bin/env bash

SCENE_PATH="$1"
KEY_FRAME_DISTANCE="${2:-0.05}"

if [ -z "$SCENE_PATH" ]; then
	echo "[ERROR] scene path is required"
	return 2 2>/dev/null || exit 2
fi

echo "[Step1] SAI default mode: $SCENE_PATH (kfd=$KEY_FRAME_DISTANCE)"
sai-cli process "$SCENE_PATH" "$SCENE_PATH" --key_frame_distance "$KEY_FRAME_DISTANCE"
DEFAULT_EXIT=$?

if [ "$DEFAULT_EXIT" -eq 0 ]; then
	echo "[Step1] SAI default mode succeeded"
	return 0 2>/dev/null || exit 0
fi

echo "[WARN] SAI default mode failed with exit=$DEFAULT_EXIT"
echo "[Step1] Retrying with --mono fallback"
sai-cli process "$SCENE_PATH" "$SCENE_PATH" --mono --key_frame_distance "$KEY_FRAME_DISTANCE"
MONO_EXIT=$?

if [ "$MONO_EXIT" -eq 0 ]; then
	echo "[Step1] SAI mono fallback succeeded"
	return 0 2>/dev/null || exit 0
fi

echo "[ERROR] SAI failed in both default and mono modes (default=$DEFAULT_EXIT, mono=$MONO_EXIT)"
echo "[HINT] If logs contain 'Invalid value ... for dtype int64', pin pandas in this env:"
echo "       python -m pip install --upgrade 'pandas<2.2'"

return "$MONO_EXIT" 2>/dev/null || exit "$MONO_EXIT"