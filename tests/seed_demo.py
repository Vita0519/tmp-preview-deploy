#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成演示数据：多成员、多标签、多类型，方便看列表/筛选效果。"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import Client, multipart  # noqa: E402

BASE = "http://127.0.0.1:8010"
admin = Client(BASE)
admin.login("admin", "admin123")

print("agents...")
for name, disp in (("alice", "Alice · 前端"), ("bob", "Bob · 设计")):
    code, d = admin.req("POST", "/api/agents", {"username": name, "display_name": disp})
    print(" ", name, code)

PAGES = {
    "index.html": """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Demo Landing</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"PingFang SC",system-ui,sans-serif;
background:#0b0d0c;color:#f4f6f4;min-height:100vh;display:grid;place-items:center;overflow:hidden}
.wrap{text-align:center;padding:40px}
.kicker{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#7dd3c0;margin-bottom:18px}
h1{font-size:clamp(32px,6vw,64px);letter-spacing:-.03em;line-height:1.05;margin:0 0 16px}
h1 em{font-style:normal;color:#7dd3c0}
p{color:#9aa3a0;max-width:520px;margin:0 auto 28px;line-height:1.7;font-size:15px}
.btn{display:inline-flex;height:42px;align-items:center;padding:0 22px;border-radius:10px;background:#7dd3c0;
color:#08211c;font-weight:650;text-decoration:none}
.grid{position:fixed;inset:0;background-image:linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px);background-size:56px 56px;
mask-image:radial-gradient(70% 60% at 50% 40%,#000 30%,transparent 100%)}
</style></head><body><div class="grid"></div>
<div class="wrap"><div class="kicker">Preview Build · 2026</div>
<h1>把想法，<em>当场</em>给人看。</h1>
<p>这是一个部署在临时预览站上的示例页面，用于验收与评审；到期后自动回收，不占你的磁盘。</p>
<a class="btn" href="#">查看详情</a></div></body></html>""",
}

def upload(slug, title, desc, tags, hours, owner=None, download=False, visibility="portal", files=None):
    body_files = files or [("files", "index.html", PAGES["index.html"].encode())]
    fields = {
        "slug": slug,
        "title": title,
        "description": desc,
        "tags": tags,
        "hours": hours,
        "allow_download": "1" if download else "0",
        "visibility": visibility,
    }
    if owner:
        fields["owner"] = owner
    body, ctype = multipart(fields, body_files)
    code, d = admin.req("POST", "/api/projects", body, {"Content-Type": ctype}, ct=ctype)
    print(" ", slug, code, d.get("slug") if code == 200 else d)
    return d

print("projects...")
upload("landing-v2", "营销落地页 v2", "新版首屏，等客户确认动效节奏", "前端,campaign,v2", 24, owner="alice")
upload("dashboard-proto", "数据看板原型", "运营指标看板交互稿，含 4 个视图", "设计,看板", 72, owner="bob", visibility="portal")
upload("glb-showcase", "3D 产品展示", "WebGL 模型加载与光影测试", "webgl,模型", 168, owner="alice", download=True)
upload("acceptance-pack", "客户验收包（压缩）", "含源码与说明文档，仅提供下载", "验收,交付", 6, owner="bob", download=True, visibility="link")

# zip 类型项目
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("README.md", "# 验收包\n\n包含构建产物与说明。\n")
    z.writestr("dist/index.html", PAGES["index.html"])
body, ctype = multipart(
    {"slug": "zip-bundle", "title": "构建产物 2026-10", "description": "整包下载，用于内网部署",
     "tags": "交付,构建", "hours": "48", "owner": "bob"},
    [("zip", "bundle.zip", buf.getvalue())],
)
print("  zip-bundle", admin.req("POST", "/api/projects", body, {"Content-Type": ctype}, ct=ctype)[0])

code, d = admin.req("POST", "/api/projects/link", {
    "link_url": "https://www.figma.com/file/demo",
    "title": "设计稿（外链）",
    "slug": "figma-design",
    "description": "跳转到 Figma 源文件",
    "tags": ["设计", "figma"],
    "visibility": "portal",
    "hours": 240,
})
print("  figma-design", code)

print("simulate views...")
for slug, n in (("landing-v2", 46), ("dashboard-proto", 12), ("glb-showcase", 7), ("figma-design", 0)):
    for _ in range(n):
        admin.req("GET", f"/p/{slug}/", raw=True, headers={"Accept": "text/html"})
print("done")
