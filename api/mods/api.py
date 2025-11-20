import logging
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route as _Route
from starlette.exceptions import HTTPException as StarletteHTTPException
from typed import Function, Str, Maybe, Bool, Path
from api.mods.router import Router
from api.mods.models import Auth

class API:
    def __init__(self, name: Str="api", debug: Bool=False, auth: Maybe(Auth)=None):
        self.name = name
        self.debug = debug
        self._starlette = Starlette(debug=debug)
        self.auth = auth

        self._logger = logging.getLogger(self.name or "api")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG if debug else logging.INFO)
        self._logger.propagate = False

        @self._starlette.exception_handler(StarletteHTTPException)
        async def http_exc_handler(request: Request, exc: StarletteHTTPException):
            if 400 <= exc.status_code < 500:
                self.warn("HTTPException %s: %s %s -> %s", exc.status_code, request.method, request.url.path, exc.detail)
            else:
                self.error("HTTPException %s: %s %s -> %s", exc.status_code, request.method, request.url.path, exc.detail)
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        @self._starlette.exception_handler(TypeError)
        async def type_error_handler(request: Request, exc: TypeError):
            self.warn("[client-side] Validation error (422) on %s %s: \n%s", request.method, request.url.path, exc)
            return JSONResponse({"detail": str(exc)}, status_code=422)

        @self._starlette.exception_handler(Exception)
        async def unhandled_handler(request: Request, exc: Exception):
            self._logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            if self.debug:
                return PlainTextResponse(str(exc), status_code=500)
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500) 

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

    async def __call__(self, scope, receive, send):
        await self._starlette(scope, receive, send)

    @property
    def app(self) -> Starlette:
        return self._starlette

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: bool = False,
        workers: int = 1,
        log_level: str = "info",
        app_import_string: str | None = None,
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

    def include_router(self, router: Router, prefix: Path=""):
        from api.mods.helper import _make_handler
        prefix = prefix or ""
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix

        for r in router._routes:
            full_path = "".join([prefix, router.prefix, r.path]) or "/"
            effective_auth = None
            if r.auth is False:
                effective_auth = None
            elif r.auth is not None:
                effective_auth = r.auth
            elif router.auth is not None:
                effective_auth = router.auth
            else:
                effective_auth = self.auth

            handler = _make_handler(r.func, r.method, auth=effective_auth)
            route = _Route(full_path, handler, methods=[r.method], name=r.name)
            self._starlette.router.routes.append(route)

    def route(self, method: Str, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        from api.mods.helper import _make_handler, _unwrap
        if not path.startswith("/"):
            path = "/" + path
        def decorator(func):
            effective_auth = self.auth if auth is None else (None if auth is False else auth)
            handler = _make_handler(func, method, auth=effective_auth)
            route = _Route(path, handler, methods=[method.upper()], name=name or _unwrap(func).__name__)
            self._starlette.router.routes.append(route)
            return func
        return decorator

    def get(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("GET", path, name, auth)

    def post(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("POST", path, name, auth)

    def put(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("PUT", path, name, auth)

    def patch(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("PATCH", path, name, auth)

    def delete(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("DELETE", path, name, auth)

    def options(self, path: Path, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("OPTIONS", path, name, auth)

    def head(self, path: Str, name: Maybe(Str)=None, auth: Maybe(Auth)=None):
        return self.route("HEAD", path, name, auth) 
