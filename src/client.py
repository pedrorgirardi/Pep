import socket
import json

# Define the path to the Unix socket
socket_path = "/tmp/pep.socket"

# Data to be sent
data = {"op": "hello"}

# Create a socket object for Unix Domain Socket communication
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
    # Connect to the server
    client_socket.connect(socket_path)
    
    # Send data encoded in JSON
    client_socket.sendall(json.dumps(data).encode('utf-8'))
    
    # Optionally, receive a response from the server
    response = client_socket.recv(1024)
    print("Received:", response.decode('utf-8'))
