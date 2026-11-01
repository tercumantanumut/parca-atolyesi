r"""Builds the two native pieces Hunyuan3D-2.1 texturing needs, from the (untouched) clone sources into
<veri>/derleme. Started by `kur.py ortam` inside an MSVC x64 environment (vcvars64) with CUDA_HOME and
TORCH_CUDA_ARCH_LIST set; by hand:

  <venv>/python -I kurulum/eklenti_derle.py build_ext --build-lib <veri>/derleme --build-temp <veri>/derleme/tmp

- custom_rasterizer_kernel: CUDA extension, from hy3dpaint/custom_rasterizer/lib/custom_rasterizer_kernel_for_windows
  (the official Windows variant; on Linux the plain lib/custom_rasterizer_kernel). TORCH_CUDA_ARCH_LIST decides the GPU
  targets: an RTX 50 card with a CUDA toolkit older than 12.8 gets compute_90 PTX, which the driver JIT-compiles.
- mesh_inpaint_processor: plain C++/pybind11 module (CPU), replaces the clone's Linux-only compile_mesh_painter.sh.

Two source patches are applied to copies (the clone stays untouched):
1. rasterizer.h: under nvcc, <torch/types.h> instead of <torch/extension.h>. On Windows <torch/extension.h> pulls in
   torch/csrc/dynamo/compiled_autograd.h, which nvcc 12.x + MSVC rejects ("error C2872: 'std': ambiguous symbol").
2. rasterizer_gpu.cu: the z-buffer is a kInt64 tensor; torch >= 2.3 refuses data_ptr<uint64_t>() on it ("expected
   scalar type UInt64 but found Long"). Same bits, so read it as int64 and reinterpret.
"""
import os
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

import pybind11  # noqa: E402
from setuptools import Extension, setup  # noqa: E402
from torch.utils.cpp_extension import BuildExtension, CUDAExtension  # noqa: E402

from atolye.ayar import yukle  # noqa: E402

A = yukle()
PAINT = A.kod / "Hunyuan3D-2.1" / "hy3dpaint"
WINDOWS = os.name == "nt"
KSRC = PAINT / "custom_rasterizer" / "lib" / ("custom_rasterizer_kernel_for_windows" if WINDOWS else "custom_rasterizer_kernel")
BUILD = A.derleme

BUILD.mkdir(parents=True, exist_ok=True)
# The pure-Python wrapper package of the rasterizer sits next to the compiled kernel.
shutil.copytree(PAINT / "custom_rasterizer" / "custom_rasterizer", BUILD / "custom_rasterizer", dirs_exist_ok=True)

SRC = BUILD / "src" / "custom_rasterizer_kernel"
shutil.copytree(KSRC, SRC, dirs_exist_ok=True)
header = (SRC / "rasterizer.h").read_text()
if "__CUDACC__" not in header.split("#include <vector>")[0]:
    header = header.replace(
        "#include <torch/extension.h>",
        "#ifdef __CUDACC__\n#include <torch/types.h>\n#else\n#include <torch/extension.h>\n#endif",
        1,
    )
    (SRC / "rasterizer.h").write_text(header)
cu = (SRC / "rasterizer_gpu.cu").read_text()
cu = cu.replace("(uint64_t*)z_min.data_ptr<uint64_t>()", "reinterpret_cast<uint64_t*>(z_min.data_ptr<int64_t>())")
(SRC / "rasterizer_gpu.cu").write_text(cu)


def rel(p: Path) -> str:
    # setuptools wants paths relative to the working directory when it can get them
    return str(p.relative_to(Path.cwd())) if p.is_relative_to(Path.cwd()) else str(p)


cxx = ["/O2", "/std:c++17", "/EHsc"] if WINDOWS else ["-O3", "-std=c++17"]
setup(
    name="atolye_native",
    version="0.1",
    ext_modules=[
        CUDAExtension(
            "custom_rasterizer_kernel",
            [rel(SRC / "rasterizer.cpp"), rel(SRC / "grid_neighbor.cpp"), rel(SRC / "rasterizer_gpu.cu")],
            extra_compile_args={"cxx": cxx[:1], "nvcc": ["-O3"]},
        ),
        Extension(
            "mesh_inpaint_processor",
            [rel(PAINT / "DifferentiableRenderer" / "mesh_inpaint_processor.cpp")],
            include_dirs=[pybind11.get_include()],
            language="c++",
            extra_compile_args=cxx,
        ),
    ],
    cmdclass={"build_ext": BuildExtension},
)
