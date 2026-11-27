"""静态检查：路由函数的入参有没有被 FastAPI 静默丢掉。

背景：`tag: list[str] | None = None` 这种写法，FastAPI 会按 **body** 处理 list，
GET 请求没有 body，`?tag=xxx` 就被丢了，接口永远收到 None —— 而且**不报错**。
标签筛选就是这么坏的，前端点了、CLI 传了，看着都没反应。

这个脚本对比「函数签名里的入参」和「OpenAPI 里注册的 query 参数」，
端点没有 requestBody 却没注册的，就是被丢的那个。

用法：
    python tests/check_query_params.py
退出码 0 表示干净，1 表示有可疑入参。
"""
import inspect
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 数据目录指向临时空库，避免碰到真实数据
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="tp-paramscan-"))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import params as fparams  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    spec = app.openapi()
    suspects: list[tuple[str, str, str, str, object]] = []
    composite: list[tuple[str, str, str, str]] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        try:
            sig = inspect.signature(route.endpoint)
        except (TypeError, ValueError):
            continue

        for method in route.methods:
            op = spec["paths"].get(route.path, {}).get(method.lower(), {})
            registered = {p["name"] for p in op.get("parameters", [])}
            path_params = set(route.param_convertors or {})
            has_body = "requestBody" in op

            for name, p in sig.parameters.items():
                if name in ("request", "self") or name in path_params:
                    continue
                if isinstance(p.default, fparams.Depends):
                    continue
                if p.annotation in (Request, Response):
                    continue

                ann = str(p.annotation)
                if "list[" in ann or "dict[" in ann or ann in ("list", "dict"):
                    explicit = (
                        "Query" if isinstance(p.default, fparams.Query)
                        else "Body" if isinstance(p.default, fparams.Body)
                        else "Form" if isinstance(p.default, fparams.Form)
                        else "未显式声明"
                    )
                    composite.append((f"{method.upper()}", route.path, name, explicit))

                if name in registered or has_body:
                    continue
                suspects.append((method.upper(), route.path, name, ann.replace("typing.", ""), p.default))

    print("— 复合类型（list / dict）入参 —")
    if composite:
        for m, path, name, how in composite:
            flag = "" if how in ("Query", "Body", "Form") else "   ← 危险：list/dict 必须显式声明"
            print(f"  {m:6} {path:38} {name:14} {how}{flag}")
    else:
        print("  （无）")

    print("\n— 未注册成 query、端点也没有 body 的入参 —")
    if suspects:
        for m, path, name, ann, default in suspects:
            print(f"  {m:6} {path:38} {name:16} {ann:32} default={default!r}")
        print(f"\n共 {len(suspects)} 处，调用方传的参数会被静默丢弃")
        return 1
    print("  （无，干净）")

    # list/dict 没写 Query/Body/Form 时，FastAPI 会把它塞进 requestBody，
    # 于是上面的「有没有 body」判断看不出问题 —— 这里单独判一次
    danger = [c for c in composite if c[3] == "未显式声明"]
    if danger:
        print(f"\n共 {len(danger)} 处 list/dict 入参没显式声明，GET 请求会收不到值")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
