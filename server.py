import os
import subprocess
import threading
import time
import webbrowser
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder=".")

# Minecraft server configuration - modify these as needed
MINECRAFT_JAR = "server.jar"  # Name of your server JAR file
SERVER_DIRECTORY = "."  # Directory where your server is located
MIN_RAM = "1G"
MAX_RAM = "4G"

# Server state variables
server_process = None
server_output = []
server_running = False

# Write simple HTML template for the dashboard
with open("index.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Minecraft Server Control Panel</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f0f0f0;
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .controls {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin: 20px 0;
        }
        button {
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            transition: background-color 0.3s;
        }
        #start-btn {
            background-color: #27ae60;
            color: white;
        }
        #stop-btn {
            background-color: #e74c3c;
            color: white;
        }
        #restart-btn {
            background-color: #f39c12;
            color: white;
        }
        #cmd-btn {
            background-color: #3498db;
            color: white;
        }
        button:hover {
            opacity: 0.8;
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .command-area {
            margin: 20px 0;
            display: flex;
            gap: 10px;
        }
        #command {
            flex: 1;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .console {
            background-color: #2c3e50;
            color: #ecf0f1;
            height: 400px;
            overflow-y: scroll;
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            white-space: pre-wrap;
        }
        .server-status {
            text-align: center;
            font-weight: bold;
            margin-bottom: 20px;
        }
        .online {
            color: #27ae60;
        }
        .offline {
            color: #e74c3c;
        }
    </style>
</head>
<body>
    <h1>Minecraft Server Control Panel</h1>
    
    <div class="server-status">
        Status: <span id="status" class="offline">OFFLINE</span>
    </div>
    
    <div class="controls">
        <button id="start-btn" onclick="startServer()">Start Server</button>
        <button id="stop-btn" onclick="stopServer()" disabled>Stop Server</button>
        <button id="restart-btn" onclick="restartServer()" disabled>Restart Server</button>
    </div>
    
    <div class="command-area">
        <input type="text" id="command" placeholder="Enter server command...">
        <button id="cmd-btn" onclick="sendCommand()" disabled>Send</button>
    </div>
    
    <div class="console" id="console"></div>
    
    <script>
        // Update console output regularly
        function updateConsole() {
            fetch('/console')
                .then(response => response.json())
                .then(data => {
                    const consoleElem = document.getElementById('console');
                    consoleElem.innerHTML = data.output.join('\\n');
                    consoleElem.scrollTop = consoleElem.scrollHeight;
                    
                    // Update status and buttons
                    const statusElem = document.getElementById('status');
                    const startBtn = document.getElementById('start-btn');
                    const stopBtn = document.getElementById('stop-btn');
                    const restartBtn = document.getElementById('restart-btn');
                    const cmdBtn = document.getElementById('cmd-btn');
                    const cmdInput = document.getElementById('command');
                    
                    if (data.running) {
                        statusElem.textContent = 'ONLINE';
                        statusElem.className = 'online';
                        startBtn.disabled = true;
                        stopBtn.disabled = false;
                        restartBtn.disabled = false;
                        cmdBtn.disabled = false;
                        cmdInput.disabled = false;
                    } else {
                        statusElem.textContent = 'OFFLINE';
                        statusElem.className = 'offline';
                        startBtn.disabled = false;
                        stopBtn.disabled = true;
                        restartBtn.disabled = true;
                        cmdBtn.disabled = true;
                        cmdInput.disabled = true;
                    }
                });
        }
        
        // Control server functions
        function startServer() {
            fetch('/start', { method: 'POST' });
        }
        
        function stopServer() {
            fetch('/stop', { method: 'POST' });
        }
        
        function restartServer() {
            fetch('/restart', { method: 'POST' });
        }
        
        function sendCommand() {
            const command = document.getElementById('command').value;
            fetch('/command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command: command }),
            });
            document.getElementById('command').value = '';
        }
        
        // Add Enter key support for command input
        document.getElementById('command').addEventListener('keyup', function(event) {
            if (event.key === 'Enter') {
                sendCommand();
            }
        });
        
        // Update console every second
        setInterval(updateConsole, 1000);
        updateConsole(); // Initial update
    </script>
</body>
</html>
    """)

def read_output(process):
    """Read and store the Minecraft server output in a separate thread"""
    global server_output
    while True:
        if process.poll() is not None:
            break
        line = process.stdout.readline().decode('utf-8', errors='replace')
        if line:
            server_output.append(line.rstrip())
            # Keep only the last 100 lines to prevent memory issues
            if len(server_output) > 100:
                server_output.pop(0)
    
    # When the process ends, update the status
    global server_running
    server_running = False

@app.route('/')
def index():
    """Serve the main control panel page"""
    return render_template('index.html')

@app.route('/console')
def console():
    """Return the current console output and server status"""
    global server_output, server_running
    return jsonify({'output': server_output, 'running': server_running})

@app.route('/start', methods=['POST'])
def start_server():
    """Start the Minecraft server"""
    global server_process, server_running, server_output
    
    if server_running:
        return jsonify({'status': 'already_running'})
    
    try:
        # Change directory to the server directory
        os.chdir(SERVER_DIRECTORY)
        
        # Start the server process
        cmd = ['java', f'-Xms{MIN_RAM}', f'-Xmx{MAX_RAM}', '-jar', MINECRAFT_JAR, 'nogui']
        server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=False
        )
        
        # Clear previous output
        server_output = []
        server_running = True
        
        # Start reading output in a separate thread
        output_thread = threading.Thread(target=read_output, args=(server_process,))
        output_thread.daemon = True
        output_thread.start()
        
        return jsonify({'status': 'started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop', methods=['POST'])
def stop_server():
    """Stop the Minecraft server"""
    global server_process, server_running
    
    if not server_running:
        return jsonify({'status': 'not_running'})
    
    try:
        # Send the stop command to the server
        server_process.stdin.write(b'stop\n')
        server_process.stdin.flush()
        
        # Wait up to 30 seconds for the server to stop
        for _ in range(30):
            if server_process.poll() is not None:
                break
            time.sleep(1)
        
        # Force kill if necessary
        if server_process.poll() is None:
            server_process.terminate()
            time.sleep(2)
            if server_process.poll() is None:
                server_process.kill()
        
        server_running = False
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/restart', methods=['POST'])
def restart_server():
    """Restart the Minecraft server"""
    stop_server()
    time.sleep(2)  # Wait for the server to fully stop
    return start_server()

@app.route('/command', methods=['POST'])
def send_command():
    """Send a command to the Minecraft server"""
    global server_process, server_running
    
    if not server_running:
        return jsonify({'status': 'not_running'})
    
    try:
        command = request.json.get('command', '')
        if command:
            server_process.stdin.write(f'{command}\n'.encode())
            server_process.stdin.flush()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    try:
        # Open web browser with the control panel
        webbrowser.open('http://localhost:5000')
        # Start the web server
        app.run(debug=False, host='localhost', port=5000)
    except KeyboardInterrupt:
        # If there's a running server when the panel is closed, stop it
        if server_running and server_process:
            try:
                server_process.stdin.write(b'stop\n')
                server_process.stdin.flush()
                time.sleep(5)
                if server_process.poll() is None:
                    server_process.terminate()
            except:
                pass
