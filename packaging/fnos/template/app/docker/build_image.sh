#!/bin/bash
# 在 NAS 上构建 tmp-preview 镜像（应用中心不会替你构建）
# 用法：bash build_image.sh [源码目录，默认脚本同级的 src]
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
SRC="${1:-$HERE/src}"
IMAGE="tmp-preview:2.0.0"

if [ ! -f "$SRC/Dockerfile" ]; then
    echo "找不到 Dockerfile：$SRC/Dockerfile" >&2
    exit 1
fi

echo "构建 $IMAGE（源码：$SRC）"
docker build -t "$IMAGE" "$SRC"
echo "完成：docker image ls | grep tmp-preview"
