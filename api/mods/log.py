import logging
import inspect
from typed import Str, Any

class log:
    def __init__(self, logger_name: Str = "uvicorn.error"):
        self._base_logger = logging.getLogger(logger_name)

    def _caller_prefix(self) -> str:
        try:
            frame = inspect.stack()[2].frame
            module_name = frame.f_globals.get("__name__", "__main__")
            return f"[{module_name}] "
        except Exception:
            return ""

    def debug(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._base_logger.debug(self._caller_prefix() + str(message), *args, **kwargs)
        except Exception:
            pass

    def info(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._base_logger.info(self._caller_prefix() + str(message), *args, **kwargs)
        except Exception:
            pass

    def warning(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._base_logger.warning(self._caller_prefix() + str(message), *args, **kwargs)
        except Exception:
            pass

    warn = warning

    def error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._base_logger.error(self._caller_prefix() + str(message), *args, **kwargs)
        except Exception:
            pass

    err = error

    def critical(self, message: Str, *args: Any, **kwargs: Any) -> None:
        try:
            self._base_logger.critical(self._caller_prefix() + str(message), *args, **kwargs)
        except Exception:
            pass

