import os
import sys
import subprocess
import webbrowser
import rumps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "friday_env", "bin", "python")
PYTHON_EXECUTABLE = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable

class FridayMenuBarApp(rumps.App):
    def __init__(self):
        # Swapped to the lightning bolt for the active state
        super(FridayMenuBarApp, self).__init__("Friday", title="⚡ Friday")

        # Start the backend server silently in the background
        self.server_process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "friday_server.py"],
            cwd=BASE_DIR
        )

        self.status_toggle = rumps.MenuItem("System Active", callback=self.toggle_system)
        self.status_toggle.state = True 

        self.menu = [
            rumps.MenuItem("Open Interface", callback=self.open_ui),
            None,  
            self.status_toggle,
            None,  
            rumps.MenuItem("Restart Server", callback=self.restart_server),
        ]

    def toggle_system(self, sender):
        sender.state = not sender.state

        if sender.state:
            sender.title = "System Active"
            self.title = "⚡ Friday"
            if not self.server_process or self.server_process.poll() is not None:
                self.server_process = subprocess.Popen(
                    [PYTHON_EXECUTABLE, "friday_server.py"],
                    cwd=BASE_DIR
                )
            rumps.notification("Friday OS", "Status", "Friday is online.")
        else:
            sender.title = "System Paused"
            self.title = "💤 Friday" # Switches to sleep emoji when paused
            if self.server_process:
                self.server_process.terminate()
                self.server_process.wait()
            rumps.notification("Friday OS", "Status", "Friday is paused.")

    def open_ui(self, _):
        webbrowser.open("http://localhost:8000")

    def restart_server(self, _):
        if self.server_process:
            self.server_process.terminate()

        self.server_process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "friday_server.py"],
            cwd=BASE_DIR
        )

        self.status_toggle.state = True
        self.status_toggle.title = "System Active"
        self.title = "⚡ Friday"
        rumps.notification("Friday OS", "Server", "Backend server restarted.")

    def clean_up(self):
        if self.server_process:
            self.server_process.terminate()
            self.server_process.wait()

if __name__ == "__main__":
    app = FridayMenuBarApp()
    try:
        app.run()
    finally:
        app.clean_up()