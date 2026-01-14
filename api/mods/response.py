from typed import model, Enum, Str, typed, Maybe
from utils.types import Json, Nat


@model
class Response:
    status: Enum(Str, "success", "failure")
    code: Nat
    data: Maybe(Json)=None
    message: Maybe(Str)=None

class response:
    @typed
    def success(code: Nat=200, message: Maybe(Str)=None, data: Maybe(Json)=None) -> Response:
        return Response(status="success", message=message, code=code, data=data)

    @typed
    def failure(code: Nat=400, message: Maybe(Str)=None, data: Maybe(Json)=None) -> Response:
        return Response(status="failure", code=code, data=data)
