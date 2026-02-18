from utils.general import lazy

__imports__ = {
    "API":      "api.mods.api_",
    "Router":   "api.mods.router",
    "log":      "api.mods.log",
    "Response": "api.mods.handler",
    "route":    "api.mods.handler"
}

if lazy(__imports__):
    from api.mods.api_ import API
    from api.mods.router import Router
    from api.mods.log import log
    from api.mods.handler import Response, route
