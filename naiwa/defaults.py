"""出厂默认值。

CI 会用 workflow_dispatch 的 ``model_url`` 输入改写这里的 ``DEFAULT_MODEL_URL``，
这样打出来的 APK 首次启动就知道去哪儿下模型。留空则表示不预置，用户自己在设置里填。
"""

from __future__ import annotations

# 本地模型
MODEL_FILENAME = "Qwen3.5-2B-Q4_K_M.gguf"
# 约 1.19 GB，用于校验下载是否完整（按需改）
MODEL_SIZE_HINT = 1_280_835_840
# 直链。建议放国内对象存储或你自己的 GitHub Release（单个 Release 资源上限 2 GB）。
DEFAULT_MODEL_URL = ""
# 可选：填了就在下载完成后校验 SHA256，留空跳过
MODEL_SHA256 = ""

# 推理参数
DEFAULT_N_CTX = 2048
DEFAULT_N_THREADS = 4
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 512

# 云模型默认用哪家；见 naiwa/llm/remote.py 的 PROVIDER_PRESETS
DEFAULT_REMOTE_PROVIDER = "zhipu"
