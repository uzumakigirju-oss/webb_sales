import subprocess
import sys
import time
import json
import os
import signal
import urllib.request

PID_DIR = ".pids"

def ensure_pid_dir():
    os.makedirs(PID_DIR, exist_ok=True)

def write_pid(name: str, pid: int):
    with open(os.path.join(PID_DIR, f"{name}.pid"), "w") as f:
        f.write(str(pid))

def read_pid(name: str):
    path = os.path.join(PID_DIR, f"{name}.pid")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None

def kill_process(name: str):
    pid = read_pid(name)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Остановлен {name} (PID: {pid})")
        except OSError:
            pass
        try:
            os.remove(os.path.join(PID_DIR, f"{name}.pid"))
        except OSError:
            pass

def get_ngrok_url():
    try:
        req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            for tunnel in data['tunnels']:
                if tunnel['proto'] == 'https':
                    return tunnel['public_url']
    except Exception:
        pass
    return None

def kill_old_processes():
    print("🧹 Очистка зависших процессов...")
    for name in ["main", "web_app", "ngrok"]:
        kill_process(name)
    time.sleep(1)

def main():
    ensure_pid_dir()
    kill_old_processes()
    print("🚀 Запуск кассы, бота и ngrok...")

    bot_process = subprocess.Popen([sys.executable, "main.py"])
    write_pid("main", bot_process.pid)

    web_process = subprocess.Popen([sys.executable, "web_app.py"])
    write_pid("web_app", web_process.pid)

    ngrok_process = subprocess.Popen(["./ngrok", "http", "8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_pid("ngrok", ngrok_process.pid)

    time.sleep(3)

    url = get_ngrok_url()
    if url:
        with open(".current_url", "w") as f:
            f.write(url)
        print("\n" + "="*50)
        print(f"🌍 ВАША КАССА ДОСТУПНА ПО ССЫЛКЕ:")
        print(f"👉 {url} 👈")
        print("="*50 + "\n")
        print("Нажмите Ctrl+C чтобы остановить всё.\n")
    else:
        print("\n⚠️ Касса запущена, но получить ссылку ngrok не удалось.\n")

    try:
        bot_process.wait()
        web_process.wait()
        ngrok_process.wait()
    except KeyboardInterrupt:
        print("\nОстановка...")
        for name in ["main", "web_app", "ngrok"]:
            kill_process(name)

if __name__ == "__main__":
    main()
