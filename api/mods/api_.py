import logging
import json
from typed import model, typed, List, Function, Maybe, Str, Union
from typed.models import MODEL, LAZY_MODEL
from utils.types import Path, Json
from api.mods.helper import (
    _set_api_name,
    _enforce_ip_block,
    _enforce_token_auth,
    _enforce_rate_limit,
    Error,
    Request,
)
from api.mods.response import Response
from api.mods.log import log
from api.mods.router import Router
import inspect
from typing import get_type_hints


@model
class _RouteEntry:
    method: Str
    path: Str
    handler: Function
    name: Str
    mids: Maybe(List)
    hint: Str


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
        self._add_help_routes()

    def _find_matching_route(self, method, path):
        """Find the right route handler for help paths."""
        for r in self._routes:
            params = _match_path(r.path, path)
            if params is not None and r.method == method.upper():
                return r
        return None

    def _add_help_routes(self):
        """Add help routes to the API."""
        async def _help_main(request):
            endpoints = []
            for route in self._routes:
                if route.path != "/help" and not route.path.startswith("/help/"):
                    endpoints.append({
                        "method": route.method,
                        "path": route.path,
                        "name": route.name
                    })
            return Response(
                status="success",
                code=200,
                data=endpoints,
                message="Main helper endpoint. For help with specific endpoints, try '/help/<endpoint>'"
            )
        main_entry = _RouteEntry(
            method="GET",
            path="/help",
            handler=_help_main,
            name="help",
            mids=None,
            hint="Show available API endpoints"
        )
        self._routes.append(main_entry)
        async def _help_specific(request):
            requested_path = request.path[len('/help/'):].strip()
            if not requested_path:
                raise Error(404, "No specific endpoint provided for help")
            found_route = None
            for route in self._routes:
                if (route.path != "/help" and
                    not route.path.startswith("/help/") and
                    (f"/help/{route.name}" == request.path or
                     route.path.rstrip('/') == f"/{requested_path.rstrip('/')}")):
                    found_route = route
                    break
            if not found_route:
                for route in self._routes:
                    if (route.path != "/help" and not route.path.startswith("/help/")):
                        route_parts = route.path.strip('/').split('/')
                        req_parts = requested_path.strip('/').split('/')
                        if (route_parts and req_parts and
                            (route_parts[0] == req_parts[0] or route.path == f"/{requested_path}")):
                            found_route = route
                            break
            if not found_route:
                raise Error(404, f"No endpoint found matching '{requested_path}' for help")
            handler = found_route.handler
            sig = inspect.signature(found_route.handler)
            hints = get_type_hints(found_route.handler)

            params_info = {}
            for name, p in sig.parameters.items():
                if name == 'request':
                    continue
                hinted_type = hints.get(name)
                if hinted_type:
                    type_str = getattr(hinted_type, '__name__', str(hinted_type))
                    if hasattr(hinted_type, '__annotations__'):
                        type_name = getattr(hinted_type, '__name__', 'TypedModel')
                        params_info[name] = {
                            'type': 'model',
                            'class': type_name,
                            'details': getattr(hinted_type, '__annotations__', {}),
                        }
                    else:
                        params_info[name] = {
                            'type': type_str,
                            'default': p.default if p.default is not inspect.Parameter.empty else None
                        }
                else:
                    params_info[name] = {
                        'type': 'Any',
                        'default': p.default if p.default is not inspect.Parameter.empty else None
                    }
            return_annotation = sig.return_annotation
            if hasattr(return_annotation, '__name__'):
                return_type = return_annotation.__name__
            else:
                return_type = str(return_annotation)
            route_help_info = {
                "method": found_route.method,
                "path": found_route.path,
                "name": found_route.name,
                "middlewares": [m.__class__.__name__ for m in found_route.mids] if found_route.mids else None,
                "parameters": params_info,
                "returns": return_type,
                "description": getattr(found_route.handler, '__doc__', "No description provided"),
            }
            return Response(
                status="success",
                code=200,
                data=route_help_info,
                message=f"Detailed help for endpoint '{found_route.name}'"
            )

        detail_entry = _RouteEntry(
            method="GET",
            path="/help/{endpoint}",
            handler=_help_specific,
            name="help_detail",
            mids=None,
            hint=f"Detailed help on given endpoint."
        )
        self._routes.append(detail_entry)

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

        if path == "/help":
            route = next((r for r in self._routes if r.path == "/help"), None)
            route_params = {}
        elif path.startswith("/help/"):
            route = next((r for r in self._routes if r.path == "/help/{endpoint}"), None)
            route_params = {"endpoint": path[6:]}
        else:
            try:
                route, route_params = self._match_route(method, path)
            except Error as e:
                log.warning(
                    f"Error {e.status_code}: {method} {path_for_log} -> {e.detail}",
                    router_name=client_ip,
                )
                resp_model = Response(
                    status="failure",
                    code=e.status_code,
                    data=e.detail if e.detail in Json else None,
                    message=e.detail if e.detail in Str else None
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

        effective_mids = route.mids if hasattr(route, 'mids') and route.path != "/help" and not route.path.startswith("/help/") else None

        if route.path == "/help" or route.path.startswith("/help/"):
            result = await route.handler(request)
            resp_model = self._to_response_model(result)
        else:
            try:
                if effective_mids:
                    _enforce_ip_block(request, effective_mids, status_code=None)
                    _enforce_token_auth(request, effective_mids)
                    _enforce_rate_limit(request, effective_mids)

                result = await route.handler(request)

                resp_model = self._to_response_model(result)

                if effective_mids:
                    try:
                        _enforce_ip_block(request, effective_mids, status_code=resp_model.code)
                    except Error as block_exc:
                        resp_model = Response(
                            status="failure",
                            code=block_exc.status_code,
                            data=block_exc.detail if block_exc.detail in Json else None,
                            message=block_exc.detail if block_exc.detail in Str else None,
                        )

            except Error as exc:
                msg = f"Error {exc.status_code}: {method} {path_for_log} -> {exc.detail}"
                log.client(msg, router_name=client_ip)
                client_log_done = True

                if effective_mids:
                    try:
                        _enforce_ip_block(request, effective_mids, status_code=exc.status_code)
                    except Error as block_exc:
                        resp_model = Response(
                            status="failure",
                            code=block_exc.status_code,
                            data=block_exc.detail if block_exc.detail in Json else None,
                            message=block_exc.detail if block_exc.detail in Str else None,
                        )
                    else:
                        resp_model = Response(
                            status="failure",
                            code=exc.status_code,
                            data=exc.detail if exc.detail in Json else None,
                            message=exc.detail if exc.detail in Str else None,
                        )
                else:
                    resp_model = Response(
                        status="failure",
                        code=exc.status_code,
                        data=exc.detail if exc.detail in Json else None,
                        message=exc.detail if exc.detail in Str else None,
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
                            data=block_exc.detail if block_exc.detail in Json else None,
                            message=block_exc.detail if block_exc.detail in Str else None,
                        )
                    else:
                        resp_model = Response(
                            status="failure",
                            code=422,
                            data=exc if exc in Json else None,
                            message=exc if exc in Str else None,
                        )
                else:
                    resp_model = Response(
                        status="failure",
                        code=422,
                        data=exc if exc in Json else None,
                        message=exc if exc in Str else None,
                    )

            except Exception as exc:
                log.error(
                    f"Unhandled error on {method} {path_for_log}: {exc}",
                    router_name=self.name,
                )
                detail = str(exc) if hasattr(self, '_debug') and self._debug else "Internal Server Error"
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
                            data=None,
                            message=block_exc.detail if block_exc.detail in Str else None,
                        )
                    else:
                        resp_model = Response(
                            status="failure",
                            code=500,
                            data=detail if detail in Json else None,
                            message=detail if detail in Str else None,
                        )
                else:
                    resp_model = Response(
                        status="failure",
                        code=500,
                        data=detail if detail in Json else None,
                        message=detail if detail in Str else None,
                    )

        if not client_log_done and route.path != "/help" and not route.path.startswith("/help/"):
            code = int(resp_model.code)
            if 200 <= code < 400:
                log.client(
                    f"OK {code}: {method} {path_for_log}",
                    router_name=client_ip,
                )
            else:
                # Look for message field in response first before falling back to data field
                message = resp_model.message or resp_model.data
                if isinstance(message, dict) and "detail" in message:
                    detail = message["detail"]
                else:
                    detail = str(message)
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
            if r.path == "/help" or r.path.startswith("/help/"):
                continue
            if r.method != method.upper():
                continue
            params = _match_path(r.path, path)
            if params is not None:
                return r, params
        raise Error(404, f"No route for {method} {path}")

    def _to_response_model(self, result):
        if isinstance(result, Response):
            if hasattr(result, 'message') and result.message is not None:
                return result
            return result

        if hasattr(result, "__json__"):
            data = getattr(result, "__json__")
            return Response(status="success", code=200, data=data)

        try:
            json.dumps(result)
            data = result
            return Response(status="success", code=200, data=data)
        except TypeError:
            if result in Str:
                return Response(status="success", code=200, message=result)

    async def _send_response(self, send, resp: Response) -> None:
        try:
            payload = getattr(resp, "__json__", None)
            if payload is None:
                payload = {
                    "status": resp.status,
                    "code": resp.code,
                    "data": resp.data,
                    "message": resp.message,
                } if hasattr(resp, 'message') else {
                    "status": resp.status,
                    "code": resp.code,
                    "data": resp.data,
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
    # App Properties
    # ------------------------------------------------------------------

    @property
    def app(self):
        return self

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

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def include_router(self, router, prefix: Path = ""):
        """
        Include either:
          - a traditional Router instance (with ._routes, .prefix, .mids), or
          - a Route instance (possibly with nested .children).
        """
        from api.mods.helper import _make_handler
        from api.mods.router import Route as RouteNode
        try:
            from api.mods.router import Router as RouterType
        except Exception:
            RouterType = type(None)

        prefix = prefix or ""
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix

        def walk_route(route_obj, parent_path="", inherited_mids=None):
            base_path = (parent_path or "") + (route_obj.path or "")

            route_level_mids = route_obj.mids if getattr(route_obj, "mids", None) is not None else inherited_mids

            if getattr(route_obj, "method", None) and getattr(route_obj, "func", None):
                method = route_obj.method.upper()
                full_path = base_path or "/"

                effective_mids = route_level_mids if route_level_mids is not None else self.mids

                handler = _make_handler(route_obj.func, method, mids=effective_mids)
                entry = _RouteEntry(
                    method=method,
                    path=full_path,
                    handler=handler,
                    name=route_obj.name,
                    mids=effective_mids,
                    hint=f"Route: {route_obj.func.__name__ if hasattr(route_obj, 'func') else str(route_obj)}",
                )
                self._routes.append(entry)

            for child in getattr(route_obj, "children", []) or []:
                walk_route(
                    child,
                    parent_path=base_path,
                    inherited_mids=route_level_mids,
                )

        if isinstance(router, RouterType):
            base_prefix = prefix + getattr(router, "prefix", "") or ""
            router_mids = getattr(router, "mids", None)

            for r in router._routes:
                walk_route(
                    r,
                    parent_path=base_prefix,
                    inherited_mids=router_mids,
                )
            return

        if isinstance(router, RouteNode):
            walk_route(
                router,
                parent_path=prefix,
                inherited_mids=router.mids,
            )
            return

        raise TypeError(f"Unsupported router type for include_router: {type(router)!r}") 

    def route(self, method: Str, path: Path, name: Maybe(Str) = None, mids=None):
        from api.mods.helper import _make_handler, _unwrap

        if not path.startswith("/"):
            path = "/" + path

        def decorator(func):
            effective_mids = self.mids if mids is None else mids
            typed_func = typed(func, lazy=False)
            if typed_func.cod is not Response:
                raise TypeError(
                    "..."
                )
            if method.upper() in ('POST', 'PUT', 'PATCH'):
                if len(typed_func.dom) != 1 or not typed_func.dom[0] in Union(MODEL, LAZY_MODEL):
                    raise TypeError(
                        "aaaaaa"
                    )

            handler = _make_handler(func, method, mids=effective_mids)
            route_name = name or _unwrap(func).__name__
            entry = _RouteEntry(
                method=method.upper(),
                path=path,
                handler=handler,
                name=route_name,
                mids=effective_mids,
                hint=f"Endpoint: {func.__name__}"
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

