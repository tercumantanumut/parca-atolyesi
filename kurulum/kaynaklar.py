"""What the installer downloads: torch wheels, pinned code clones and model weights (in download order).

Weights are never redistributed by this project; they come straight from their publishers. Hugging Face files are
pinned to a commit and verified against the Hub listing of that commit (sha256 for LFS files, the git blob sha1 for
small files). The listing is cached next to the weights, so `dogrula` also works offline.
"""

# torch 2.11.0 + CUDA 12.8 runtime (RTX 50 / sm_120 support), per platform. Hashes as published in the
# download.pytorch.org/whl/cu128 index. The Linux pair is listed but the Linux install is untested.
TEKERLEKLER = [
    {
        "platform": "win32",
        "ad": "torch-2.11.0+cu128-cp312-cp312-win_amd64.whl",
        "url": "https://download.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl",
        "sha256": "7c78215c3af4f62e63f2b2e360f1722fc719b0853c7ac22666483d9810613a4c",
        "boyut": 2753189216,
    },
    {
        "platform": "win32",
        "ad": "torchvision-0.26.0+cu128-cp312-cp312-win_amd64.whl",
        "url": "https://download.pytorch.org/whl/cu128/torchvision-0.26.0%2Bcu128-cp312-cp312-win_amd64.whl",
        "sha256": "8c0d1c4fbb2c9a4d5d41d0aaa87da20e525bcb2a154ce405725b0be59456804b",
        "boyut": 9585013,
    },
    {
        "platform": "linux",
        "ad": "torch-2.11.0+cu128-cp312-cp312-manylinux_2_28_x86_64.whl",
        "url": "https://download.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-manylinux_2_28_x86_64.whl",
        "sha256": "d252cf975fb18c94a85336323ad425f473df56dab35a44b00399bd70c7a3b997",
        "boyut": 820326880,
    },
    {
        "platform": "linux",
        "ad": "torchvision-0.26.0+cu128-cp312-cp312-manylinux_2_28_x86_64.whl",
        "url": "https://download.pytorch.org/whl/cu128/torchvision-0.26.0%2Bcu128-cp312-cp312-manylinux_2_28_x86_64.whl",
        "sha256": "ccf26b4b659cfce6f2208cb8326071d51c70219a34856dfdf468d1e19af52c0d",
        "boyut": 8057226,
    },
]


def tekerlekler(platform: str) -> list[dict]:
    """The wheels for this platform (sys.platform: "win32" or "linux")."""
    return [t for t in TEKERLEKLER if t["platform"] == platform]

# Upstream code, cloned once and used read-only (monkeypatched at run time, never edited).
KODLAR = {
    "Hunyuan3D-2.1": ("https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1", "82920d643c0dc2f7bfd7255f45f62d386edfe60c"),
    "Hunyuan3D-Part": ("https://github.com/Tencent-Hunyuan/Hunyuan3D-Part", "e96be065375438962375b55326416291342958a7"),
    "Hunyuan3D-2": ("https://github.com/Tencent-Hunyuan/Hunyuan3D-2", "f8db63096c8282cb27354314d896feba5ba6ff8a"),
}

# Model groups. `model` = the id in GET /api/sistem -> modeller. Files are HF paths; a trailing "/" takes the folder.
# Order = download order: what the light route needs first, X-Part (9 GB, only for >= 40 GB cards) last.
GRUPLAR = [
    {
        "ad": "sekil", "model": "sekil", "zorunlu": True,
        "hf": [
            ("tencent/Hunyuan3D-2.1", "0b94677654c57bb9a6b6845cd7b704ccf551d327",
             ["LICENSE", "Notice.txt", "README.md", "hunyuan3d-dit-v2-1/", "hunyuan3d-vae-v2-1/"]),
        ],
        "dosya": [
            # u2net: background removal fallback (rembg); md5 is the one rembg itself pins.
            {"yol": "danielgatis__rembg/u2net.onnx", "boyut": 175997641,
             "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
             "md5": "60024c5c889badc19c04ad937298a77b"},
        ],
    },
    {
        "ad": "doku", "model": "doku", "zorunlu": True,
        "hf": [
            ("tencent/Hunyuan3D-2.1", "0b94677654c57bb9a6b6845cd7b704ccf551d327", ["hunyuan3d-paintpbr-v2-1/"]),
            ("facebook/dinov2-giant", "611a9d42f2335e0f921f1e313ad3c1b7178d206d",
             ["config.json", "preprocessor_config.json", "model.safetensors", "README.md"]),
        ],
        "dosya": [
            {"yol": "xinntao__Real-ESRGAN/RealESRGAN_x4plus.pth", "boyut": 67040989,
             "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
             "sha256": "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"},
        ],
    },
    {
        "ad": "parcalar", "model": "parcalar", "zorunlu": True,
        "hf": [
            ("tencent/Hunyuan3D-Part", "677174466c53571e8bacd5050dff5948734a1a4d",
             ["LICENSE.txt", "NOTICE.txt", "README.md", "config.json", "p3sam/"]),
            ("facebook/sonata", "df99897472c09f91ba9288da0a034aacffc0b010", ["sonata.pth", "config.json", "README.md"]),
        ],
        "dosya": [],
    },
    {
        "ad": "2mv", "model": "2mv", "zorunlu": False,
        "hf": [
            ("tencent/Hunyuan3D-2mv", "3a761b539b29fe4ff64714813aa9560fd66f5de0",
             ["LICENSE", "NOTICE", "README.md", "config.json",
              "hunyuan3d-dit-v2-mv/config.yaml", "hunyuan3d-dit-v2-mv/model.fp16.safetensors"]),
        ],
        "dosya": [],
    },
    {
        "ad": "xpart", "model": "xpart", "zorunlu": False,
        "hf": [
            ("tencent/Hunyuan3D-Part", "677174466c53571e8bacd5050dff5948734a1a4d",
             ["conditioner/", "model/", "shapevae/", "scheduler/"]),
        ],
        "dosya": [],
    },
]


def klasor(repo: str) -> str:
    """Local folder name of a HF repo inside the models folder."""
    return repo.replace("/", "__")
