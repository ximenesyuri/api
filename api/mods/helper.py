import os
import sys
import inspect
import logging
from datetime import datetime, timedelta
import json
from typing import get_type_hints
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool
from typed import Any, TYPE, Str, Bool, Function, Json, Dict, List
from typed.mods.helper.helper import (
    _hinted_domain,
    _hinted_codomain,
    _check_domain,
    _check_codomain,
)

blocked_ips = {}

_auth_failures = {}
_ROUTER_CLASS = None
_api_name = None

def _set_api_name(name: Str) -> None:
    global _api_name
    _api_name = name

def _get_router_class():
    global _ROUTER_CLASS
    if _ROUTER_CLASS is None:
        try:
            from api.mods.router import Router
            _ROUTER_CLASS = Router
        except Exception:
            _ROUTER_CLASS = object
    return _ROUTER_CLASS

def _build_logger(logger, formatter) -> logging.Logger:
    logger = logging.getLogger(logger)
    logger.setLevel(logging.DEBUG)
    logger.propagate = True
    return logger

def _truncate_router_name(name: Str, maxlen: int) -> Str:
    if len(name) <= maxlen:
        return name
    if maxlen <= 3:
        return name[:maxlen]
    return name[: maxlen - 3] + "..."

def _build_prefix(col_width, router_name=None) -> Str:
    api_name = _api_name or "api"
    api_part = f"[{api_name}]"
    label = router_name or ""
    if label:
        label = _truncate_router_name(label, col_width)
        router_bracket = f"[{label}]"
    else:
        router_bracket = "[]"

    target_width = col_width + 2
    spaces_after = max(0, target_width - len(router_bracket))
    router_part = f"{router_bracket}{' ' * spaces_after}"

    return f"{api_part} {router_part} "

def _unwrap(func):
    f = func
    while hasattr(f, "func") and callable(getattr(f, "func")):
        inner = getattr(f, "func")
        if inner is f:
            break
        f = inner
    return f

def _looks_like_json(s: Str) -> Bool:
    if not isinstance(s, str):
        return False
    t = s.strip()
    return (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]"))

def _parse_literal(value):
    if not isinstance(value, str):
        return value
    s = value.strip()
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        if (s.startswith(("+", "-")) and s[1:].isdigit()) or s.isdigit():
            return int(s)
    except Exception:
        pass
    try:
        return float(s)
    except Exception:
        pass
    return value

def _parse_json_maybe(value):
    if not isinstance(value, str):
        return value
    if _looks_like_json(value):
        try:
            import json
            return json.loads(value)
        except Exception:
            return value
    return value

def _maybe_cast_sequence_to_target(seq, ann):
    try:
        from typed.helper import name as typed_name
    except Exception:
        typed_name = lambda x: str(x)
    if not isinstance(seq, list):
        return seq
    n = typed_name(ann) if ann is not None else ""
    if n.startswith("Tuple(") or n == "Tuple":
        return tuple(seq)
    if n.startswith("Set(") or n == "Set":
        return set(seq)
    return seq

def _parse_query_value(name: str, ann, request) -> Any:
    vals = request.query_params.getlist(name)
    if len(vals) > 1:
        parsed = [_parse_literal(v) for v in vals]
        return _maybe_cast_sequence_to_target(parsed, ann)

    if len(vals) == 1:
        v = vals[0]
        j = _parse_json_maybe(v)
        if j is not v:
            return _maybe_cast_sequence_to_target(j, ann)
        if "," in v:
            parts = [p for p in v.split(",")]
            parsed = [_parse_literal(p) for p in parts]
            return _maybe_cast_sequence_to_target(parsed, ann)
        return _parse_literal(v)

    return None

def _to_response(result: Any) -> Response:
    if isinstance(result, Response):
        return result

    if hasattr(result, "__json__"):
        return JSONResponse(result.__json__)

    if isinstance(result, tuple) and len(result) == 2:
        data, status = result
        if hasattr(data, "__json__"):
            data = data.__json__
        return JSONResponse(data, status_code=int(status))

    if result is None:
        return Response(status_code=204)

    if isinstance(result, (dict, list)):
        return JSONResponse(result)

    try:
        json.dumps(result)
        return JSONResponse(result)
    except Exception:
        return PlainTextResponse(str(result))

async def _read_body(request: Request) -> Any:
    try:
        if "application/json" in (request.headers.get("content-type") or ""):
            return await request.json()
        body_bytes = await request.body()
        if not body_bytes:
            return None
        text = body_bytes.decode("utf-8", errors="ignore")
        try:
            return json.loads(text)
        except Exception:
            return text
    except Exception:
        return None

def _want_body_for(param_name: Str, ann: Any) -> Bool:
    if ann is None or ann is inspect._empty:
        return False
    if getattr(ann, "is_model", False):
        return True
    if ann is Json or ann is Dict or ann is dict or ann is list or isinstance(ann, (List, Dict)):
        return True
    return False

async def _build_kwargs(func: Function, request: Request) -> Dict:
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    params = sig.parameters
    path_params = request.path_params or {}
    query_params = request.query_params
    headers = {k.lower(): v for k, v in request.headers.items()}
    cookies = request.cookies or {}

    body_loaded = False
    body_value: Any = None

    kw = {}

    for name, p in params.items():
        if name == "request":
            kw[name] = request
            continue

        ann = hints.get(name)

        # Path
        if name in path_params:
            value = path_params[name]
            kw[name] = _parse_json_maybe(value)
            kw[name] = _parse_literal(kw[name])
            continue

        # Query
        if name in request.query_params:
            kw[name] = _parse_query_value(name, ann, request)
            continue

        # Headers
        if name.lower() in headers:
            v = headers[name.lower()]
            v = _parse_json_maybe(v)
            kw[name] = _parse_literal(v)
            continue

        # Cookies
        if name in cookies:
            v = cookies[name]
            v = _parse_json_maybe(v)
            kw[name] = _parse_literal(v)
            continue

        # Body
        if _want_body_for(name, ann):
            if not body_loaded:
                body_loaded = True
                body_value = await _read_body(request)

            if getattr(ann, "is_model", False):
                if not isinstance(body_value, dict):
                    raise TypeError(f"Body for '{name}' must be a JSON object for model '{getattr(ann, '__name__', str(ann))}'")
                from typed.mods.models import validate as typed_validate
                entity = typed_validate(body_value, ann)
                kw[name] = ann(**entity)
            else:
                kw[name] = body_value
            continue

        if p.default is not inspect._empty:
            kw[name] = p.default
        else:
            raise StarletteHTTPException(status_code=422, detail=f"Missing required parameter '{name}'")

    return kw

def _enforce_ip_block(request: Request, mids, status_code: int | None = None) -> None:
    from api.mods.mids import Block

    if not mids:
        return

    block_mid = None
    for m in mids:
        if isinstance(m, Block):
            block_mid = m
            break

    if block_mid is None:
        return

    ip = (request.client.host if request.client else None) or "unknown"
    now = datetime.now()

    info = blocked_ips.get(ip)
    if info is not None:
        blocked_until = info.get("blocked_until")
        if blocked_until is None or blocked_until > now:
            raise StarletteHTTPException(
                status_code=403,
                detail=info.get("message", block_mid.message),
            )
        else:
            blocked_ips.pop(ip, None)
            _auth_failures.pop(ip, None)

    if status_code is None:
        return

    codes = getattr(block_mid, "codes", []) or []
    if codes and status_code not in codes:
        return

    window_start = now - timedelta(seconds=int(block_mid.interval))
    failures = _auth_failures.setdefault(ip, [])
    failures[:] = [t for t in failures if t >= window_start]
    failures.append(now)

    if len(failures) >= int(block_mid.attempts):
        if block_mid.block_minutes < 0:
            blocked_until = None
        elif block_mid.block_minutes == 0:
            blocked_until = now
        else:
            blocked_until = now + timedelta(minutes=int(block_mid.block_minutes))

        blocked_ips[ip] = {
            "blocked_until": blocked_until,
            "message": block_mid.message,
            "reason": getattr(block_mid, "reason", None),
        }
        _auth_failures.pop(ip, None)

        raise StarletteHTTPException(
            status_code=403,
            detail=block_mid.message,
        )

def _enforce_token_auth(request: Request, mids) -> None:
    from api.mods.mids import Auth, Token

    if not mids:
        return

    auth_mid = None
    for m in mids:
        if isinstance(m, Auth):
            auth_mid = m
            break

    if auth_mid is None:
        return

    if isinstance(auth_mid, Token):
        expected = auth_mid.token

        got = None
        auth_header = request.headers.get("authorization")
        if auth_header:
            parts = auth_header.strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower() in ("token", "bearer"):
                got = parts[1].strip()

        if not got:
            got = request.headers.get("x-api-token")

        if not got:
            got = request.query_params.get("token")

        if not got or got != expected:
            raise StarletteHTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )
        return

    raise StarletteHTTPException(status_code=500, detail="Unsupported authentication type")


def _make_handler(func: Function, method: Str, mids=None) -> Function:
    original = _unwrap(func)
    sig = inspect.signature(original)
    param_names = [
        name for name, p in sig.parameters.items()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]

    expected_domain = _hinted_domain(original)
    expected_codomain = _hinted_codomain(original)
    is_async = inspect.iscoroutinefunction(original)

    async def handler(request: Request) -> Response:
        try:
            if mids:
                _enforce_ip_block(request, mids, status_code=None)
                _enforce_token_auth(request, mids)

            kw = await _build_kwargs(original, request)
            args_list = [kw[name] for name in param_names if name in kw]

            _check_domain(original, param_names, expected_domain, None, args_list)

            if is_async:
                result = await original(**kw)
            else:
                result = await run_in_threadpool(lambda: original(**kw))

            _check_codomain(original, expected_codomain, TYPE(result), result, param_value_map=kw)

            response = _to_response(result)

            if mids:
                _enforce_ip_block(request, mids, status_code=response.status_code)

            return response

        except StarletteHTTPException as exc:
            if mids:
                _enforce_ip_block(request, mids, status_code=exc.status_code)
            raise
        except TypeError:
            if mids:
                _enforce_ip_block(request, mids, status_code=422)
            raise
        except Exception:
            if mids:
                _enforce_ip_block(request, mids, status_code=500)
            raise

    return handler

def _import_string(self) -> str:
    caller_frame = inspect.stack()[2].frame
    g = caller_frame.f_globals

    caller_name = g.get("__name__", None)
    caller_file = g.get("__file__", None)

    var_name = None
    for k, v in g.items():
        if v is self:
            var_name = k
            break
    if not var_name:
        raise RuntimeError(
            "Could not determine the variable name for the API instance in the caller module.\n"
            "Make sure your API instance is assigned to a module-level variable (e.g., my_api = API())."
        )

    if caller_name and caller_name != "__main__":
        module_path = caller_name
    else:
        if not caller_file:
            raise RuntimeError(
                "Cannot infer import string: caller __file__ not available. "
                "Run from a regular Python module (not an interactive shell)."
            )
        caller_file = os.path.abspath(caller_file)

        best_base = None
        rel_mod = None
        for sp in map(os.path.abspath, sys.path):
            if not caller_file.startswith(sp + os.sep) and caller_file != sp:
                continue
            if best_base is None or len(sp) > len(best_base):
                best_base = sp
                rel = os.path.relpath(caller_file, sp)
                rel_mod = rel

        if rel_mod is None:
            raise RuntimeError(
                "Could not map the caller file to an importable module.\n"
                "Ensure your project root is on PYTHONPATH or run from the package root."
            )

        rel_mod = rel_mod.replace(os.sep, ".")
        if rel_mod.endswith(".py"):
            rel_mod = rel_mod[:-3]
        if rel_mod.endswith(".__init__"):
            rel_mod = rel_mod[: -len(".__init__")]

        module_path = rel_mod

    return f"{module_path}:{var_name}"
