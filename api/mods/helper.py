import os
import sys
import inspect
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import get_type_hints, List as PyList, Dict as PyDict, Any as PyAny
from urllib.parse import parse_qs
from http.cookies import SimpleCookie

from typed import Any, TYPE, Str, Bool, Function, Dict, List, Nill
from utils.types import Json
from typed.mods.helper.helper import (
    _hinted_domain,
    _hinted_codomain,
    _check_domain,
    _check_codomain,
)

# ---------------------------------------------------------------------------
# Globals for IP-blocking and misc
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Minimal Request / QueryParams / Error
# ---------------------------------------------------------------------------


class Error(Exception):
    """
    Simple HTTP-style error used internally by the framework.
    """

    def __init__(self, status_code: int, detail: str, headers: PyDict[str, str] | None = None):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail
        self.headers = headers or {}


class QueryParams:
    """
    Very small helper for query-parameter access, similar to Starlette's QueryParams.
    """

    def __init__(self, query_string: bytes | str | None):
        if isinstance(query_string, bytes):
            qs = query_string.decode("ascii", "ignore")
        else:
            qs = query_string or ""
        self._data: PyDict[str, PyList[str]] = parse_qs(qs, keep_blank_values=True)

    def get(self, name: str, default: PyAny = None) -> PyAny:
        values = self._data.get(name)
        if not values:
            return default
        return values[0]

    def getlist(self, name: str) -> PyList[str]:
        return self._data.get(name, [])

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def __repr__(self) -> str:
        return f"QueryParams({self._data!r})"


class Request:
    """
    Minimal request object the framework uses internally.

    Built from the ASGI scope + body by api.API.__call__.
    """

    def __init__(
        self,
        method: str,
        path: str,
        query_string: bytes | str | None,
        headers: PyList[tuple[bytes, bytes]] | None,
        path_params: PyDict[str, str] | None,
        body: bytes | None,
        client: tuple[str, int] | None,
    ):
        self.method = method.upper()
        self.path = path
        self.query_params = QueryParams(query_string)
        self.path_params: PyDict[str, str] = path_params or {}
        self._body = body or b""
        self.client = client

        # Normalize headers to lower-case string keys
        hdrs: PyDict[str, str] = {}
        if headers:
            for name_b, value_b in headers:
                name = name_b.decode("latin1").lower()
                value = value_b.decode("latin1")
                hdrs[name] = value
        self.headers = hdrs

        # Cookies
        cookie_header = self.headers.get("cookie")
        if cookie_header:
            c = SimpleCookie()
            c.load(cookie_header)
            self.cookies = {k: morsel.value for k, morsel in c.items()}
        else:
            self.cookies = {}

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> PyAny:
        if not self._body:
            return None
        text = self._body.decode("utf-8", errors="ignore")
        return json.loads(text)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


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


def _parse_query_value(name: str, ann, request: Request) -> Any:
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


async def _read_body(request: Request) -> Any:
    try:
        ctype = request.headers.get("content-type") or ""
        if "application/json" in ctype:
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
    if ann is Nill or ann is inspect._empty:
        return False
    if getattr(ann, "is_model", False):
        return True
    if ann <= Json or ann <= List or ann <= Dict:
        return True
    return False


async def _build_kwargs(func: Function, request: Request) -> Dict:
    """
    Build kwargs for a user handler based on function signature and Request.
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    params = sig.parameters
    path_params = request.path_params or {}
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

        # Path params
        if name in path_params:
            value = path_params[name]
            kw[name] = _parse_literal(_parse_json_maybe(value))
            continue

        # Query params
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
                    raise TypeError(
                        f"Body for '{name}' must be a JSON object "
                        f"for model '{getattr(ann, '__name__', str(ann))}'"
                    )
                from typed.mods.models import validate as typed_validate

                entity = typed_validate(body_value, ann)
                kw[name] = ann(**entity)
            else:
                kw[name] = body_value
            continue

        # Default or required
        if p.default is not inspect._empty:
            kw[name] = p.default
        else:
            # Validation-like error
            raise Error(
                status_code=422,
                detail=f"Missing required parameter '{name}'",
            )

    return kw


# ---------------------------------------------------------------------------
# Middlewares (IP block, token auth)
# ---------------------------------------------------------------------------


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

    # Determine client IP
    client = getattr(request, "client", None)
    if isinstance(client, tuple) and client:
        ip = client[0]
    else:
        ip = "unknown"

    now = datetime.now()

    info = blocked_ips.get(ip)
    if info is not None:
        blocked_until = info.get("blocked_until")
        if blocked_until is None or blocked_until > now:
            raise Error(
                status_code=403,
                detail=info.get("message", block_mid.message),
            )
        else:
            blocked_ips.pop(ip, None)
            _auth_failures.pop(ip, None)

    if status_code is None:
        return

    raw_codes = getattr(block_mid, "codes", None)

    if raw_codes is None:
        return

    if isinstance(raw_codes, (list, tuple, set)):
        codes = [int(c) for c in raw_codes]
    else:
        try:
            codes = [int(c) for c in list(raw_codes)]
        except TypeError:
            codes = [int(raw_codes)]

    if not codes:
        return

    if status_code not in codes:
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

        raise Error(
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
            raise Error(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )
        return

    raise Error(status_code=500, detail="Unsupported authentication type")


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def _make_handler(func: Function, method: Str, mids=None) -> Function:
    """
    Wrap the user handler into an async callable that:
      - builds kwargs from Request (path/query/body/headers/cookies)
      - checks typed domain/codomain
      - runs sync functions in a thread
    Note: middlewares (auth/block) are *not* applied here; they are
    applied centrally in api.API.__call__.
    """
    original = _unwrap(func)
    sig = inspect.signature(original)
    param_names = [
        name
        for name, p in sig.parameters.items()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]

    expected_domain = _hinted_domain(original)
    expected_codomain = _hinted_codomain(original)
    is_async = inspect.iscoroutinefunction(original)

    async def handler(request: Request):
        kw = await _build_kwargs(original, request)
        args_list = [kw[name] for name in param_names if name in kw]

        _check_domain(original, param_names, expected_domain, None, args_list)

        if is_async:
            result = await original(**kw)
        else:
            # Run sync handler in a thread
            result = await asyncio.to_thread(original, **kw)

        _check_codomain(
            original,
            expected_codomain,
            TYPE(result),
            result,
            param_value_map=kw,
        )

        return result

    return handler


# ---------------------------------------------------------------------------
# Import string helper (left mostly unchanged)
# ---------------------------------------------------------------------------


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

