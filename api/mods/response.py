from typed import model, Enum, Str, Int, List, Dict, Union, typed
from utils.types import Json, Nat


@model
class Response:
    status: Enum(Str, "success", "failure")
    code: Int
    data: Union(Str, List, Dict)


class response:
    @typed
    def success(data: Json={}, code: Nat=200) -> Response:
        return Response(status="success", code=code, data=data)

    @typed
    def failure(data: Json = {}, code: Nat = 400) -> Response:
        return Response(status="failure", code=code, data=data)
