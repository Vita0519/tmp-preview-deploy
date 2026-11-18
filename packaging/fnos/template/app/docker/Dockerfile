# 飞牛 fpk 专用：前端已构建，单阶段镜像，避免在 NAS 上装 Node
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

LABEL org.opencontainers.image.title="tmp-preview" \
      org.opencontainers.image.description="临时预览站：带到期时间的自托管预览 / 下载服务" \
      org.opencontainers.image.authors="孟庆炜 (Vita0519)" \
      org.opencontainers.image.url="https://github.com/Vita0519/tmp-preview-deploy" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/dist frontend/dist
COPY LICENSE NOTICE /app/

RUN mkdir -p /data/projects /data/zips

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
