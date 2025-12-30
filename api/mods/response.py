from typed import model, Enum, Str, Int, List, Dict, Union, Nat, typed
from utils.types import Json


@model
class Response:
    """
    High-level API response model.

    This is the *logical* response returned by your endpoint functions.
    It will be serialized to JSON for HTTP responses by the framework.

    Fields:
        status: 'success' or 'failure'
        code:   integer status code (also used as HTTP status code)
        data:   payload (string, list, or dict)
    """
    status: Enum(Str, "success", "failure")
    code: Int
    data: Union(Str, List, Dict)


class response:
    """
    Convenience helpers to build Response models.
    """

    @typed
    def success(data: Json = {}, code: Nat = 200) -> Response:
        return Response(status="success", code=code, data=data)

    @typed
    def failure(data: Json = {}, code: Nat = 400) -> Response:
        return Response(status="failure", code=code, data=data)
