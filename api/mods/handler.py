from typed import model, Maybe
from typed.models import value
from utils.types import Nat
from system import Message, Handler

@model
class Response(Message):
    code: Maybe(Nat)=(
        lambda:
            200 if value('status') == 'success' else
            500 if value('status') == 'failure' else
            None
        )

Response.__display__ = 'Response'

route  = Handler(Response, lazy=False, name="route")
GET    = Handler(Response, lazy=False, name="get")
POST   = Handler(Response, lazy=False, name="post")
PUT    = Handler(Response, lazy=False, name="put")
PATCH  = Handler(Response, lazy=False, name="patch")
DELETE = Handler(Response, lazy=False, name="delete")
