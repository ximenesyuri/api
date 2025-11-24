import logging
import inspect
from typed import Any, Str

ROUTER_COL_WIDTH = 11
BASE_LOGGER = "uvicorn"

class Formatter(logging.Formatter):
    LEVEL_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARN",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRIT",
    }

    def __init__(self, datefmt=None):
        super().__init__(datefmt=datefmt or "%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        level_word = self.LEVEL_MAP.get(record.levelno, record.levelname)
        level_field = (level_word + ":").ljust(7)
        dt = self.formatTime(record, self.datefmt)
        msg = record.getMessage()

        return f"{level_field} {dt} {msg}"

class Logger:
    def __init__(self, base_logger: Str=BASE_LOGGER):
        self._base_logger = base_logger

    def _caller_router_name(self):
        try:
            frame = inspect.stack()[3].frame
        except Exception:
            frame = None

        if frame is None:
            return None

        from api.mods.helper import _get_router_class
        R = _get_router_class()
        try:
            for v in frame.f_globals.values():
                if isinstance(v, R):
                    name = getattr(v, "name", None)
                    if name:
                        return name
        except Exception:
            return None
        return None

    def _log(
        self,
        level: int,
        message: Str,
        router_name=None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        try:
            from api.mods.helper import _build_logger, _build_prefix
            logger = _build_logger(BASE_LOGGER, Formatter())
            router = router_name or self._caller_router_name()
            prefix = _build_prefix(ROUTER_COL_WIDTH, router)
            logger.log(level, prefix + message, *args, **kwargs)
        except Exception:
            pass

    def debug(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: Str, *args, **kwargs):
        self._log(logging.WARNING, message, *args, **kwargs)

    warn = warning

    def error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, *args, **kwargs)

    err = error

    def critical(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, *args, **kwargs)

    def _client_warning(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, router_name="client-side", *args, **kwargs)

    def _client_error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, router_name="client-side", *args, **kwargs)


log = Logger()

