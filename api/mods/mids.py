from typed import model, Enum, Str, Int, Bool, List
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

@model
class Cors(Mid):
    origins: List(Str) = ["*"]
    allow_credentials: Bool=False
    allow_methods: List(Str)=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers: List(Str)=["*"]
    expose_headers: List(Str)=[]

Mid.__display__   = "Mid"
Auth.__display__  = "Auth"
Block.__display__ = "Block"
Token.__display__ = "Token"
Limit.__display__ = "Limit"
Cors.__display__  = "Cors"
