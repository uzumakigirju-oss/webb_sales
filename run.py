import subprocess
import sys
import time
import re
import os
import signal

PID_DIR = ".pids"
CLOUDFLARED_PATH = os.path.expanduser("~/.local/bin/cloudflared")

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

def get_cloudflared_url(process, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        line = process.stderr.readline()
        if not line:
            continue
        line = line.decode("utf-8", errors="ignore").strip()
        if line:
            print(f"  cloudflared: {line}")
        m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if m:
            return m.group(0)
    return None

def kill_old_processes():
    print("🧹 Очистка зависших процессов...")
    for name in ["main", "web_app", "cloudflared", "ngrok"]:
        kill_process(name)
    time.sleep(1)

def main():
    ensure_pid_dir()
    kill_old_processes()
    print("🚀 Запуск кассы, бота и cloudflared...")

    bot_process = subprocess.Popen([sys.executable, "main.py"])
    write_pid("main", bot_process.pid)

    web_process = subprocess.Popen([sys.executable, "web_app.py"])
    write_pid("web_app", web_process.pid)

    time.sleep(2)

    cf_process = subprocess.Popen(
        [CLOUDFLARED_PATH, "tunnel", "--url", "http://localhost:8000", "--no-autoupdate"],
        stderr=subprocess.PIPE, stdout=subprocess.DEVNULL
    )
    write_pid("cloudflared", cf_process.pid)

    url = get_cloudflared_url(cf_process)
    if url:
        with open(".current_url", "w") as f:
            f.write(url)
        print("\n" + "=" * 50)
        print(f"🌍 ВАША КАССА ДОСТУПНА ПО ССЫЛКЕ:")
        print(f"👉 {url} 👈")
        print("=" * 50 + "\n")
        print("Нажмите Ctrl+C чтобы остановить всё.\n")
    else:
        print("\n⚠️ Касса запущена, но получить ссылку cloudflared не удалось.\n")
        print("Проверьте, что cloudflared установлен: ~/.local/bin/cloudflared\n")

    try:
        bot_process.wait()
        web_process.wait()
        cf_process.wait()
    except KeyboardInterrupt:
        print("\nОстановка...")
        for name in ["main", "web_app", "cloudflared", "ngrok"]:
            kill_process(name)

if __name__ == "__main__":
    main()
