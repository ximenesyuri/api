from api.mods.helper import _unwrap

class Router:
    def __init__(self, method=None, path="", func=None, name=None, mids=None, children=None):
        self.method = method.upper() if method else None

        if path:
            self.path = path if path.startswith("/") else f"/{path}"
        else:
            self.path = ""

        self.func = func

        if name is not None:
            self.name = name
        elif func is not None and method is not None:
            self.name = getattr(
                _unwrap(func),
                "__name__",
                f"{self.method}_{self.path}".replace("/", "_"),
            )
        else:
            self.name = None

        self.mids = mids

        self.children = list(children) if children is not None else []

    def include_router(self, route: "Router", prefix: str = ""):
        if prefix:
            if not prefix.startswith("/"):
                prefix = "/" + prefix

            group = Router(path=prefix)
            group.children.append(route)
            self.children.append(group)
        else:
            self.children.append(route)

        return route

    def route(self, method, path, name=None, mids=None):
        """
        Define a child route under this Route group.

        Example:
            users = Route(path="/users")

            @users.get("/")
            async def list_users(...):
                ...
        """
        if not path.startswith("/"):
            path = "/" + path

        def decorator(func):
            child = Router(
                method=method,
                path=path,
                func=func,
                name=name,
                mids=mids,
            )
            self.children.append(child)
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

