import logging
import inspect
from typed import Any, Str

ROUTER_COL_WIDTH = 11
LOGGER_NAME = "api"

class Formatter(logging.Formatter):
    LEVEL_MAP = {
        logging.DEBUG: "DEB",
        logging.INFO: "INF",
        logging.WARNING: "WRN",
        logging.ERROR: "ERR",
        logging.CRITICAL: "CRT",
    }

    def __init__(self, datefmt: str | None = None):
        super().__init__(datefmt=datefmt or "%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        level_word = self.LEVEL_MAP.get(record.levelno, record.levelname)
        level_field = (level_word + ":").ljust(7)

        dt = self.formatTime(record, self.datefmt)
        msg = record.getMessage()
        return f"{level_field} {dt} {msg}"

def _get_app_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(Formatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger

def _truncate_router_name(name: Str, maxlen: int) -> Str:
    if len(name) <= maxlen:
        return name
    if maxlen <= 3:
        return name[:maxlen]
    return name[: maxlen - 3] + "..."

def _build_prefix(router_name: Str | None = None) -> Str:
    from api.mods.helper import _api_name

    api_name = _api_name or "api"
    api_part = f"[{api_name}]"
    label = router_name or ""
    if label:
        label = _truncate_router_name(label, ROUTER_COL_WIDTH)
        router_bracket = f"[{label}]"
    else:
        router_bracket = "[]"

    target_width = ROUTER_COL_WIDTH + 2
    spaces_after = max(0, target_width - len(router_bracket))
    router_part = f"{router_bracket}{' ' * spaces_after}"
    return f"{api_part} {router_part} "

class Logger:
    def __init__(self, base_logger: Str = LOGGER_NAME):
        self._base_logger = base_logger

    def _caller_router_name(self) -> Str | None:
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
        router_name: Str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        try:
            logger = _get_app_logger()
            router = router_name or self._caller_router_name()
            prefix = _build_prefix(router)
            logger.log(level, prefix + message, *args, **kwargs)
        except Exception:
            pass

    def debug(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, *args, **kwargs)

    warn = warning

    def error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, *args, **kwargs)

    err = error

    def critical(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, *args, **kwargs)

    def client_warning(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, router_name="client-side", *args, **kwargs)

    def client_error(self, message: Str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, router_name="client-side", *args, **kwargs)

log = Logger()

