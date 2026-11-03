#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
trap 'echo "Kinbo 安装未完成。请保留上方错误，按回车关闭。"; read -r; exit 1' ERR

kinbo_source="$(cd "$(dirname "$0")" && pwd)"
kinbo_boot="$kinbo_source/.bootstrap/macos"
case "$(uname -m)" in
  arm64)
    kinbo_platform="aarch64-apple-darwin"
    kinbo_sha="e0b1d4743ce64c55d9f0f4a444afa6b81125680070ee04e853fcd0f6c1ebf8f1"
    ;;
  x86_64)
    kinbo_platform="x86_64-apple-darwin"
    kinbo_sha="7be2dcd316122f4b3e5a0a7889f6248266c14425374e105ff7dc9779184603a6"
    ;;
  *) echo "此安装器支持 Apple Silicon 和 Intel Mac。"; exit 1 ;;
esac
mkdir -p "$kinbo_boot/bin"
kinbo_archive="$kinbo_boot/uv-$kinbo_platform-0.13.4.tar.gz"
if [ ! -f "$kinbo_archive" ]; then
  echo "正在下载经过固定版本校验的安装工具…"
  /usr/bin/curl --fail --location --retry 2 --connect-timeout 15 --max-time 180 \
    --output "$kinbo_archive.part" \
    "https://releases.astral.sh/github/uv/releases/download/0.13.4/uv-$kinbo_platform.tar.gz"
  mv "$kinbo_archive.part" "$kinbo_archive"
fi
printf '%s  %s\n' "$kinbo_sha" "$kinbo_archive" | /usr/bin/shasum -a 256 --check
/usr/bin/tar -xzf "$kinbo_archive" -C "$kinbo_boot/bin" --strip-components=1 "uv-$kinbo_platform/uv"
export UV_PYTHON_INSTALL_DIR="$kinbo_boot/python"
export UV_PYTHON_BIN_DIR="$kinbo_boot/python-bin"
"$kinbo_boot/bin/uv" python install 3.12 --no-bin --no-registry
"$kinbo_boot/bin/uv" run --no-project --no-config --python 3.12 python "$kinbo_source/setup_fresh.py" \
  --uv "$kinbo_boot/bin/uv" --install-dir "$HOME/Library/Application Support/Kinbo/app" --start "$@"
/usr/bin/open -a Zotero
/usr/bin/open -R "$HOME/Library/Application Support/Kinbo/app/zotero-pdf2zh-body-only.xpi"
echo "后台已配置自动启动，Finder 已选中 XPI。在 Zotero「工具 → 插件 → 从文件安装」中安装它。"
echo "首次安装的后台地址为 http://127.0.0.1:8891。"
