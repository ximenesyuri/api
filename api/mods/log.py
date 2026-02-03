import logging
import inspect
from utils.general import message as _message

ROUTER_COL_WIDTH = 11
LOGGER_NAME = "api"
CLIENT_LEVEL = logging.INFO + 1
logging.addLevelName(CLIENT_LEVEL, "CLIENT")

class Formatter(logging.Formatter):
    def __init__(self, datefmt=None):
        super().__init__(datefmt=datefmt or "%Y-%m-%d %H:%M:%S")

    def format(self, record):
        level_field = f"{record.levelname}:".ljust(8)
        dt = self.formatTime(record, self.datefmt)
        msg = record.getMessage()
        return f"{level_field} {dt} {msg}"


def _get_app_logger():
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(Formatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


def _truncate_router_name(name, maxlen):
    if len(name) <= maxlen:
        return name
    if maxlen <= 3:
        return name[:maxlen]
    return name[: maxlen - 3] + "..."


def _build_prefix(router_name=None):
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
    def __init__(self, base_logger=LOGGER_NAME):
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

    def _log(self, level, message, router_name=None, **kwargs):
        try:
            logger = _get_app_logger()
            router = router_name or self._caller_router_name()
            prefix = _build_prefix(router)
            message = _message(message=message, **kwargs)
            logger.log(level, prefix + message)
        except Exception:
            pass

    def debug(self, message, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    warn = warning

    def error(self, message, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    err = error

    def critical(self, message, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)

    def client(self, message, **kwargs):
        router_name = kwargs.pop("router_name", None)
        self._log(CLIENT_LEVEL, message, router_name=router_name, **kwargs)

log = Logger()
