import logging
import json
from typed import model, List, Function, Maybe, Str
from utils.types import Path

from api.mods.helper import (
    _set_api_name,
    _enforce_ip_block,
    _enforce_token_auth,
    Error,
    Request,
)
from api.mods.response import Response
from api.mods.log import log
from api.mods.router import Router


@model
class _RouteEntry:
    method: Str
    path: Str
    handler: Function
    name: Str
    mids: Maybe(List)


def _match_path(template, path):
    t_parts = [p for p in template.strip("/").split("/") if p] or [""]
    p_parts = [p for p in path.strip("/").split("/") if p] or [""]
    if len(t_parts) != len(p_parts):
        return None

    params = {}
    for t, p in zip(t_parts, p_parts):
        if t.startswith("{") and t.endswith("}"):
            name = t[1:-1]
            params[name] = p
        elif t == p:
            continue
        else:
            return None
    return params


class API:
    def __init__(self, name="api", log_level='DEBUG', mids=None):
        try:
            self.name = name
            _set_api_name(self.name or "api")
        except Exception:
            self.name = name or "api"

        self._log_level = log_level
        self.mids = mids
        self._routes = []

        from api.mods.log import _get_app_logger

        self._logger = _get_app_logger()
        log_levels = {
            'DEBUG':    logging.DEBUG,
            'INFO':     logging.INFO,
            'WARNING':  logging.WARNING,
            'ERROR':    logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        self._logger.setLevel(log_levels.get(log_level.upper(), logging.INFO))

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"")
        headers = scope.get("headers") or []
        client = scope.get("client")

        if isinstance(client, tuple) and client:
            client_ip = client[0]
        else:
            client_ip = "unknown"

        if isinstance(query_string, (bytes, bytearray)):
            qs_raw = query_string.decode("ascii", "ignore")
        else:
            qs_raw = query_string or ""
        path_for_log = path if not qs_raw else f"{path}?{qs_raw}"

        client_log_done = False
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            mtype = message.get("type")
            if mtype == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            elif mtype == "http.disconnect":
                break
            else:
                more_body = False

        try:
            route, path_params = self._match_route(method, path)
        except Error as e:
            log.warning(
                f"Error {e.status_code}: {method} {path_for_log} -> {e.detail}",
                router_name=client_ip,
            )
            resp_model = Response(
                status="failure",
                code=e.status_code,
                data=e.detail,
            )
            await self._send_response(send, resp_model)
            return

        request = Request(
            method=method,
            path=path,
            query_string=query_string,
            headers=headers,
            path_params=path_params,
            body=body,
            client=client,
        )

        effective_mids = route.mids

        try:
            if effective_mids:
                _enforce_ip_block(request, effective_mids, status_code=None)
                _enforce_token_auth(request, effective_mids)

            result = await route.handler(request)

            resp_model = self._to_response_model(result)

            if effective_mids:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=resp_model.code)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        code=block_exc.status_code,
                        data=block_exc.detail,
                    )

        except Error as exc:
            msg = f"Error {exc.status_code}: {method} {path_for_log} -> {exc.detail}"
            log.client(msg, router_name=client_ip)
            client_log_done = True

            if effective_mids:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=exc.status_code)
                except Error as block_exc:
                    exc = block_exc

            resp_model = Response(
                status="failure",
                code=exc.status_code,
                data=exc.detail,
            )

        except TypeError as exc:
            log.client(
                f"Error 422: {method} {path_for_log} -> {exc}",
                router_name=client_ip,
            )
            client_log_done = True

            if effective_mids:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=422)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        code=block_exc.status_code,
                        data=block_exc.detail,
                    )
                else:
                    resp_model = Response(
                        status="failure",
                        code=422,
                        data=str(exc),
                    )
            else:
                resp_model = Response(
                    status="failure",
                    code=422,
                    data=str(exc),
                )

        except Exception as exc:
            log.error(
                f"Unhandled error on {method} {path_for_log}: {exc}",
                router_name=self.name,
            )
            detail = str(exc) if self._debug else "Internal Server Error"
            log.client(
                f"Error 500: {method} {path_for_log} -> {detail}",
                router_name=client_ip,
            )
            client_log_done = True

            if effective_mids:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=500)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        code=block_exc.status_code,
                        data=block_exc.detail,
                    )
                else:
                    resp_model = Response(
                        status="failure",
                        code=500,
                        data=detail,
                    )
            else:
                resp_model = Response(
                    status="failure",
                    code=500,
                    data=detail,
                )

        if not client_log_done:
            code = int(resp_model.code)
            if 200 <= code < 400:
                log.client(
                    f"OK {code}: {method} {path_for_log}",
                    router_name=client_ip,
                )
            else:
                data = resp_model.data
                if isinstance(data, dict) and "detail" in data:
                    detail = data["detail"]
                else:
                    detail = data
                log.client(
                    f"Error {code}: {method} {path_for_log} -> {detail}",
                    router_name=client_ip,
                )

        await self._send_response(send, resp_model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_route(self, method, path):
        for r in self._routes:
            if r.method != method.upper():
                continue
            params = _match_path(r.path, path)
            if params is not None:
                return r, params
        raise Error(404, f"No route for {method} {path}")

    def _to_response_model(self, result):
        if isinstance(result, Response):
            return result

        if hasattr(result, "__json__"):
            data = getattr(result, "__json__")
            return Response(status="success", code=200, data=data)

        try:
            json.dumps(result)
            data = result
        except TypeError:
            data = str(result)

        return Response(status="success", code=200, data=data)

    async def _send_response(self, send, resp: Response) -> None:
        try:
            payload = getattr(resp, "__json__", None)
            if payload is None:
                payload = {
                    "status": resp.status,
                    "code": resp.code,
                    "data": resp.data,
                }
        except Exception:
            payload = {
                "status": getattr(resp, "status", "failure"),
                "code": getattr(resp, "code", 500),
                "data": getattr(resp, "data", {"detail": "Serialization error"}),
            }

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body_bytes)).encode("ascii")),
        ]

        await send(
            {
                "type": "http.response.start",
                "status": int(resp.code),
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
                "more_body": False,
            }
        )

    # ------------------------------------------------------------------
    # Logging convenience
    # ------------------------------------------------------------------

    def log(self, level, message: str, *args, **kwargs) -> None:
        if isinstance(level, str):
            lvl = level.lower().strip()
            level_map = {
                "debug": logging.DEBUG,
                "info": logging.INFO,
                "warning": logging.WARNING,
                "error": logging.ERROR,
                "critical": logging.CRITICAL,
            }
            lvlno = level_map.get(lvl, logging.INFO)
        else:
            lvlno = int(level)
        self._logger.log(lvlno, message, *args, **kwargs)

    def debug(self, message: str, *args, **kwargs) -> None:
        self.log("debug", message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        self.log("warning", message, *args, **kwargs)

    warn = warning

    def error(self, message: str, *args, **kwargs) -> None:
        self.log("error", message, *args, **kwargs)

    err = error

    @property
    def app(self):
        return self

    def run(
        self,
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
        log_level='debug',
        app_import_string=None,
        **kwargs,
    ):
        from api.mods.server import run as run_builtin
        from api.mods.log import log as _log
        import logging as _logging

        if reload or workers != 1:
            _log.warning(
                "reload/workers options are not supported by the builtin server; "
                "running a single-process server without auto-reload."
            )

        lvl_map = {
            "debug": _logging.DEBUG,
            "info": _logging.INFO,
            "warning": _logging.WARNING,
            "error": _logging.ERROR,
            "critical": _logging.CRITICAL,
        }
        lvl = lvl_map.get(str(log_level).lower(), _logging.INFO)
        self._logger.setLevel(lvl)

        run_builtin(self, host=host, port=port)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def include_router(self, router: Router, prefix: Path = ""):
        from api.mods.helper import _make_handler

        prefix = prefix or ""
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix

        for r in router._routes:
            full_path = "".join([prefix, router.prefix, r.path]) or "/"

            if r.mids is not None:
                effective_mids = r.mids
            elif router.mids is not None:
                effective_mids = router.mids
            else:
                effective_mids = self.mids

            handler = _make_handler(r.func, r.method, mids=effective_mids)
            entry = _RouteEntry(
                method=r.method.upper(),
                path=full_path,
                handler=handler,
                name=r.name,
                mids=effective_mids,
            )
            self._routes.append(entry)

    def route(self, method: Str, path: Path, name: Maybe(Str) = None, mids=None):
        from api.mods.helper import _make_handler, _unwrap

        if not path.startswith("/"):
            path = "/" + path

        def decorator(func):
            effective_mids = self.mids if mids is None else mids
            handler = _make_handler(func, method, mids=effective_mids)
            route_name = name or _unwrap(func).__name__
            entry = _RouteEntry(
                method=method.upper(),
                path=path,
                handler=handler,
                name=route_name,
                mids=effective_mids,
            )
            self._routes.append(entry)
            return func

        return decorator

    def get(self, path: Path, name: Maybe(Str) = None, mids=None):
        return self.route("GET", path, name, mids)

    def post(self, path: Path, name: Maybe(Str) = None, mids=None):
        return self.route("POST", path, name, mids)

    def put(self, path: Path, name: Maybe(Str) = None, mids=None):
        return self.route("PUT", path, name, mids)

    def patch(self, path: Path, name: Maybe(Str) = None, mids=None):
        return self.route("PATCH", path, name, mids)

    def delete(self, path: Path, name: Maybe(Str) = None, mids=None):
        return self.route("DELETE", path, name, mids)
