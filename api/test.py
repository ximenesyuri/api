from typed import Str
from api import API, log, Router, Response

test = API(name="test")

router = Router()

@router.get("/test")
def aaa(x: Str) -> Response:
    log.debug("aaaaaaa")
    # You can return any JSON-serializable data as "data"
    return Response(
        status="success",
        code=200,
        data=x,
    )

test.include_router(router, prefix='/router')

if __name__ == "__main__":
    test.run(port=8080)
