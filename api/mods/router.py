from api.mods.helper import _unwrap

class Route:
    def __init__(self, method, path, func, name=None, mids=None):
        self.method = method.upper()
        self.path = path if path.startswith("/") else f"/{path}"
        self.func = func
        self.name = name or getattr(_unwrap(func), "__name__", f"{self.method}_{self.path}".replace("/", "_"))
        self.mids = mids

class Router:
    def __init__(self, name="router", prefix="", mids=None):
        self.name = name
        self.prefix = prefix or ""
        if self.prefix and not self.prefix.startswith("/"):
            self.prefix = "/" + self.prefix
        self._routes = []
        self.mids = mids

    def route(self, method, path, name=None, mids=None):
        if not path.startswith("/"):
            path = "/" + path
        def decorator(func):
            self._routes.append(Route(method=method, path=path, func=func, name=name, mids=mids))
            return func
        return decorator

    def get(self, path, name=None, mids=None):
        return self.route("GET", path, name, mids)

    def post(self, path, name=None, mids=None):
        return self.route("POST", path, name, mids)

    def put(self, path, name=None, mids=None):
        return self.route("PUT", path, name, mids)

    def patch(self, path, name=None, mids=None):
        return self.route("PATCH", path, name, mids)

    def delete(self, path, name=None, mids=None):
        return self.route("DELETE", path, name, mids)

    def options(self, path, name=None, mids=None):
        return self.route("OPTIONS", path, name, mids)

    def head(self, path, name=None, mids=None):
        return self.route("HEAD", path, name, mids)
