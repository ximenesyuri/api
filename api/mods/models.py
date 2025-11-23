from typed import model, Enum, Str, Int, Nat

AuthType = Enum(Str, 'token', 'basic')
BlockReason = Enum(Str, 'auth')

@model
class Middleware:
    pass

@model
class Auth(Middleware):
    type: AuthType

@model
class Block(Middleware):
    reason: BlockReason='auth'
    attempts: Nat=3
    interval: Nat=30
    block_minutes: Int=-1
    message: Str

@model
class Token(Auth):
    type: AuthType = 'token'
    token: Str
