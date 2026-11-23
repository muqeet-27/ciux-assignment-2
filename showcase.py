import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
VERSIONS = (
    ("V1", ROOT_DIR / "V1"),
    ("V2", ROOT_DIR / "v2"),
    ("V3", ROOT_DIR / "v3"),
    ("V4", ROOT_DIR / "V4"),
    ("V5", ROOT_DIR / "V5"),
)
HOST = "127.0.0.1"
PORT = 5000
APP_URL = f"http://{HOST}:{PORT}/"
STARTUP_TIMEOUT = 30


def get_python_executable(project_dir):
    for environment_name in (".venv", "venv", "env"):
        environment_python = (
            project_dir / environment_name / "Scripts" / "python.exe"
        )
        if environment_python.is_file():
            return str(environment_python)
    return sys.executable


def port_is_available():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        try:
            server_socket.bind((HOST, PORT))
        except OSError:
            return False
    return True


def server_is_ready():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.25):
            return True
    except OSError:
        return False


def stop_process(process):
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_version(name, project_dir):
    app_path = project_dir / "app.py"
    if not app_path.is_file():
        print(f"Cannot start {name}: {app_path} was not found.")
        return

    if not port_is_available():
        print(
            f"Cannot start {name}: port {PORT} is already in use. "
            "Stop the other Flask app and try again."
        )
        return

    python_executable = get_python_executable(project_dir)
    command = [python_executable, str(app_path)]
    print(f"\nStarting {name} with {python_executable}")
    print("The app's output will appear below. Press Ctrl+C to return to the menu.\n")

    try:
        process = subprocess.Popen(command, cwd=project_dir)
    except OSError as error:
        print(f"Could not start {name}: {error}")
        return

    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not server_is_ready():
            return_code = process.poll()
            if return_code is not None:
                print(f"{name} stopped during startup (exit code {return_code}).")
                return
            if time.monotonic() >= deadline:
                print(
                    f"{name} did not start listening on {APP_URL} within "
                    f"{STARTUP_TIMEOUT} seconds. Check the app output above."
                )
                process.wait()
                return
            time.sleep(0.2)

        print(f"{name} is running at {APP_URL}")
        try:
            browser_opened = webbrowser.open_new_tab(APP_URL)
        except (webbrowser.Error, OSError) as error:
            print(f"Could not open the browser: {error}")
            browser_opened = False
        if not browser_opened:
            print(f"Open this address in your browser: {APP_URL}")
        return_code = process.wait()
        if return_code:
            print(f"{name} stopped with exit code {return_code}.")
    except KeyboardInterrupt:
        print(f"\nStopping {name}...")
        stop_process(process)


def main():
    while True:
        print("\nShowcase launcher")
        for number, (name, _) in enumerate(VERSIONS, start=1):
            print(f"{number}. {name}")
        print("Q. Quit")

        try:
            choice = input("Select a version: ").strip().lower()
        except EOFError:
            print()
            return

        if choice in ("q", "quit"):
            return

        if not choice.isdigit() or not 1 <= int(choice) <= len(VERSIONS):
            print("Choose a number from 1 to 5, or Q to quit.")
            continue

        name, project_dir = VERSIONS[int(choice) - 1]
        run_version(name, project_dir)


if __name__ == "__main__":
    main()
