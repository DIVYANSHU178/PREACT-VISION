from flask_socketio import SocketIO, emit

class WebSocketManager:
    def __init__(self):
        self.socketio = None
        self.connected_clients = 0 # Optional: keep track of connected clients
        print("WebSocketManager initialized.")

    def init_app(self, app):
        """
        Initializes Flask-SocketIO with the Flask app.
        """
        self.socketio = SocketIO(app, cors_allowed_origins="http://127.0.0.1:5500", async_mode='threading')

        @self.socketio.on('connect')
        def handle_connect():
            self.connected_clients += 1
            print(f"Client connected. Total clients: {self.connected_clients}")
            emit('server_response', {'data': 'Connected to WebSocket'})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            self.connected_clients -= 1
            print(f"Client disconnected. Total clients: {self.connected_clients}")

        @self.socketio.on('message')
        def handle_message(msg):
            print(f"Received message: {msg}")
            emit('server_response', {'data': msg, 'status': 'received'})

    def broadcast(self, event_name, data={}):
        """
        Broadcasts a message to all connected WebSocket clients.
        :param event_name: The name of the event to emit.
        :param data: The data payload to send with the event.
        """
        if self.socketio:
            self.socketio.emit(event_name, data)
            # print(f"Broadcasted event '{event_name}' with data: {data}")
        else:
            print("SocketIO not initialized, cannot broadcast.")

# Instantiate the manager globally (or as needed)
sio_manager = WebSocketManager()
