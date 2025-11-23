from typed import Function, Any, Str, Maybe, Path, List
from api.mods.helper import _unwrap
from api.mods.mids import Middleware

class Route:
    def __init__(self: Any, method: Str, path: Path, func: Function, name: Maybe(Str)=None, mids: List(Middleware)=None):
        self.method = method.upper()
        self.path = path if path.startswith("/") else f"/{path}"
        self.func = func
        self.name = name or getattr(_unwrap(func), "__name__", f"{self.method}_{self.path}".replace("/", "_"))
        self.mids = mids

class Router:
    def __init__(self, name: Str="router", prefix: Str="", mids: List(Middleware)=None) -> Any:
        self.name = name
        self.prefix = prefix or ""
        if self.prefix and not self.prefix.startswith("/"):
            self.prefix = "/" + self.prefix
        self._routes = []
        self.mids = mids

    def route(self: Any, method: Str, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None) -> Function:
        if not path.startswith("/"):
            path = "/" + path
        def decorator(func):
            self._routes.append(Route(method=method, path=path, func=func, name=name, mids=mids))
            return func
        return decorator

    def get(self: Any, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("GET", path, name, mids)

    def post(self, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("POST", path, name, mids)

    def put(self, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("PUT", path, name, mids)

    def patch(self, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("PATCH", path, name, mids)

    def delete(self, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("DELETE", path, name, mids)

    def options(self, path: Path, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("OPTIONS", path, name, mids)

    def head(self, path: Str, name: Maybe(Str)=None, mids: List(Middleware)=None):
        return self.route("HEAD", path, name, mids)
