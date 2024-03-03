import json
import os
import socket
import tempfile
import threading
from typing import Any, Dict

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
        client_socket.sendall(json.dumps(data).encode("utf-8"))

        chunks = []

        while True:
            chunk = client_socket.recv(1024)

            # No more data, break the loop:
            if not chunk:
                break

            chunks.append(chunk)

            # Received less data than buffer size, assuming end of message:
            if len(chunk) < 1024:
                break

        # Combine all parts into one bytes object
        response_bytes = b"".join(chunks)

        return json.loads(response_bytes.decode("utf-8"))


def diagnostics(client_socket: socket.socket, root_path: str) -> Dict[str, Any]:
    data = {
        "op": "diagnostics",
        "root-path": root_path,
    }

    return req(client_socket, data)


if __name__ == "__main__":
    # Create a socket object for Unix Domain Socket communication
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
        client_socket.connect(server_default_path())

        data = {"op": "foo"}

        response = req(client_socket, data)

        print(response)
