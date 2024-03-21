import json
import os
import socket
import tempfile
import threading
import base64
from typing import Any, Dict

from .error import PepSocketError

# Initialize a threading lock
lock = threading.Lock()


def server_default_path() -> str:
    return os.path.join(tempfile.gettempdir(), "pep.socket")


def req(client_socket: socket.socket, data: Dict[str, Any]) -> Dict[str, Any]:
    with lock:
        # Send data until either all data has been sent or an error occurs.
        #
        # None is returned on success.
        # On error, an exception is raised,
        # and there is no way to determine how much data, if any, was successfully sent.
        try:
            client_socket.sendall(f"{json.dumps(data)}\n".encode("utf-8"))
        except Exception as e:
            raise PepSocketError(str(e))

        response = bytearray()

        while True:
            chunk = client_socket.recv(1024)

            # No more data, break the loop:
            if not chunk:
                break

            response.extend(chunk)

            # Check if the last byte is the delimiter:
            if response[-1:] == b"\n":
                break

        return json.loads(response[:-1].decode("utf-8"))


def diagnostics(
    client_socket: socket.socket,
    root_path: str,
) -> Dict[str, Any]:
    data = {
        "op": "v1/diagnostics",
        "root-path": root_path,
    }

    return req(client_socket, data)


def analyze_paths(
    client_socket: socket.socket,
    root_path: str,
) -> Dict[str, Any]:
    data = {
        "op": "v1/analyze_paths",
        "root-path": root_path,
    }

    return req(client_socket, data)


def analyze_text(
    client_socket: socket.socket,
    root_path: str,
    text: str,
    filename: str,
) -> Dict[str, Any]:
    text_bytes = text.encode()
    text_encoded = base64.b64encode(text_bytes).decode()

    data = {
        "op": "v1/analyze_text",
        "root-path": root_path,
        "text": text_encoded,
        "filename": filename,
    }

    return req(client_socket, data)


def namespace_definitions(
    client_socket: socket.socket,
    root_path: str,
) -> Dict[str, Any]:
    data = {
        "op": "v1/namespace_definitions",
        "root-path": root_path,
    }

    return req(client_socket, data)


def find_definitions(
    client_socket: socket.socket,
    root_path: str,
    filename: str,
    row: int,
    col: int,
) -> Dict[str, Any]:
    data = {
        "op": "v1/find_definitions",
        "root-path": root_path,
        "filename": filename,
        "row": row,
        "col": col,
    }

    return req(client_socket, data)
