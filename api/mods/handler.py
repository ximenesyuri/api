from typed import model, Maybe
from typed.models import value
from utils.types import Nat
from system import Message, Handler
from api.mods.log import log

@model
class Response(Message):
    code: Maybe(Nat)=(
        lambda:
            200 if value('status') == 'success' else
            500 if value('status') == 'failure' else
            None
        )

Response.__display__ = 'Response'

route  = Handler(Response, lazy=False, name="route",  logger=log)
GET    = Handler(Response, lazy=False, name="GET",    logger=log)
POST   = Handler(Response, lazy=False, name="POST",   logger=log)
PUT    = Handler(Response, lazy=False, name="PUT",    logger=log)
PATCH  = Handler(Response, lazy=False, name="PATCH",  logger=log)
DELETE = Handler(Response, lazy=False, name="DELETE", logger=log)
