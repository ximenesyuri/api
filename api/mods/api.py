import logging
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route as _Route
from starlette.exceptions import HTTPException as StarletteHTTPException
from typed import Str, Maybe, Bool, Path

class API:
    def __init__(self, name: Str="api", debug: Bool=False, mids=None):
        from api.mods.log import log
        try:
            self.name = name
            from api.mods.helper import _set_api_name
            _set_api_name(self.name or "api")
        except Exception:
            pass
        self.debug = debug
        self._starlette = Starlette(debug=debug)
        self.mids = mids

        self._logger = logging.getLogger(self.name or "api")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(levelname)s: %(asctime)s [%(name)s] %(message)s"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG if debug else logging.INFO)
        self._logger.propagate = True

        @self._starlette.exception_handler(TypeError)
        async def type_error_handler(request: Request, exc: TypeError):
            log.client_warning(
                f"Validation error (422) on {request.method} {request.url.path}: \n{exc}"
            )
            return JSONResponse({"detail": str(exc)}, status_code=422)

        @self._starlette.exception_handler(StarletteHTTPException)
        async def http_exc_handler(request: Request, exc: StarletteHTTPException):
            msg = f"HTTPException {exc.status_code}: {request.method} {request.url.path} -> {exc.detail}"
            if 400 <= exc.status_code < 500:
                log.warning(msg)
            else:
                log.error(msg)

            used_handler = getattr(request.state, "_used_ip_block_handler", False)
            if not used_handler and self.mids:
                try:
                    from api.mods.helper import _enforce_ip_block
                    _enforce_ip_block(request, self.mids, status_code=exc.status_code)
                except StarletteHTTPException as block_exc:
                    return JSONResponse(
                        {"detail": block_exc.detail},
                        status_code=block_exc.status_code,
                    )

            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
            )

        @self._starlette.exception_handler(Exception)
        async def unhandled_handler(request: Request, exc: Exception):
            log.error(f"Unhandled error on {request.method} {request.url.path}: {exc}")
            if self.debug:
                return PlainTextResponse(str(exc), status_code=500)
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    async def __call__(self, scope, receive, send):
        await self._starlette(scope, receive, send)

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
    def app(self) -> Starlette:
        return self._starlette

    def run(
        self,
        host = "127.0.0.1",
        port = 8000,
        reload = False,
        workers = 1,
        log_level = "debug",
        app_import_string = None,
        **uvicorn_kwargs,
    ):
        import uvicorn
        from api.mods.helper import _import_string

        if reload or workers > 1:
            if not app_import_string:
                app_import_string = _import_string(self)
            uvicorn.run(
                app_import_string,
                host=host,
                port=port,
                reload=reload,
                workers=workers,
                log_level=log_level,
                **uvicorn_kwargs,
            )
            return

        uvicorn.run(
            self._starlette,
            host=host,
            port=port,
            reload=False,
            workers=1,
            log_level=log_level,
            **uvicorn_kwargs,
        )

    def include_router(self, router, prefix: Path=""):
        from api.mods.helper import _make_handler
        prefix = prefix or ""
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix

        for r in router._routes:
            full_path = "".join([prefix, router.prefix, r.path]) or "/"
            effective_mids = None
            if r.mids is not None:
                effective_mids = r.mids
            elif router.mids is not None:
                effective_mids = router.mids
            else:
                effective_mids = self.mids

            handler = _make_handler(r.func, r.method, mids=effective_mids)
            route = _Route(full_path, handler, methods=[r.method], name=r.name)
            self._starlette.router.routes.append(route)

    def route(self, method: Str, path: Path, name: Maybe(Str)=None, mids=None):
        from api.mods.helper import _make_handler, _unwrap
        if not path.startswith("/"):
            path = "/" + path
        def decorator(func):
            effective_mids = self.mids if mids is None else mids
            handler = _make_handler(func, method, mids=effective_mids)
            route = _Route(path, handler, methods=[method.upper()], name=name or _unwrap(func).__name__)
            self._starlette.router.routes.append(route)
            return func
        return decorator

    def get(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("GET", path, name, mids)

    def post(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("POST", path, name, mids)

    def put(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("PUT", path, name, mids)

    def patch(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("PATCH", path, name, mids)

    def delete(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("DELETE", path, name, mids)

    def options(self, path: Path, name: Maybe(Str)=None, mids=None):
        return self.route("OPTIONS", path, name, mids)

    def head(self, path: Str, name: Maybe(Str)=None, mids=None):
        return self.route("HEAD", path, name, mids)
