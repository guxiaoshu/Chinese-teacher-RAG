"""下载向量模型 bge-base-zh-v1.5 到项目内 models/ 目录。

优先走魔搭 ModelScope（国内稳），失败再尝试 HuggingFace（需 .env 配 HF_ENDPOINT 镜像）。
下载完成后，config.yaml 里的 embedding.model_name 指向 models/bge-base-zh-v1.5（相对路径），
整包拷到别的电脑也无需重新下载。

用法：python scripts/download_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK 编码，强制 UTF-8 输出，避免中文乱码
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
TARGET = BASE_DIR / "models" / "bge-base-zh-v1.5"

MODELSCOPE_IDS = ["AI-ModelScope/bge-base-zh-v1.5", "BAAI/bge-base-zh-v1.5"]
HF_IDS = ["BAAI/bge-base-zh-v1.5"]


def _complete(target: Path) -> bool:
    return (target / "config.json").exists() and (
        (target / "pytorch_model.bin").exists() or (target / "model.safetensors").exists()
    )


def _download_modelscope() -> str | None:
    try:
        from modelscope import snapshot_download
    except ImportError:
        print("[!] 未安装 modelscope，请先执行：python -m pip install modelscope")
        return None
    for mid in MODELSCOPE_IDS:
        try:
            print(f"[*] 魔搭下载中：{mid} ...")
            return str(snapshot_download(mid, local_dir=str(TARGET)))
        except Exception as e:  # noqa: BLE001
            print(f"[-] {mid} 下载失败：{e}")
    return None


def _download_hf() -> str | None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return None
    for mid in HF_IDS:
        try:
            print(f"[*] HuggingFace 下载中：{mid} ...")
            return str(snapshot_download(mid, local_dir=str(TARGET)))
        except Exception as e:  # noqa: BLE001
            print(f"[-] {mid} 下载失败：{e}")
    return None


def main() -> int:
    if _complete(TARGET):
        print(f"[√] 模型已存在，跳过下载：{TARGET}")
        return 0
    TARGET.mkdir(parents=True, exist_ok=True)
    p = _download_modelscope() or _download_hf()
    if p is None:
        print("[×] 下载失败。请检查网络，或手动下载：")
        print("   1) 浏览器打开 modelscope.cn，搜「bge-base-zh-v1.5」")
        print(f"   2) 把整个模型文件夹解压到：{TARGET}")
        return 1
    print(f"[√] 下载完成：{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
