import logging
import json
import inspect
from typing import get_type_hints
from typed import name as _name, Dict, Str, Union
from typed.models import MODEL, LAZY_MODEL
from typed.mods.helper.helper import _unwrap
from api.mods.helper import (
    _set_api_name,
    _enforce_ip_block,
    _enforce_token_auth,
    _enforce_rate_limit,
    Error,
    Request,
    _build_kwargs
)
from api.mods.log import log
from system import System
from system.mods.handler import HandlerInfo
from api.mods.router import Router
from api.mods.handler import Response, route, GET, POST, PUT, PATCH, DELETE

def _match_path_segments(template_segs, path_segs):
    """Match ('users', '{id}') against ('users', '123') -> params dict or None."""
    if len(template_segs) != len(path_segs):
        return None
    params = {}
    for t, p in zip(template_segs, path_segs):
        if t.startswith("{") and t.endswith("}"):
            params[t[1:-1]] = p
        elif t == p:
            continue
        else:
            return None
    return params

class API(System):
    def __init__(self, name="api", log_level='DEBUG', mids=None, desc=""):
        super().__init__(name=name, desc=desc or "")

        try:
            self.name = name
            _set_api_name(self.name or "api")
        except Exception:
            self.name = name or "api"

        self._log_level = log_level
        self.mids = mids

        from api.mods.log import _get_app_logger
        self._logger = _get_app_logger()
        log_levels = {
            'DEBUG':    logging.DEBUG,
            'INFO':     logging.INFO,
            'WARNING':  logging.WARNING,
            'ERROR':    logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        self._logger.setLevel(log_levels.get(log_level.upper(), logging.INFO))

        self._add_help_routes()

    def _find_matching_handler(self, method: str, path: str):
        """
        Find a HandlerInfo matching HTTP method + path.

        - method: 'GET', 'POST', ...
        - path:   '/users/123'
        """
        method = method.upper()
        path_segs = [s for s in path.strip("/").split("/") if s]

        for info in self._handlers.values():  # dict[path_tuple] -> HandlerInfo
            if not isinstance(info, HandlerInfo):
                continue

            kind = str(info.meta.get("kind", "")).lower()
            if kind not in ("route", "get", "post", "put", "patch", "delete"):
                continue

            if kind == "route":
                allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else:
                allowed_methods = {kind.upper()}

            if method not in allowed_methods:
                continue

            template_segs = list(info.path)
            params = _match_path_segments(template_segs, path_segs)
            if params is not None:
                return info, params

        raise Error(404, f"No route for {method} {path}")

    # ------------------------------------------------------------
    # Help endpoints (using System registry)
    # ------------------------------------------------------------
    def _add_help_routes(self):
        @self.GET("/help", name="help")
        def help_main(request: Request) -> Response:
            endpoints = []
            for info in self._handlers.values():
                if not isinstance(info, HandlerInfo):
                    continue
                path = "/" + "/".join(info.path) if info.path else "/"
                if path == "/help" or path.startswith("/help/"):
                    continue
                kind = str(info.meta.get("kind", "")).upper()
                method = kind if kind in ("GET", "POST", "PUT", "PATCH", "DELETE") else "GET"
                endpoints.append({
                    "method": method,
                    "path": path,
                    "name": info.name,
                })
            return Response(
                status="success",
                success=True,
                code=200,
                data=endpoints,
                message="Main helper endpoint. For help with specific endpoints, try '/help/<endpoint>'",
            )

        @self.GET("/help/{endpoint}", name="help_detail")
        def help_detail(request: Request, endpoint: Str) -> Response:
            requested_path = endpoint.strip()
            if not requested_path:
                raise Error(404, "No specific endpoint provided for help")

            target = None
            for info in self._handlers.values():
                if not isinstance(info, HandlerInfo):
                    continue
                path = "/" + "/".join(info.path) if info.path else "/"
                if path == "/help" or path.startswith("/help/"):
                    continue
                if path.rstrip("/") == f"/{requested_path.rstrip('/')}":
                    target = info
                    break
                if info.name == requested_path:
                    target = info
                    break

            if target is None:
                raise Error(404, f"No endpoint found matching '{requested_path}' for help")

            func_to_inspect = _unwrap(target.func)
            sig = inspect.signature(func_to_inspect)
            hints = get_type_hints(func_to_inspect)

            models = {}
            params_info = {}
            for name, p in sig.parameters.items():
                if name == "request":
                    continue

                param_info = {}
                hinted_type = hints.get(name)

                if hinted_type:
                    if hinted_type in Union(MODEL, LAZY_MODEL):
                        param_info["type"] = hinted_type.__name__
                        attrs = hinted_type.__json__.get("attrs")
                        attrs_repr = {}
                        for k, v in attrs.items():
                            if v in Dict:
                                new_v = {}
                                for k2, v2 in v.items():
                                    if k2 == "type":
                                        new_v.update({k2: _name(v2)})
                                    else:
                                        new_v.update({k2: v2})
                                attrs_repr[k] = new_v
                            else:
                                attrs_repr[k] = v
                        models[hinted_type.__name__] = attrs_repr
                    else:
                        param_info["type"] = _name(hinted_type)
                else:
                    param_info["type"] = "Any"

                if p.default is inspect.Parameter.empty:
                    param_info["required"] = True
                else:
                    param_info["required"] = False
                    param_info["default"] = p.default

                params_info[name] = param_info

            path = "/" + "/".join(target.path) if target.path else "/"
            route_help_info = {
                "method": str(target.meta.get("kind", "")).upper(),
                "path": path,
                "name": target.name,
                "mids": target.meta.get("mids"),
                "params": params_info,
                "desc": getattr(func_to_inspect, "__doc__", "No description provided"),
            }
            if models:
                route_help_info["models"] = models

            return Response(
                status="success",
                success=True,
                code=200,
                data=route_help_info,
                message=f"Detailed help for endpoint '{target.name}'",
            )

    async def __asgi__(self, scope, receive, send):
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
            info, route_params = self._find_matching_handler(method, path)
        except Error as e:
            log.warning(
                f"Error {e.status_code}: {method} {path_for_log} -> {e.detail}",
                router_name=client_ip,
            )
            resp_model = Response(
                status="failure",
                success=False,
                code=e.status_code,
                data=None,
                message=str(e.detail)
            )
            await self._send_response(send, resp_model)
            return

        request = Request(
            method=method,
            path=path,
            query_string=query_string,
            headers=headers,
            path_params=route_params,
            body=body,
            client=client,
        )

        path_is_help = ("/" + "/".join(info.path) if info.path else "/").startswith("/help")
        effective_mids = info.meta.get("mids") or self.mids

        try:
            if not path_is_help and effective_mids:
                _enforce_ip_block(request, effective_mids, status_code=None)
                _enforce_token_auth(request, effective_mids)
                _enforce_rate_limit(request, effective_mids)

            kw = await _build_kwargs(info.func, request)
            result = info.func(**kw)
            if inspect.isawaitable(result):
                result = await result

            resp_model = self._to_response_model(result)

        except Error as exc:
            msg = f"Error {exc.status_code}: {method} {path_for_log} -> {exc.detail}"
            log.client(msg, router_name=client_ip)
            client_log_done = True

            if effective_mids and not path_is_help:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=exc.status_code)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=block_exc.status_code,
                        data=None,
                        message=str(block_exc.detail),
                    )
                else:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=exc.status_code,
                        data=None,
                        message=str(exc.detail),
                    )
            else:
                resp_model = Response(
                    status="failure",
                    success=False,
                    code=exc.status_code,
                    data=None,
                    message=str(exc.detail),
                )

        except TypeError as exc:
            log.client(
                f"Error 422: {method} {path_for_log} -> {exc}",
                router_name=client_ip,
            )
            client_log_done = True

            if effective_mids and not path_is_help:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=422)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=block_exc.status_code,
                        data=None,
                        message=str(block_exc.detail),
                    )
                else:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=422,
                        data=None,
                        message=str(exc).strip(),
                    )
            else:
                resp_model = Response(
                    status="failure",
                    success=False,
                    code=422,
                    data=None,
                    message=str(exc),
                )

        except Exception as exc:
            log.error(
                f"Unhandled error on {method} {path_for_log}: {exc}",
                router_name=self.name,
            )
            detail = str(exc) if getattr(self, "_debug", False) else "Internal Server Error"
            log.client(
                f"Error 500: {method} {path_for_log} -> {detail}",
                router_name=client_ip,
            )
            client_log_done = True

            if effective_mids and not path_is_help:
                try:
                    _enforce_ip_block(request, effective_mids, status_code=500)
                except Error as block_exc:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=block_exc.status_code,
                        data=None,
                        message=str(block_exc.detail) if block_exc.detail else None,
                    )
                else:
                    resp_model = Response(
                        status="failure",
                        success=False,
                        code=500,
                        data=None,
                        message=detail,
                    )
            else:
                resp_model = Response(
                    status="failure",
                    success=False,
                    code=500,
                    data=None,
                    message=detail,
                )

        if not client_log_done and not path_is_help:
            code = resp_model.code
            if 200 <= code < 400:
                log.client(
                    f"OK {code}: {method} {path_for_log}",
                    router_name=client_ip,
                )
            else:
                message = resp_model.message or resp_model.data
                if isinstance(message, dict) and "detail" in message:
                    d = message["detail"]
                else:
                    d = str(message)
                log.client(
                    f"Error {code}: {method} {path_for_log} -> {d}",
                    router_name=client_ip,
                )

        await self._send_response(send, resp_model)

    def __call__(self, *args, **kwargs):
        if len(args) == 3 and not kwargs and isinstance(args[0], dict):
            scope = args[0]
            if scope.get("type") in {"http", "websocket", "lifespan"}:
                return self.__asgi__(*args)

        return System.__call__(self, *args, **kwargs)

    def _to_response_model(self, result):
        if isinstance(result, Response):
            return result

        if hasattr(result, "__json__"):
            data = getattr(result, "__json__")
            return Response(
                status="success",
                success=True,
                code=200,
                data=data
            )

        try:
            json.dumps(result)
            data = result
            return Response(
                status="success",
                success=True,
                code=200,
                data=data
            )
        except TypeError:
            if result in Str:
                return Response(
                    status="success",
                    success=True,
                    code=200,
                    message=result
                )

    async def _send_response(self, send, resp: Response) -> None:
        try:
            payload = getattr(resp, "__json__", None)
            if payload is None:
                payload = {
                    "status": resp.status,
                    "success": resp.success,
                    "code": resp.code,
                    "data": resp.data,
                    "message": resp.message,
                }
        except Exception:
            payload = {
                "status": getattr(resp, "status", "failure"),
                "code": getattr(resp, "code", 500),
                "data": getattr(resp, "data", {"detail": "Serialization error"}),
                "message": getattr(resp, "message", None),
            }

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body_bytes)).encode("ascii")),
        ]

        await send(
            {
                "type": "http.response.start",
                "status": resp.code,
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

    def run(
        self,
        host="127.0.0.1",
        port=8000,
        log_level='debug',
        app_import_string=None,
        **kwargs,
    ):
        from api.mods.server import run as run_builtin
        import logging as _logging

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

API.attach(handler=route,  name='route')
API.attach(handler=GET,    name='GET')
API.attach(handler=POST,   name='POST')
API.attach(handler=PUT,    name='PUT')
API.attach(handler=PATCH,  name='PATCH')
API.attach(handler=DELETE, name='DELETE')

API.allow(Router)

