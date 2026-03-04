## Colmap questions

### install

[https://github.com/colmap/colmap/issues/2464](https://github.com/colmap/colmap/issues/2464)

### No CMAKE_CUDA_COMPILER could be found

[https://github.com/jetsonhacks/buildLibrealsense2TX/issues/13](https://github.com/jetsonhacks/buildLibrealsense2TX/issues/13)

### FAILED: src/colmap/mvs/CMakeFiles/xxx

[https://github.com/colmap/colmap/issues/2091](https://github.com/colmap/colmap/issues/2091)

### libcudart.so error

[https://github.com/vllm-project/vllm/issues/1369](https://github.com/vllm-project/vllm/issues/1369)

E.g. `export LD_LIBRARY_PATH=/home/wwj/miniconda3/envs/droidenv/lib/:$LD_LIBRARY_PATH`

### For colmap registration problems, see this in detail:

[https://colmap.github.io/faq.html#register-localize-new-images-into-an-existing-reconstruction](https://colmap.github.io/faq.html#register-localize-new-images-into-an-existing-reconstruction)

## Numpy

If you meets this problem:

`ImportError: cannot import name 'bool' from 'numpy'`

use this:

`pip install git+https://github.com/mattloper/chumpy`

if you meet this: `floating point exception`

You can  `pip install numpy==1.26.4`

```bash
pip install --force-reinstall charset-normalizer==3.1.0
```



```
ValueError: numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject.
```

```ini
numpy==1.26.4
```


## Isaac Gym

export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/envs/gym/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
export LD_LIBRARY_PATH=/home/wenjiawang/miniconda3/pkgs/python-3.8.20-he870216_0/lib/libpython3.8.so.1.0:/usr/lib/x86_64-linux-gnu
