import logging
import inspect
from typed import Any, Str

ROUTER_COL_WIDTH = 11
LOGGER_NAME = "api"
CLIENT_LEVEL = logging.INFO + 1
logging.addLevelName(CLIENT_LEVEL, "CLIENT")


class Formatter(logging.Formatter):
    """
    Formatter that aligns the log level column so that the timestamp
    starts at the same position for all levels.

    Example:
        WARNING: 2025-12-30 14:42:02,515 ...
        DEBUG:   2025-12-30 14:42:08,380 ...
    """

    def __init__(self, datefmt: str | None = None):
        super().__init__(datefmt=datefmt or "%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        level_field = f"{record.levelname}:".ljust(8)
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

    def client(self, message: Str, *args: Any, **kwargs: Any) -> None:
        router_name = kwargs.pop("router_name", None)
        self._log(CLIENT_LEVEL, message, router_name=router_name, *args, **kwargs)

log = Logger()

