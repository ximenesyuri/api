from typed import model, Enum, Str, Int, Nat, List

AuthType = Enum(Str, 'token', 'basic')

@model
class Middleware:
    pass

@model
class Auth(Middleware):
    type: AuthType

@model
class Block(Middleware):
    codes: List(Nat)=[]
    attempts: Nat=3
    interval: Nat=30
    block_minutes: Int=-1
    message: Str

@model
class Token(Auth):
    type: AuthType = 'token'
    token: Str
