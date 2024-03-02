import json
import os
import socket
import tempfile
import threading


# Initialize a threading lock
lock = threading.Lock()


def default_path():
    return os.path.join(tempfile.gettempdir(), "pep.socket")


def send_message(client_socket, data):
    # Send data until either all data has been sent or an error occurs.
    #
    # None is returned on success.
    # On error, an exception is raised,
    # and there is no way to determine how much data, if any, was successfully sent.
    client_socket.sendall(json.dumps(data).encode("utf-8"))


def receive_message(client_socket):
    # Receive data from the socket.
    # The return value is a bytes object representing the data received.
    response = client_socket.recv(1024)

    return json.loads(response.decode("utf-8"))


def req(client_socket, data):
    with lock:
        send_message(client_socket, data)

        return receive_message(client_socket)


def diagnostics(client_socket, root_path):
    data = {
        "op": "diagnostics",
        "root-path": root_path,
    }

    return req(client_socket, data)


if __name__ == "__main__":
    # Create a socket object for Unix Domain Socket communication
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
        client_socket.connect(default_path())

        data = {"op": "foo"}

        response = req(client_socket, data)

        print(response)
