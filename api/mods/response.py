from typed import model, Dict, Str, typed, Maybe
from utils.types import Nat
from utils.general import message as _message
from system import Message, Status, Data

@model
class Response(Message):
    status: Status

class _propagate:
    @typed
    def success(msg: Message) -> Response:
        return Response(
            status="success",
            success=True,
            code=msg.code,
            data=msg.data,
            message=msg.message
        )
    @typed
    def failure(msg: Message) -> Response:
        return Response(
            status="failure",
            success=False,
            code=msg.code,
            data=msg.data,
            message=msg.message
        )

class response:
    @typed
    def success(
            code: Maybe(Nat)=None,
            message: Maybe(Str)=None,
            data: Maybe(Data)=None,
            **kwargs: Dict(Str)
        ) -> Response:
        return Response(
            status="success",
            success=True,
            code=code or 200,
            data=data,
            message=_message(message=message, **kwargs)
        )

    @typed
    def failure(
        code: Maybe(Nat)=500,
        message: Maybe(Str)=None,
        data: Maybe(Data)=None,
        **kwargs: Dict(Str)
    ) -> Response:
        return Response(
            status="failure",
            success=False,
            code=code or 500,
            data=data,
            message=_message(message=message, **kwargs)
        )

    propagate = _propagate
