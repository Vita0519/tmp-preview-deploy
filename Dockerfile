# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS web

WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- 阶段 2：运行时 ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

# OCI 标注：镜像里也带上许可与出处（AGPL-3.0 要求保留署名，见 NOTICE）
LABEL org.opencontainers.image.title="tmp-preview" \
      org.opencontainers.image.description="临时预览站：带到期时间的自托管预览 / 下载服务" \
      org.opencontainers.image.authors="Vita0519" \
      org.opencontainers.image.url="https://github.com/Vita0519/tmp-preview-deploy" \
      org.opencontainers.image.source="https://github.com/Vita0519/tmp-preview-deploy" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /web/dist frontend/dist

# 镜像里也留一份许可与署名声明（AGPL-3.0 要求随分发保留）
COPY LICENSE NOTICE VERSION /app/
# 主题商店的示例插件随镜像分发：装示例插件不依赖外网
COPY examples /app/examples/

RUN mkdir -p /data/projects /data/zips

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
