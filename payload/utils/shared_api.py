# SPDX-License-Identifier: AGPL-3.0-only
"""Resolve the user's existing translation API without exposing its credential."""
from dataclasses import dataclass, field
import base64
import copy
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


PDF_PROTOCOLS = {'auto', 'gemini', 'chat', 'responses'}


def pdf_protocol(profile, selected='auto'):
    if selected not in PDF_PROTOCOLS:
        raise ValueError('无效的 PDF 接口格式')
    if selected != 'auto':
        return selected
    if profile.provider == 'gemini' or profile.model.lower().removeprefix('models/').startswith('gemini'):
        return 'gemini'
    if profile.provider == 'openai' or urllib.parse.urlsplit(profile.endpoint).hostname == 'api.openai.com':
        return 'responses'
    return 'chat'


def pdf_request(profile, pdf, filename, system_prompt, protocol='auto', search_tools=False):
    """One complete original PDF. Omit every generation/thinking/token budget."""
    protocol = pdf_protocol(profile, protocol)
    endpoint = checked_endpoint(profile.endpoint)
    encoded = base64.b64encode(pdf).decode('ascii')
    instruction = '请完整阅读所附 PDF，按系统中的论文阅读模板生成中文深度结构化笔记。'
    headers = {'Authorization': 'Bearer ' + profile.key, 'Content-Type': 'application/json',
               'Accept': 'application/json', 'User-Agent': 'zotero-pdf2zh-body-only'}
    if protocol == 'gemini':
        if endpoint.endswith('/openai'):
            endpoint = endpoint[:-len('/openai')]
        if endpoint.endswith('/v1'):
            endpoint = endpoint[:-len('/v1')]
        if not endpoint.endswith(('/v1beta', '/v1alpha')):
            endpoint += '/v1beta'
        endpoint += '/models/' + urllib.parse.quote(profile.model.removeprefix('models/'), safe='') + ':generateContent'
        if urllib.parse.urlsplit(endpoint).hostname == 'generativelanguage.googleapis.com':
            headers.pop('Authorization')
            headers['x-goog-api-key'] = profile.key
        payload = {'systemInstruction': {'parts': [{'text': system_prompt}]},
                   'contents': [{'role': 'user', 'parts': [
                       {'inlineData': {'mimeType': 'application/pdf', 'data': encoded}}, {'text': instruction}]}]}
    elif protocol == 'responses':
        if not endpoint.endswith('/responses'):
            endpoint += '/responses'
        payload = {'model': profile.model, 'instructions': system_prompt, 'stream': False,
                   'input': [{'role': 'user', 'content': [
                       {'type': 'input_file', 'filename': filename, 'file_data': 'data:application/pdf;base64,' + encoded},
                       {'type': 'input_text', 'text': instruction}]}]}
    else:
        endpoint += '/chat/completions'
        payload = {'model': profile.model, 'stream': False, 'messages': [
            {'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': [
                {'type': 'file', 'file': {'filename': filename, 'file_data': 'data:application/pdf;base64,' + encoded}},
                {'type': 'text', 'text': instruction}]}]}
    if search_tools and protocol == 'gemini':
        payload['tools'] = [{'google_search': {}}]
    elif search_tools and protocol == 'responses':
        payload.update(tools=[{'type': 'web_search'}], include=['web_search_call.action.sources'])
    return endpoint, payload, headers, protocol


def parse_pdf_response(data, protocol):
    if protocol == 'gemini':
        choices = data.get('candidates') or []
        if not choices:
            raise ValueError('API 未返回 PDF 阅读内容，可能被内容过滤或不支持该文件')
        candidate = choices[0]
        content = '\n'.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', [])
                            if not part.get('thought') and isinstance(part.get('text'), str))
        metadata = data.get('usageMetadata') or {}
        usage = {}
        for original, name in [('promptTokenCount', 'prompt_tokens'), ('candidatesTokenCount', 'completion_tokens'),
                               ('thoughtsTokenCount', 'reasoning_tokens'), ('totalTokenCount', 'total_tokens')]:
            if isinstance(metadata.get(original), int) and metadata[original] >= 0:
                usage[name] = metadata[original]
        if 'completion_tokens' in usage:
            usage['completion_tokens'] += usage.get('reasoning_tokens', 0)
        finish = candidate.get('finishReason')
        finish = 'stop' if finish == 'STOP' else 'length' if finish == 'MAX_TOKENS' else 'content_filter' if finish in {
            'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY'} else 'unknown'
    elif protocol == 'responses':
        content = '\n'.join(part.get('text', '') for item in data.get('output', []) if item.get('type') == 'message'
                            for part in item.get('content', []) if part.get('type') == 'output_text')
        original = data.get('usage') or {}
        usage = {new: original[old] for old, new in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'),
                                                   ('total_tokens', 'total_tokens')] if isinstance(original.get(old), int)}
        finish = 'stop' if data.get('status') == 'completed' else 'length' if (data.get('incomplete_details') or {}).get('reason') == 'max_output_tokens' else 'unknown'
    else:
        choices = data.get('choices') or []
        if not choices:
            raise ValueError('API 未返回 PDF 阅读内容，请确认接口和模型支持 PDF 文件输入')
        content = choices[0].get('message', {}).get('content', '')
        if isinstance(content, list):
            content = '\n'.join(part.get('text', '') for part in content if part.get('type') == 'text')
        usage = data.get('usage') or {}
        finish = choices[0].get('finish_reason') or 'unknown'
    if not isinstance(content, str) or (not content.strip() and finish != 'length'):
        raise ValueError('API 返回了空内容，请确认模型支持完整 PDF 阅读')
    return content, usage, finish


CONTINUE_PDF = ('继续完成同一份论文阅读笔记，从上一条输出中断的准确位置继续。不要重新开始，不要重复已有标题、段落或公式。'
                '此前提交的完整 PDF 仍是阅读依据，请完成余下全部内容。若上一条实际已经完成，只输出 [KINBO_READING_COMPLETE]。')


def continue_pdf_request(body, response, protocol):
    body = copy.deepcopy(body)
    if protocol == 'gemini':
        # Retain native thought signatures exactly as returned by the API.
        model = copy.deepcopy(response['candidates'][0].get('content') or {})
        model.setdefault('role', 'model')
        if model.get('parts'):
            body['contents'].extend([model, {'role': 'user', 'parts': [{'text': CONTINUE_PDF}]}])
        else:
            body['contents'][-1]['parts'].append({'text': '上一轮达到输出上限但没有返回正文，请直接开始输出完整笔记。' + CONTINUE_PDF})
    elif protocol == 'responses':
        body['input'].extend(copy.deepcopy(response.get('output', [])))
        body['input'].append({'role': 'user', 'content': [{'type': 'input_text', 'text': CONTINUE_PDF}]})
    else:
        original = response['choices'][0]['message']
        assistant = {'role': 'assistant', 'content': copy.deepcopy(original.get('content', ''))}
        if 'reasoning_content' in original:
            assistant['reasoning_content'] = original['reasoning_content']
        if assistant['content']:
            body['messages'].extend([assistant, {'role': 'user', 'content': CONTINUE_PDF}])
        elif isinstance(body['messages'][-1]['content'], list):
            body['messages'][-1]['content'].append({'type': 'text', 'text': CONTINUE_PDF})
        else:
            body['messages'][-1]['content'] += '\n\n' + CONTINUE_PDF
    return body


def read_pdf(profile, pdf, filename, system_prompt, protocol='auto', timeout=None, conversation=None, search_tools=False):
    endpoint, body, headers, protocol = pdf_request(profile, pdf, filename, system_prompt, protocol, search_tools)
    if conversation and conversation.get('response'):
        body = continue_pdf_request(conversation['body'], conversation['response'], protocol)
    req = urllib.request.Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST', headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        # Provider errors sometimes echo credentials or request content.
        status = error.code
        error.close()
        if status in {400, 404, 413, 415, 422}:
            raise ValueError(f'完整 PDF 请求失败，HTTP {status}。请确认接口格式、模型文件输入能力、文件大小与上下文范围。未自动切分、降级或重试') from None
        raise ValueError(f'API 请求失败，HTTP {status}。请检查接口、模型权限和额度。未自动重试') from None
    except urllib.error.URLError:
        raise ValueError("无法连接 API，请检查网络与接口地址") from None
    except TimeoutError:
        raise ValueError('PDF 阅读请求等待超时，可调整网络等待时间。未自动重新调用 API') from None
    result = parse_pdf_response(data, protocol)
    if conversation is not None:
        conversation.update(body=body, response=data)
    return result
