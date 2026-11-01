"""Measured VRAM needs per model: the peak working set of its step, weights included (GiB, torch allocated, RTX 5090,
see docs/MOTOR.md "Ölçümler"). Used for the X-Part warning and to decide which kept models to unload first."""

IHTIYAC_GB = {
    "sekil_21": 7.6,    # Hunyuan3D-2.1 shape, octree 384
    "sekil_2mv": 9.5,   # Hunyuan3D-2mv shape (front + back)
    "doku": 13.5,       # Hunyuan3D-2.1 paint, 6 views x 512
    "p3sam": 12.3,      # P3-SAM, prompt_bs 8
    "xpart": 35.4,      # X-Part, octree 384 (maceraci, 12 parts); spills into shared memory on a 32 GB card
}
PAY_GB = 0.6           # margin for the CUDA context and fragmentation
