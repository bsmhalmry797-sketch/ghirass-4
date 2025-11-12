# app.py - Real-Time SocketIO Backend Server

from flask import Flask
from flask_cors import CORS 
from flask_socketio import SocketIO, emit
import threading, time
import eventlet 
import shared_data_ghirass

# ----------------- Configuration -----------------
app = Flask(__name__)
# Enable CORS for all origins and paths (essential for Render/Frontend integration)
CORS(app, resources={r"/*": {"origins": "*"}}) 

# Initialize SocketIO with eventlet for better concurrency
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') 

# --- Control variables for the background stream ---
thread = None
thread_lock = threading.Lock()

# ----------------- Root Route for Status Check -----------------
@app.route('/')
def index():
    """Returns a simple message to confirm the server is running."""
    # This addresses the "Page Not Found" error when navigating to the base URL
    return "<h1>Socket.IO Backend is Running!</h1><p>Connect using a Socket.IO client on event 'realtime_update'.</p>"


# ----------------- Background Data Stream Function -----------------
def background_data_stream():
    """This thread constantly reads shared_data and broadcasts it."""
    while True:
        # Read the latest data from the shared memory file
        data_to_send = shared_data.latest_status
        
        # Emit data to all connected clients using the 'realtime_update' event
        socketio.emit('realtime_update', data_to_send)
        
        # Wait for 1 second before sending the next update
        socketio.sleep(1) 

# ----------------- SocketIO Event Handlers -----------------
@socketio.on('connect')
def handle_connect():
    """Triggered when a new client (browser) connects."""
    print('Client connected. Checking data stream status.')
    
    global thread
    with thread_lock:
        if thread is None:
            # Start the background data pusher thread if it's not running
            thread = socketio.start_background_task(target=background_data_stream)
            print("Real-Time Data Stream thread started.")
            
    emit('connection_status', {'data': 'Successfully connected to Real-Time API'})

@socketio.on('disconnect')
def handle_disconnect():
    """Triggered when a client disconnects."""
    print('Client disconnected.')

# ----------------- Server Execution -----------------
if __name__ == '__main__':
    # Use socketio.run for WebSockets compatibility and run on 0.0.0.0 for external access
    print("Starting Socket.IO Server on port 8000...")
    socketio.run(app, host='0.0.0.0', port=8000)
