==== Step 10, Process depth & mask for ../datasets/my_capture/scene_0014 seq0 ====
/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/xformers/ops/fmha/flash.py:211: FutureWarning: `torch.library.impl_abstract` was renamed to `torch.library.register_fake`. Please use that instead; we will remove `torch.library.impl_abstract` in a future version of PyTorch.
  @torch.library.impl_abstract("xformers_flash::flash_fwd")
/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/xformers/ops/fmha/flash.py:344: FutureWarning: `torch.library.impl_abstract` was renamed to `torch.library.register_fake`. Please use that instead; we will remove `torch.library.impl_abstract` in a future version of PyTorch.
  @torch.library.impl_abstract("xformers_flash::flash_bwd")
/home/wubin/third_src/mmcv-1.7.2/mmcv/__init__.py:20: UserWarning: On January 1, 2023, MMCV will release v2.0.0, in which it will remove components related to the training process and add a data transformation module. In addition, it will rename the package names mmcv to mmcv-lite and mmcv-full to mmcv. See https://github.com/open-mmlab/mmcv/blob/master/docs/en/compatibility.md for more details.
  warnings.warn(
apex is not installed
apex is not installed
apex is not installed
/home/wubin/third_src/mmcv-1.7.2/mmcv/cnn/bricks/transformer.py:33: UserWarning: Fail to import ``MultiScaleDeformableAttention`` from ``mmcv.ops.multi_scale_deform_attn``, You should install ``mmcv-full`` if you need this module.
  warnings.warn('Fail to import ``MultiScaleDeformableAttention`` from '
Processing keyframes only: v1=53, v2=54
Processing v1 depth refine (53 keyframes)
Processing v1 depths with depth refine:   0%|                                                                                                                                           | 0/7 [00:00<?, ?it/s]/home/wubin/EmbodMocap_dev/embod_mocap/processor/process_frames.py:363: FutureWarning: `torch.cuda.amp.autocast(args...)` is deprecated. Please use `torch.amp.autocast('cuda', args...)` instead.
  with torch.cuda.amp.autocast():
/home/wubin/EmbodMocap_dev/embod_mocap/processor/process_frames.py:375: RuntimeWarning: invalid value encountered in cast
  depth = np.clip(depth, 0, 65535).astype(np.uint16)
Processing v1 depths with depth refine: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 7/7 [00:46<00:00,  6.65s/it]
Processing v2 depth refine (54 keyframes)
Processing v2 depths with depth refine: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 7/7 [00:47<00:00,  6.75s/it]
Generating masks for keyframes only: v1=53, v2=54
Attempting to load processor from local path: /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base
Attempting to load model from local path: /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base
/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/utils/cpp_extension.py:1965: UserWarning: TORCH_CUDA_ARCH_LIST is not set, all archs for visible cards are included for compilation.
If this is not desired, please set os.environ['TORCH_CUDA_ARCH_LIST'].
  warnings.warn(
Could not load the custom kernel for multi-scale deformable attention: Error building extension 'MultiScaleDeformableAttention': [1/3] /home/wubin/miniconda3/envs/embodmocap/bin/nvcc --generate-dependencies-with-compile --dependency-output ms_deform_attn_cuda.cuda.o.d -DTORCH_EXTENSION_NAME=MultiScaleDeformableAttention -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/TH -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/THC -isystem /home/wubin/miniconda3/envs/embodmocap/include -isystem /home/wubin/miniconda3/envs/embodmocap/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_89,code=compute_89 -gencode=arch=compute_89,code=sm_89 --compiler-options '-fPIC' -DCUDA_HAS_FP16=1 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ -std=c++17 -c /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cuda/ms_deform_attn_cuda.cu -o ms_deform_attn_cuda.cuda.o
FAILED: [code=1] ms_deform_attn_cuda.cuda.o
/home/wubin/miniconda3/envs/embodmocap/bin/nvcc --generate-dependencies-with-compile --dependency-output ms_deform_attn_cuda.cuda.o.d -DTORCH_EXTENSION_NAME=MultiScaleDeformableAttention -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/TH -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/THC -isystem /home/wubin/miniconda3/envs/embodmocap/include -isystem /home/wubin/miniconda3/envs/embodmocap/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_89,code=compute_89 -gencode=arch=compute_89,code=sm_89 --compiler-options '-fPIC' -DCUDA_HAS_FP16=1 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ -std=c++17 -c /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cuda/ms_deform_attn_cuda.cu -o ms_deform_attn_cuda.cuda.o
In file included from /home/wubin/miniconda3/envs/embodmocap/include/cuda_bf16.h:3974,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/c10/util/BFloat16.h:14,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/c10/core/ScalarType.h:3,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/c10/core/TensorImpl.h:11,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/c10/core/GeneratorImpl.h:8,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/core/Generator.h:18,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/CPUGeneratorImpl.h:3,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/Context.h:4,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/ATen.h:7,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cuda/ms_deform_im2col_cuda.cuh:16,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cuda/ms_deform_attn_cuda.cu:12:
/home/wubin/miniconda3/envs/embodmocap/include/cuda_bf16.hpp:80:10: fatal error: nv/target: No such file or directory
   80 | #include <nv/target>
      |          ^~~~~~~~~~~
compilation terminated.
[2/3] c++ -MMD -MF ms_deform_attn_cpu.o.d -DTORCH_EXTENSION_NAME=MultiScaleDeformableAttention -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/TH -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/THC -isystem /home/wubin/miniconda3/envs/embodmocap/include -isystem /home/wubin/miniconda3/envs/embodmocap/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -fPIC -std=c++17 -DWITH_CUDA=1 -c /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cpu/ms_deform_attn_cpu.cpp -o ms_deform_attn_cpu.o
FAILED: [code=1] ms_deform_attn_cpu.o
c++ -MMD -MF ms_deform_attn_cpu.o.d -DTORCH_EXTENSION_NAME=MultiScaleDeformableAttention -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/TH -isystem /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/THC -isystem /home/wubin/miniconda3/envs/embodmocap/include -isystem /home/wubin/miniconda3/envs/embodmocap/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -fPIC -std=c++17 -DWITH_CUDA=1 -c /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cpu/ms_deform_attn_cpu.cpp -o ms_deform_attn_cpu.o
In file included from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/cuda/CUDAContext.h:3,
                 from /home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/transformers/kernels/deformable_detr/cpu/ms_deform_attn_cpu.cpp:14:
/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torch/include/ATen/cuda/CUDAContextLight.h:7:10: fatal error: cusparse.h: No such file or directory
    7 | #include <cusparse.h>
      |          ^~~~~~~~~~~~
compilation terminated.
ninja: build stopped: subcommand failed.

Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Segmenting images...
  0%|                                                                                                                                                                                   | 0/6 [00:00<?, ?it/s]/home/wubin/miniconda3/envs/embodmocap/lib/python3.11/site-packages/torchvision/transforms/functional.py:154: UserWarning: The given NumPy array is not writable, and PyTorch does not support non-writable tensors. This means writing to this tensor will result in undefined behavior. You may want to copy the array to protect its data or make it writable before converting it to a tensor. This type of warning will be suppressed for the rest of this program. (Triggered internally at ../torch/csrc/utils/tensor_numpy.cpp:206.)
  img = torch.from_numpy(pic.transpose((2, 0, 1))).contiguous()
100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 6/6 [00:05<00:00,  1.07it/s]
[ WARN:0@112.298] global loadsave.cpp:1089 imwrite_ Unsupported depth image for selected encoder is fallbacked to CV_8U.
Attempting to load processor from local path: /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base
Attempting to load model from local path: /home/wubin/EmbodMocap_dev/checkpoints/grounding_dino_base
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Could not load the custom kernel for multi-scale deformable attention: /home/wubin/.cache/torch_extensions/py311_cu121/MultiScaleDeformableAttention/MultiScaleDeformableAttention.so: cannot open shared object file: No such file or directory
Segmenting images...
100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 6/6 [00:05<00:00,  1.15it/s]
Filtering v1 points2D with keyframe masks
Filtering v2 points2D with keyframe masks
process_depth_mask done.
