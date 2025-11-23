import logging
import inspect
from typed import Any, Str

class Logger:
    def __init__(self, base_logger: Str = "uvicorn"):
        self._base_logger = base_logger

    def _caller_info(self):
        try:
            frame = inspect.stack()[2].frame
        except Exception:
            frame = None

        module_name = None
        router_name = None

        if frame is not None:
            from api.mods.helper import _get_router_class
            module_name = frame.f_globals.get("__name__", "__main__")
            R = _get_router_class()
            try:
                for v in frame.f_globals.values():
                    if isinstance(v, R):
                        router_name = getattr(v, "name", None)
                        if router_name:
                            break
            except Exception:
                router_name = None

        return module_name, router_name

    def _target_logger(self):
        from api.mods.helper import _api_name
        if _api_name:
            module_name, router_name = self._caller_info()
            if router_name:
                return logging.getLogger(f"[{_api_name}] [{router_name}]")
            if module_name:
                short = module_name.rsplit(".", 1)[-1]
                return logging.getLogger(f"[{_api_name}] [{short}]")
            return logging.getLogger(_api_name)
        return logging.getLogger(self._base_logger)

    def debug(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._target_logger().debug(message, *args, **kwargs)
        except Exception:
            pass

    def info(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._target_logger().info(message, *args, **kwargs)
        except Exception:
            pass

    def warning(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._target_logger().warning(message, *args, **kwargs)
        except Exception:
            pass

    warn = warning

    def error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._target_logger().error(message, *args, **kwargs)
        except Exception:
            pass

    err = error

    def critical(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._target_logger().critical(message, *args, **kwargs)
        except Exception:
            pass

log = Logger()
