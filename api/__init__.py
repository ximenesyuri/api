from utils.general import lazy

__imports__ = {
    "API":      "api.mods.api_",
    "Router":   "api.mods.router",
    "log":      "api.mods.log",
    "Response": "api.mods.response",
    "response": "api.mods.response"
}

if lazy(__imports__):
    from api.mods.api_ import API
    from api.mods.router import Router
    from api.mods.log import log
    from api.mods.response import Response, response
