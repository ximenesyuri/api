from typed import model, Enum, Str, Int, List
from utils.types import Nat

AuthType = Enum(Str, 'token', 'basic')

@model
class Mid:
    pass

@model
class Auth(Mid):
    type: AuthType

@model
class Block(Mid):
    codes: List(Nat)=[401, 404]
    attempts: Nat=3
    interval: Nat=30
    block_minutes: Int=-1
    message: Str="Blocked IP."

@model
class Token(Auth):
    type: AuthType='token'
    token: Str

@model
class Limit(Mid):
    limit: Nat=20
    block_minutes: Nat=5
    message: Str="Too many requests."
