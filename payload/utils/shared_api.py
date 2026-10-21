# SPDX-License-Identifier: AGPL-3.0-only
"""Resolve the user's existing translation API without exposing its credential."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
import urllib.error
import urllib.parse
import urllib.request

import toml

_WRITE_LOCK = threading.RLock()
# These are the same OpenAI-compatible endpoints used by pdf2zh_next 2.9.0.
PROVIDERS = {
    "openaicompatible": ("OpenAI 兼容 API", "openai_compatible", ""),
    "openai": ("OpenAI", "openai", "https://api.openai.com/v1"),
    "deepseek": ("DeepSeek", "deepseek", "https://api.deepseek.com/v1"),
    "gemini": ("Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "siliconflow": ("SiliconFlow API", "siliconflow", "https://api.siliconflow.cn/v1"),
    "modelscope": ("ModelScope API", "modelscope", "https://api-inference.modelscope.cn/v1"),
    "zhipu": ("智谱", "zhipu", "https://open.bigmodel.cn/api/paas/v4"),
    "grok": ("Grok", "grok", "https://api.x.ai/v1"),
    "groq": ("Groq", "groq", "https://api.groq.com/openai/v1"),
}


def clean(value):
    result = str(value or "").strip()
    return "" if result.lower() in {"null", "none"} else result


def checked_endpoint(value):
    value = clean(value).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})):
        raise ValueError("请输入 HTTPS API 地址，本机测试接口也可使用 HTTP")
    return value[:-len('/chat/completions')] if value.endswith('/chat/completions') else value


@dataclass(frozen=True)
class APIProfile:
    provider: str
    label: str
    model: str
    endpoint: str
    key: str = field(repr=False)
    timeout: int = 180

    def public(self):
        return {"id": self.provider, "label": self.label, "model": self.model,
                "endpoint": self.endpoint, "configured": True, "source": "translation"}


def profiles(config_folder):
    path = Path(config_folder) / "config.toml"
    if not path.exists():
        return [], None
    with _WRITE_LOCK:
        data = toml.load(path)
    found = []
    for provider, (label, prefix, default) in PROVIDERS.items():
        values = data.get(provider + "_detail", {})
        key = clean(values.get(prefix + "_api_key"))
        model = clean(values.get(prefix + "_model"))
        endpoint = clean(values.get(prefix + "_base_url")) or default
        if key and model and endpoint:
            try:
                endpoint = checked_endpoint(endpoint)
            except ValueError:
                continue
            try:
                timeout = min(600, max(30, int(values.get(prefix + "_timeout", 180))))
            except (TypeError, ValueError):
                timeout = 180
            found.append(APIProfile(provider, label, model, endpoint, key, timeout))
    active = next((profile.provider for profile in found if data.get(profile.provider) is True), None)
    return found, active or (found[0].provider if found else None)


def resolve(config_folder, provider=None):
    found, active = profiles(config_folder)
    selected = next((profile for profile in found if profile.provider == (provider or active)), None)
    if selected is None:
        raise ValueError("深度阅读需要你自己的 API。请先配置翻译 API，免费翻译服务不能直接用于深度阅读")
    return selected


def save_compatible(config_folder, endpoint, model, key=None):
    """Save to the existing translation table; there is no second credential store."""
    endpoint = checked_endpoint(endpoint)
    model = clean(model)
    if not model or len(model) > 200:
        raise ValueError("请输入有效模型名称")
    path = Path(config_folder) / "config.toml"
    with _WRITE_LOCK:
        data = toml.load(path) if path.exists() else {}
        table = data.setdefault("openaicompatible_detail", {})
        key = clean(key) or clean(table.get("openai_compatible_api_key"))
        if not key or "\n" in key or "\r" in key:
            raise ValueError("请输入自己的 API 密钥")
        table.update(translate_engine_type="OpenAICompatible", support_llm="yes",
                     openai_compatible_base_url=endpoint, openai_compatible_model=model,
                     openai_compatible_api_key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # toml is the upstream format, so preserve all other translation tables.
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as handle:
            handle.write(toml.dumps(data))
            temp = handle.name
        os.replace(temp, path)
    return resolve(config_folder, "openaicompatible")


def sync_translation_profile(config_folder, data):
    provider = {"openailiked": "openaicompatible", "openai-compatible": "openaicompatible"}.get(data.get('service'), data.get('service'))
    if provider not in PROVIDERS:
        raise ValueError('这个翻译服务暂不支持结构化阅读，请使用已配置的 OpenAI 兼容 API')
    label, prefix, default = PROVIDERS[provider]
    model, key = clean(data.get('model')), clean(data.get('apiKey'))
    endpoint = clean(data.get('apiUrl')) or default
    if not model or not key or '\n' in key or '\r' in key:
        raise ValueError('翻译 API 需要完整的模型名称和密钥')
    endpoint = checked_endpoint(endpoint)
    path = Path(config_folder) / 'config.toml'
    import os
    import tempfile
    with _WRITE_LOCK:
        values = toml.load(path) if path.exists() else {}
        table = values.setdefault(provider + '_detail', {})
        table['support_llm'] = 'yes'
        table.update({prefix + '_model': model, prefix + '_api_key': key})
        # Keep provider-specific schemas identical to upstream. Providers with
        # fixed endpoints have no base_url field in their pydantic settings.
        if provider in {'openaicompatible', 'openai', 'siliconflow'}:
            table[prefix + '_base_url'] = endpoint
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, encoding='utf-8', delete=False) as handle:
            handle.write(toml.dumps(values))
            temporary = handle.name
        os.replace(temporary, path)
    return resolve(config_folder, provider)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API 返回重定向，请填写最终的 API 地址")


def chat(profile, messages, max_tokens):
    endpoint = profile.endpoint
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    payload = json.dumps({"model": profile.model, "messages": messages,
                          "max_tokens": max_tokens, "stream": False}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method="POST", headers={
        "Authorization": "Bearer " + profile.key, "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "zotero-pdf2zh-body-only",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=profile.timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        # Provider errors sometimes echo credentials or request content.
        raise ValueError(f"API 请求失败，HTTP {error.code}。请检查接口、模型权限和额度") from None
    except urllib.error.URLError:
        raise ValueError("无法连接 API，请检查网络与接口地址") from None
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("API 未返回阅读内容")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("API 返回了空内容，请确认模型支持文本阅读")
    usage = data.get("usage") or {}
    return content, usage, choices[0].get("finish_reason")
