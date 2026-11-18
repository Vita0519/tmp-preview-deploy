# 飞牛 fnOS 应用包（fpk）

把 tmp-preview 打成飞牛应用中心可安装的 `.fpk`。安装后由应用中心执行
`app/docker/docker-compose.yaml` 启停容器，数据落在应用数据目录。

## 目录

```
packaging/fnos/
├── template/                 # fpk 工程模板
│   ├── manifest              # 应用元信息（appname / version / service_port …）
│   ├── config/privilege      # 运行身份
│   ├── config/resource       # 声明 docker-project 与数据共享目录
│   ├── cmd/                  # 生命周期脚本（start/stop/status 等）
│   ├── wizard/install        # 安装向导（管理员账号、站点标题、门户开关）
│   ├── app/docker/           # compose + 单阶段 Dockerfile
│   ├── app/ui/               # 桌面入口与图标
│   ├── ICON.PNG              # 64×64
│   └── ICON_256.PNG          # 256×256
├── make_icons.py             # 从 frontend/public/icon-512.png 生成图标
├── build.py                  # 复制模板 + 打包源码 + fnpack build
└── out/                      # 产物（不入库）
```

## 构建

```bash
# 1. 前端产物（容器内不再装 Node，直接复制 dist）
cd frontend && npm run build && cd ..

# 2. 图标（改了站点图标才需要）
python packaging/fnos/make_icons.py

# 3. 打包（需要飞牛官方 fnpack）
#    https://developer.fnnas.com/docs/cli/fnpack/
python packaging/fnos/build.py
```

`fnpack` 不在 PATH 时用环境变量指定：

```bash
FNPACK=/path/to/fnpack python packaging/fnos/build.py
```

产物：`packaging/fnos/out/tmp-preview.fpk`

## 安装

1. 飞牛「应用中心 → 手动安装」，选择 `tmp-preview.fpk`
2. 向导里填管理员用户名/密码（密码留空则首启自动生成，到容器日志查看）
3. 首次启动会构建镜像（拉取 `python:3.12-slim` 与依赖，几分钟），完成后访问
   `http://<NAS 地址>:519`

## 运行方式

- 端口：宿主机 `519` → 容器 `8000`（改端口需同时改 `manifest` 的 `service_port`、
  `app/ui/config` 的 `port` 与 compose 的端口映射）
- `519` 属于特权端口（<1024）：Docker 由 root 运行时正常；若应用中心以普通用户
  启动容器导致绑定失败，把三处端口一起改成 `10519` 即可
- 数据：`${TRIM_PKGVAR}/data`（SQLite + 项目文件 + zip），卸载不删除
- 镜像：`tmp-preview:2.0.0`，由 compose 的 `build` 从 `app/docker/src` 构建，
  不依赖任何镜像仓库

## 外网访问

推荐 Cloudflare Tunnel，并显式指定 HTTP/2（家宽 UDP 常被限速）：

```bash
cloudflared tunnel run --protocol http2 --token <TOKEN>
```

## 已知限制

- 首次安装需要 NAS 能拉取 Docker Hub 的 `python:3.12-slim` 与 pip 依赖
- 升级 = 重新打包并安装新 fpk；数据目录保留，迁移在启动时自动执行
- 应用内目前是单租户；如需多租户共享一套实例，需要额外做租户改造
