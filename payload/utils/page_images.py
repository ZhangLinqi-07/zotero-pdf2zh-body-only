# SPDX-License-Identifier: AGPL-3.0-only
"""Complete-page visual input, without text extraction, page selection or summaries."""
import base64
import json
import math
import urllib.parse

import pymupdf

MODES = {'auto', 'pdf', 'images'}
DEEPSEEK_MODELS = {'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp'}
DEEPSEEK_BODY_LIMIT = 48 * 1024 * 1024


def official_deepseek(profile):
    return urllib.parse.urlsplit(profile.endpoint).hostname == 'api.deepseek.com'


def select_mode(profile, selected='auto'):
    if selected not in MODES:
        raise ValueError('无效的论文输入模式')
    deepseek = official_deepseek(profile)
    mode = ('images' if deepseek else 'pdf') if selected == 'auto' else selected
    if deepseek and mode == 'pdf':
        raise ValueError('DeepSeek 官方 API 不接收 PDF 文件，请在阅读选项中选择全部页面图像或自动模式')
    if deepseek and profile.model.lower() not in DEEPSEEK_MODELS:
        raise ValueError('DeepSeek 全部页面图像阅读需要支持视觉的完整模型名 deepseek-flash，请核对已配置模型')
    return mode


def render_all(pdf, profile, cancelled=lambda: False):
    """144 dpi PNGs in page order. Reject oversized input rather than omit pages."""
    images = []
    encoded_bytes = 0
    with pymupdf.open(stream=pdf, filetype='pdf') as document:
        count = len(document)
        if official_deepseek(profile) and count > 600:
            raise ValueError('PDF 超过 DeepSeek 单次请求的 600 张图像上限，尚未调用 API。未省略任何页面')
        max_side = 4096 if count >= 15 else 8192
        for index, page in enumerate(document):
            if cancelled():
                raise InterruptedError('已停止页面渲染')
            width, height = math.ceil(page.rect.width * 2), math.ceil(page.rect.height * 2)
            if width < 1 or height < 1 or width * height > 40_000_000 or (
                    official_deepseek(profile) and max(width, height) > max_side):
                raise ValueError('整页图像在 144 dpi 下超过图像尺寸限制，尚未调用 API。未裁剪或省略页面')
            raw = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False).tobytes('png')
            data = base64.b64encode(raw).decode('ascii')
            encoded_bytes += len(data)
            if official_deepseek(profile) and encoded_bytes > DEEPSEEK_BODY_LIMIT:
                raise ValueError('全部页面图像超过 DeepSeek 的 48 MiB 请求限制，尚未调用 API。未选页或分段阅读')
            images.append({'page': index + 1, 'mimeType': 'image/png', 'data': data,
                           'width': width, 'height': height})
    return images


def serialize(profile, body):
    data = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if official_deepseek(profile) and len(data) > DEEPSEEK_BODY_LIMIT:
        raise ValueError('完整请求超过 DeepSeek 的 48 MiB 限制，本次请求未发送。已有笔记会保留，未省略论文页面')
    return data
