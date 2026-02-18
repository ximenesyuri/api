from system import Component
from api.mods.handler import route, GET, POST, PUT, PATCH, DELETE

class Router(Component):
    def __init__(self, path="/", name="router", desc=""):
        super().__init__(name=name, desc=desc, prefix=path)

Router.attach(handler=route,  name="router")
Router.attach(handler=GET,    name="GET")
Router.attach(handler=POST,   name="POST")
Router.attach(handler=PUT,    name="PUT")
Router.attach(handler=PATCH,  name="PATCH")
Router.attach(handler=DELETE, name="DELETE")
