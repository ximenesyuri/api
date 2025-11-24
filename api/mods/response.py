from datetime import datetime
from starlette.responses import JSONResponse as Response
from starlette.exceptions import HTTPException

from typed import typed, Nat, Str, Json

Response.__display__ = 'Response'

@typed
def Success(message: Str, code: Nat=200, data: Json={}) -> Response:
    content = {
        "status": "success",
        "code": code,
        "datetime": datetime.now().isoformat()
    }
    if message:
        content.update({'message': message})
    if data:
        content.update({'data': data})
    return Response(
        status_code=code,
        content=content
    )

@typed
def Failure(message: Str, code: Nat, data: Json={}) -> Response:
    content = {
        "status": "failure",
        "code": code,
        "datetime": datetime.now().isoformat()
    }
    if message:
        content.update({'message': message})
    if data:
        content.update({'data': data})
    return Response(
        status_code=code,
        content=content
    )

@typed
def Error(code: Nat, message: Str="") -> HTTPException:
    return HTTPException(status_code=code, detail=message)
