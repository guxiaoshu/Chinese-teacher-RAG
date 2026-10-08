"""文生图接入层：SiliconFlow（一个 key 聚合 FLUX / Kolors 等图模型）。

配置（.env）：
  SILICONFLOW_API_KEY=sk-...
  SILICONFLOW_MODEL=Kwai-Kolors/Kolors        # 可选，默认
  SILICONFLOW_IMAGE_SIZE=1024x576             # 可选，16:9
  SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1/images/generations  # 可选

无 key 时 from_env() 返回 None，deck 回退到纯矢量装饰。
"""
from __future__ import annotations

import base64
import os

import requests

_DEFAULT_BASE = "https://api.siliconflow.cn/v1/images/generations"
_DEFAULT_MODEL = "Kwai-Kolors/Kolors"
_DEFAULT_SIZE = "1024x576"


class ImageProvider:
    """生成一张图，返回图片字节（失败返回 None）。"""

    def generate(self, prompt: str, size: str | None = None) -> bytes | None:
        raise NotImplementedError


class SiliconFlowProvider(ImageProvider):
    def __init__(self, api_key: str, model: str | None = None, size: str | None = None,
                 base_url: str | None = None, timeout: int = 120):
        self.api_key = api_key
        self.model = model or os.getenv("SILICONFLOW_MODEL", _DEFAULT_MODEL)
        self.size = size or os.getenv("SILICONFLOW_IMAGE_SIZE", _DEFAULT_SIZE)
        self.base_url = base_url or os.getenv("SILICONFLOW_BASE_URL", _DEFAULT_BASE)
        self.timeout = timeout

    def generate(self, prompt: str, size: str | None = None) -> bytes | None:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "image_size": size or self.size,
            "batch_size": 1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        r = requests.post(self.base_url, json=payload, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        images = data.get("images") or data.get("data") or []
        if not images:
            return None
        img = images[0]
        b64 = img.get("b64_json")
        if b64:
            return base64.b64decode(b64)
        url = img.get("url")
        if url:
            r2 = requests.get(url, timeout=self.timeout)
            r2.raise_for_status()
            return r2.content
        return None


def from_env() -> ImageProvider | None:
    key = os.getenv("SILICONFLOW_API_KEY", "").strip()
    if not key or key.startswith("你的"):
        return None
    return SiliconFlowProvider(key)
