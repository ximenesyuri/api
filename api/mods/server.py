import asyncio
import traceback
from urllib.parse import urlsplit

_STATUS_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}

class BuiltinHTTPServer:
    def __init__(self, app, host="127.0.0.1", port=8000):
        self.app = app
        self.host = host
        self.port = port
        self._server = None

    async def _handle_client(self, reader, writer):
        try:
            try:
                header_data = await reader.readuntil(b"\r\n\r\n")
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                writer.close()
                await writer.wait_closed()
                return

            header_text = header_data.decode("iso-8859-1")
            lines = header_text.split("\r\n")
            if not lines or not lines[0]:
                await self._send_simple_response(
                    writer, 400, b"Bad Request: empty request line"
                )
                return

            request_line = lines[0]
            header_lines = lines[1:-2] if lines[-2:] == ["", ""] else lines[1:]

            try:
                method, target, http_version = request_line.split(" ", 2)
            except ValueError:
                await self._send_simple_response(
                    writer, 400, b"Bad Request: invalid request line"
                )
                return

            # ---- Parse path / query ----
            parsed_url = urlsplit(target)
            path = parsed_url.path or "/"
            raw_path = path.encode("ascii", "ignore")
            query_string = (parsed_url.query or "").encode("ascii", "ignore")

            # ---- Parse headers ----
            headers=[]
            headers_dict={}
            for line in header_lines:
                if not line:
                    continue
                if ":" not in line:
                    continue
                name, value = line.split(":", 1)
                name = name.strip()
                value = value.strip()
                headers.append(
                    (name.lower().encode("ascii", "ignore"),
                     value.encode("utf-8", "ignore"))
                )
                headers_dict[name.lower()] = value

            # ---- Read body (Content-Length only) ----
            body = b""
            if "content-length" in headers_dict:
                try:
                    length = int(headers_dict["content-length"])
                except ValueError:
                    await self._send_simple_response(
                        writer, 400, b"Bad Request: invalid Content-Length"
                    )
                    return
                if length > 0:
                    body = await reader.readexactly(length)

            # ---- Build ASGI scope ----
            client_addr = writer.get_extra_info("peername")
            server_addr = writer.get_extra_info("sockname")

            client_host, client_port = None, None
            if isinstance(client_addr, tuple):
                client_host, client_port = client_addr[0], client_addr[1]

            server_host, server_port = None, None
            if isinstance(server_addr, tuple):
                server_host, server_port = server_addr[0], server_addr[1]

            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": http_version.replace("HTTP/", ""),
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": raw_path,
                "query_string": query_string,
                "headers": headers,
                "client": (client_host, client_port),
                "server": (server_host, server_port),
            }

            request_body = body
            request_sent = False
            disconnected = False

            async def receive():
                nonlocal request_sent, disconnected
                if not request_sent:
                    request_sent = True
                    return {
                        "type": "http.request",
                        "body": request_body,
                        "more_body": False,
                    }
                if not disconnected:
                    disconnected = True
                    return {"type": "http.disconnect"}
                await asyncio.sleep(0)
                return {"type": "http.disconnect"}

            response_started = False
            response_ended = False

            async def send(message):
                nonlocal response_started, response_ended

                if response_ended:
                    return

                msg_type = message.get("type")

                if msg_type == "http.response.start":
                    if response_started:
                        raise RuntimeError("Response already started")

                    status = int(message["status"])
                    reason = _STATUS_REASONS.get(status, "Unknown")
                    status_line = f"HTTP/1.1 {status} {reason}\r\n"

                    msg_headers = message.get(
                        "headers", []
                    )

                    header_bytes = status_line.encode("ascii")
                    for name, value in msg_headers:
                        header_bytes += name + b": " + value + b"\r\n"

                    header_bytes += b"\r\n"
                    writer.write(header_bytes)
                    response_started = True

                elif msg_type == "http.response.body":
                    if not response_started:
                        await send(
                            {
                                "type": "http.response.start",
                                "status": 200,
                                "headers": [],
                            }
                        )

                    body = message.get("body", b"")
                    more_body = bool(message.get("more_body", False))

                    if body:
                        writer.write(body)

                    if not more_body:
                        await writer.drain()
                        response_ended = True
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception:
                            pass

            try:
                await self.app(scope, receive, send)
            except Exception:
                traceback.print_exc()
                if not writer.is_closing():
                    if not response_started:
                        await self._send_simple_response(
                            writer, 500, b"Internal Server Error"
                        )
                    else:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception:
                            pass

        except Exception:
            traceback.print_exc()
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send_simple_response(self, writer, status, body):
        reason = _STATUS_REASONS.get(status, "Unknown")
        status_line = f"HTTP/1.1 {status} {reason}\r\n"
        headers = (
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(status_line.encode("ascii") + headers.encode("ascii") + body)
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    async def serve_forever(self):
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        print(f"Serving on {addrs}")
        async with self._server:
            await self._server.serve_forever()


def run(app, host="127.0.0.1", port=8000):
    server = BuiltinHTTPServer(app, host=host, port=port)
    asyncio.run(server.serve_forever())
