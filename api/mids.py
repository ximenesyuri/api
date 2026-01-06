from utils.general import lazy

__mids__ = {
    "Token": "api.mods.mids",
    "Block": "api.mods.mids"
}

if lazy(__mids__):
    from api.mods.mids import Token, Block
