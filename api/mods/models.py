from typed import model, Enum, Str

AuthType = Enum(Str, 'token', 'basic')

@model
class Middleware:
    pass

@model
class Auth(Middleware):
    type: AuthType

@model
class Token(Auth):
    type: AuthType = 'token'
    token: Str
