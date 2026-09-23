import os
import sys
import time
import socket
import subprocess
import urllib.request
import ssl
import webbrowser
import rumps
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "friday_env", "bin", "python")
PYTHON_EXECUTABLE = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable

PORT = int(os.getenv("PORT", "3000"))
ENABLE_HTTPS = os.getenv("ENABLE_HTTPS", "true").lower() == "true"
PROTOCOL = "https" if ENABLE_HTTPS else "http"
UI_URL = f"{PROTOCOL}://127.0.0.1:{PORT}"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

class FridayMenuBarApp(rumps.App):
    def __init__(self):
        super(FridayMenuBarApp, self).__init__("Friday", title="⚡ Friday")

        self.log_file = open(os.path.join(BASE_DIR, "friday.log"), "a")
        self.server_process = None
        
        self.start_backend_process()

        self.status_toggle = rumps.MenuItem("System Active", callback=self.toggle_system)
        self.status_toggle.state = True 

        self.menu = [
            rumps.MenuItem("Open Interface", callback=self.open_ui),
            None,  
            self.status_toggle,
            None,  
            rumps.MenuItem("Restart Server", callback=self.restart_server),
        ]

    def start_backend_process(self):
        if is_port_in_use(PORT):
            rumps.notification("Friday OS", "Warning", f"Port {PORT} is already in use. Attempting to connect.")
            self.server_process = None
            return

        self.server_process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "friday_server.py"],
            cwd=BASE_DIR,
            stdout=self.log_file,
            stderr=self.log_file
        )

        # Verify backend actually started
        online = False
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        for _ in range(15):
            if self.server_process.poll() is not None:
                break
            try:
                req = urllib.request.Request(f"{UI_URL}/health")
                with urllib.request.urlopen(req, context=ctx, timeout=1) as resp:
                    if resp.status == 200:
                        online = True
                        break
            except Exception:
                time.sleep(0.5)

        if not online:
            rumps.notification("Friday OS", "Error", "Backend server failed health verification.")
        else:
            rumps.notification("Friday OS", "Status", "Friday is online.")

    def toggle_system(self, sender):
        sender.state = not sender.state

        if sender.state:
            sender.title = "System Active"
            self.title = "⚡ Friday"
            if not self.server_process or self.server_process.poll() is not None:
                if not is_port_in_use(PORT):
                    self.server_process = subprocess.Popen(
                        [PYTHON_EXECUTABLE, "friday_server.py"],
                        cwd=BASE_DIR,
                        stdout=self.log_file,
                        stderr=self.log_file
                    )
            rumps.notification("Friday OS", "Status", "Friday is online.")
        else:
            sender.title = "System Paused"
            self.title = "💤 Friday"
            if self.server_process:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                self.server_process = None
            rumps.notification("Friday OS", "Status", "Friday is paused.")

    def open_ui(self, _):
        webbrowser.open(UI_URL)

    def restart_server(self, _):
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

        self.start_backend_process()

        self.status_toggle.state = True
        self.status_toggle.title = "System Active"
        self.title = "⚡ Friday"

    def clean_up(self):
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass

if __name__ == "__main__":
    app = FridayMenuBarApp()
    try:
        app.run()
    finally:
        app.clean_up()