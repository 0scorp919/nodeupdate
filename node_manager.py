# -*- coding: utf-8 -*-
"""
Node.js Portable Manager (v1.4)
Author: Oleksii Rovnianskyi / Autonomous Capsule

CHANGELOG:
    v1.4 — Підготовка до публікації на GitHub (стандарт capsule_manager):
           - CAPSULE_ROOT auto-detect від SCRIPT_DIR (замінено хардкод USER_ROOT)
           - __version__ = "1.4" + get_manager_hash() — SHA256 self-check цілісності
           - hashlib додано до stdlib imports
           - _rotate_log_if_needed() — якщо активний лог > 50 MB → _part2, _part3...
           - cleanup_old_logs() — видалення за датою (7 днів), захист поточного дня (today_str)
           - ensure_in_system_path() — перевірка через CAPSULE_ROOT (не хардкод)
           - Додано: node_launcher.bat, .gitignore, .env.example
    v1.3 — Прибрано резервне копіювання (Node = CLI-інструмент без даних користувача):
           - Видалено: backup_node(), cleanup_old_backups(), load_password()
           - Видалено: весь Vaultwarden-стек
           - Порядок main(): PATH → logs → verify → update_pkgs → update_node → launch
           - Обґрунтування: бінарники відновлюються з GitHub, node_modules — через npm install -g
    v1.2 — Оновлення глобальних npm-пакетів при кожному запуску:
           - update_global_packages() — завжди виконується після verify_node_tools()
           - npm outdated -g --json → список застарілих пакетів
           - npm update -g → оновлення всіх глобальних пакетів
    v1.1 — Vaultwarden-стек + резервне копіювання apps/node/ (AES-256).
    v1.0 — Початкова версія.
"""
import os
import sys
import hashlib
import subprocess
import time
import datetime
import logging
import glob
import shutil
import re
import zipfile
import json

# ===========================================================================
# VERSION
# ===========================================================================
__version__ = "1.4"

def get_manager_hash() -> str:
    """Return first 12 chars of SHA256 of this script (self-integrity check).
    UA: Перші 12 символів SHA256 власного файлу (self-check цілісності)."""
    try:
        with open(os.path.abspath(__file__), 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except Exception:
        return "????????????"

# ===========================================================================
# AUTO-DETECT CAPSULE ROOT — НЕ хардкодити шляхи!
# UA: SCRIPT_DIR → два рівні вгору → корінь капсули
# Структура: CAPSULE_ROOT/devops/nodeupdate/node_manager.py
# ===========================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CAPSULE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# --- КОНФІГУРАЦІЯ ---
NODE_DIR      = os.path.join(CAPSULE_ROOT, "apps", "node")
NODE_EXE      = os.path.join(NODE_DIR, "node.exe")
NPM_CMD       = os.path.join(NODE_DIR, "npm.cmd")
NPX_CMD       = os.path.join(NODE_DIR, "npx.cmd")
LOG_DIR       = os.path.join(CAPSULE_ROOT, "logs", "nodelog")
DOWNLOADS_DIR = os.path.join(CAPSULE_ROOT, "downloads")
PWSH_EXE      = os.path.join(CAPSULE_ROOT, "apps", "pwsh", "pwsh.exe")
GITHUB_REPO   = "nodejs/node"

PRESERVE_PATHS = ["node_modules"]

START_TIME = time.time()

os.system('')
class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN  = '\033[92m'; YELLOW= '\033[93m'; RED  = '\033[91m'
    RESET  = '\033[0m';  BOLD  = '\033[1m'

def cprint(msg: str, color: str = Colors.RESET, end: str = "\n") -> None:
    sys.stdout.write(color + msg + Colors.RESET + end)
    sys.stdout.flush()

def ensure_dependencies() -> None:
    required = {"requests": "requests", "packaging": "packaging"}
    missing = []
    for imp, pkg in required.items():
        try: __import__(imp)
        except ImportError: missing.append(pkg)
    if missing:
        cprint(f"[SETUP] Встановлення залежностей: {', '.join(missing)}...", Colors.YELLOW)
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

ensure_dependencies()
from packaging import version  # type: ignore
import requests                # type: ignore

def _rotate_log_if_needed() -> str:
    """If today's log > 50 MB → rename to _part2, _part3... Return active log path.
    UA: Якщо поточний лог > 50 МБ → перейменувати з суфіксом _part2, _part3...
        Повертає шлях до активного лог-файлу. Поточний день ніколи не видаляється."""
    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    base = os.path.join(LOG_DIR, f"node_log_{today}.log")
    if not os.path.exists(base):
        return base
    size_mb = os.path.getsize(base) / (1024 * 1024)
    if size_mb <= 50:
        return base
    part = 2
    while os.path.exists(os.path.join(LOG_DIR, f"node_log_{today}_part{part}.log")):
        part += 1
    new_path = os.path.join(LOG_DIR, f"node_log_{today}_part{part}.log")
    os.rename(base, new_path)
    return base


_log_path = _rotate_log_if_needed()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.FileHandler(_log_path, encoding='utf-8')])

def log(msg: str, color: str = Colors.RESET, console: bool = True) -> None:
    logging.info(msg)
    if console: cprint(msg, color)

def draw_progress(label: str, percent: int, width: int = 20) -> None:
    bars = int(percent / (100 / width))
    bar = '=' * bars + '.' * (width - bars)
    sys.stdout.write(f"\r{Colors.YELLOW}{label}: [{bar}] {percent}%{Colors.RESET}")
    sys.stdout.flush()

# --- УТИЛІТИ ---

def cleanup_old_logs(max_days: int = 7) -> None:
    """Delete log files older than max_days. NEVER delete current day files.
    UA: Видаляє лог-файли старші за max_days днів. Поточний день НЕ видаляється."""
    log("🧹 Перевірка старих логів...", Colors.CYAN)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    deleted = 0
    for f in glob.glob(os.path.join(LOG_DIR, "node_log_*.log")):
        fname = os.path.basename(f)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        if not match:
            continue
        file_date = match.group(1)
        if file_date == today_str:
            continue  # поточний день — ніколи не видаляємо
        try:
            file_dt = datetime.datetime.strptime(file_date, "%Y-%m-%d").date()
            cutoff = datetime.date.today() - datetime.timedelta(days=max_days)
            if file_dt < cutoff:
                os.remove(f)
                deleted += 1
                log(f"   🗑️ Видалено лог: {fname}", Colors.YELLOW)
        except Exception:
            pass
    if deleted:
        log(f"✅ Очищено старих логів: {deleted}", Colors.GREEN)
    else:
        log("✨ Старих логів немає.", Colors.GREEN)


def ensure_in_system_path() -> None:
    """Check if apps/node is in system PATH; run fix_path.ps1 via UAC if not.
    UA: Перевіряє наявність apps/node у системному PATH."""
    cprint("-" * 50, Colors.BLUE)
    log("🔧 ПЕРЕВІРКА СИСТЕМНОГО PATH", Colors.HEADER)
    ps_script = os.path.join(CAPSULE_ROOT, "devops", "pathupdate", "fix_path.ps1")
    if not os.path.exists(ps_script):
        log("   ⚠️ fix_path.ps1 не знайдено, пропускаємо.", Colors.YELLOW); return
    try:
        import winreg  # type: ignore[import]
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                             0, winreg.KEY_READ)
        current_path, _ = winreg.QueryValueEx(key, "Path"); winreg.CloseKey(key)
        entries = {e.rstrip("\\").strip().lower() for e in current_path.split(";") if e.strip()}
        if NODE_DIR.rstrip("\\").lower() in entries:
            log("   ✅ Capsule PATH вже зареєстровано.", Colors.GREEN); return
    except Exception: pass
    log("   ℹ️  apps/node відсутній у PATH. Запускаю реєстрацію (UAC)...", Colors.YELLOW)
    pwsh = PWSH_EXE if os.path.exists(PWSH_EXE) else "pwsh"
    try:
        subprocess.run([pwsh, "-NoProfile", "-Command",
                        f"Start-Process '{pwsh}' -Verb RunAs -Wait "
                        f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script}\" -AutoClose'"],
                       timeout=60)
        log("   ✅ PATH оновлено. Перезапусти термінал для застосування.", Colors.GREEN)
    except Exception as e:
        log(f"   ⚠️ Не вдалося оновити PATH: {e}", Colors.YELLOW)
        log(f"   ℹ️  Запусти вручну: {ps_script}", Colors.CYAN)


# --- NODE.JS ФУНКЦІОНАЛ ---

def get_installed_version() -> str:
    """Read installed Node.js version. UA: Зчитує встановлену версію Node.js."""
    if not os.path.exists(NODE_EXE): return "0.0.0"
    try:
        r = subprocess.run([NODE_EXE, "--version"], capture_output=True, text=True, timeout=10)
        m = re.search(r"v?(\d+\.\d+\.\d+)", r.stdout.strip())
        if m: return m.group(1)
    except Exception: pass
    return "0.0.0"


def get_npm_version() -> str:
    """Read installed npm version. UA: Зчитує версію npm."""
    if not os.path.exists(NPM_CMD): return "unknown"
    try:
        r = subprocess.run([NPM_CMD, "--version"], capture_output=True, text=True, timeout=10,
                           env={**os.environ, "PATH": NODE_DIR + ";" + os.environ.get("PATH", "")})
        return r.stdout.strip()
    except Exception: return "unknown"


def get_latest_lts_release() -> tuple[str, str]:
    """Fetch latest Node.js LTS release from GitHub API.
    UA: Отримує останній LTS-реліз Node.js через GitHub API."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Node-Manager/1.3"}
    resp = requests.get(api_url, headers=headers, params={"per_page": 30}, timeout=15)
    resp.raise_for_status()
    for release in resp.json():
        tag = release.get("tag_name", "")
        if release.get("prerelease") or release.get("draft"): continue
        m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
        if not m: continue
        if int(m.group(1)) % 2 != 0: continue
        ver_str = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        asset_name = f"node-v{ver_str}-win-x64.zip"
        for asset in release.get("assets", []):
            if asset["name"] == asset_name:
                return ver_str, asset["browser_download_url"]
        return ver_str, f"https://nodejs.org/dist/v{ver_str}/{asset_name}"
    raise RuntimeError("Не знайдено жодного LTS-релізу Node.js у GitHub API")


def _preserve_user_data(tmp_dir: str) -> dict[str, str]:
    saved: dict[str, str] = {}
    for rel in PRESERVE_PATHS:
        src = os.path.join(NODE_DIR, rel)
        if not os.path.exists(src): continue
        dst = os.path.join(tmp_dir, "_preserve", rel)
        os.makedirs(os.path.dirname(dst) if os.path.dirname(dst) else dst, exist_ok=True)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else: shutil.copy2(src, dst)
        saved[rel] = dst
        log(f"   💾 Збережено: {rel}", Colors.CYAN)
    return saved


def _restore_user_data(saved: dict[str, str]) -> None:
    for rel, src in saved.items():
        dst = os.path.join(NODE_DIR, rel)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        log(f"   ✅ Відновлено: {rel}", Colors.GREEN)


def update_node(download_url: str, ver_str: str) -> bool:
    """Download node-v{ver}-win-x64.zip, extract, preserve user data.
    UA: Завантажує zip, розпаковує, зберігає дані користувача."""
    asset_name = f"node-v{ver_str}-win-x64.zip"
    zip_path   = os.path.join(DOWNLOADS_DIR, asset_name)
    tmp_dir    = os.path.join(DOWNLOADS_DIR, f"node_tmp_{ver_str}")
    log(f"⬇️  Завантаження {asset_name}...", Colors.BLUE)
    try:
        with requests.get(download_url, stream=True, headers={"User-Agent": "Node-Manager/1.3"},
                          timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0)); downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk); downloaded += len(chunk)
                    if total: draw_progress("Завантаження", int(downloaded * 100 / total))
        print()
    except Exception as e:
        log(f"   ❌ Помилка завантаження: {e}", Colors.RED); return False
    log("💾 Збереження даних користувача (node_modules)...", Colors.CYAN)
    os.makedirs(tmp_dir, exist_ok=True)
    saved = _preserve_user_data(tmp_dir)
    log("📦 Розпакування Node.js...", Colors.CYAN)
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        prefix = f"node-v{ver_str}-win-x64/"
        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.namelist():
                if not member.startswith(prefix): continue
                rel_path = member[len(prefix):]
                if not rel_path: continue
                target = os.path.join(extract_dir, rel_path)
                if member.endswith("/"): os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    except Exception as e:
        log(f"   ❌ Помилка розпакування: {e}", Colors.RED); return False
    log("🔄 Копіювання файлів у apps/node/...", Colors.CYAN)
    preserve_set = {p.lower() for p in PRESERVE_PATHS}
    try:
        for item in os.listdir(extract_dir):
            if item.lower() in preserve_set: continue
            src = os.path.join(extract_dir, item); dst = os.path.join(NODE_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else: shutil.copy2(src, dst)
    except Exception as e:
        log(f"   ❌ Помилка копіювання: {e}", Colors.RED); return False
    if saved:
        log("🔑 Відновлення node_modules...", Colors.CYAN)
        _restore_user_data(saved)
        log("🔨 Перекомпіляція нативних модулів (npm rebuild)...", Colors.CYAN)
        node_env = {**os.environ, "PATH": NODE_DIR + ";" + os.environ.get("PATH", "")}
        try:
            r = subprocess.run([NPM_CMD, "rebuild"], capture_output=True, text=True,
                               timeout=120, cwd=NODE_DIR, env=node_env)
            if r.returncode == 0: log("   ✅ npm rebuild завершено.", Colors.GREEN)
            else: log(f"   ⚠️  npm rebuild: {r.stderr.strip()[:200]}", Colors.YELLOW)
        except Exception as e: log(f"   ⚠️  npm rebuild не вдалося: {e}", Colors.YELLOW)
    log(f"✅ Node.js оновлено до v{ver_str}!", Colors.GREEN)
    try: shutil.rmtree(tmp_dir, ignore_errors=True); os.remove(zip_path)
    except Exception: pass
    return True


def verify_node_tools() -> None:
    """Verify node, npm, npx are functional. UA: Перевіряє node, npm, npx."""
    cprint("-" * 50, Colors.BLUE)
    log("🔍 ПЕРЕВІРКА ІНСТРУМЕНТІВ", Colors.HEADER)
    node_env = {**os.environ, "PATH": NODE_DIR + ";" + os.environ.get("PATH", "")}
    for exe, name in [(NODE_EXE, "node"), (NPM_CMD, "npm "), (NPX_CMD, "npx ")]:
        if os.path.exists(exe):
            try:
                r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                                   timeout=10, env=node_env)
                log(f"   ✅ {name}: {r.stdout.strip()}", Colors.GREEN)
            except Exception as e: log(f"   ❌ {name}: {e}", Colors.RED)
        else: log(f"   ⚠️  {name} не знайдено: {exe}", Colors.YELLOW)
    node_modules = os.path.join(NODE_DIR, "node_modules")
    if os.path.exists(node_modules):
        pkgs = [d for d in os.listdir(node_modules) if not d.startswith(".")]
        if pkgs:
            log(f"   📦 Глобальні пакети ({len(pkgs)}): {', '.join(pkgs[:10])}"
                + (" ..." if len(pkgs) > 10 else ""), Colors.CYAN)
        else: log("   📭 Глобальних пакетів немає.", Colors.CYAN)
    else: log("   📭 node_modules відсутній.", Colors.CYAN)


def update_global_packages() -> None:
    """Update all outdated global npm packages. Always runs regardless of Node update.
    UA: Оновлює всі застарілі глобальні npm-пакети. Виконується завжди."""
    cprint("-" * 50, Colors.BLUE)
    log("📦 ОНОВЛЕННЯ ГЛОБАЛЬНИХ NPM-ПАКЕТІВ", Colors.HEADER)
    if not os.path.exists(NPM_CMD):
        log("   ⚠️ npm.cmd не знайдено, пропускаємо.", Colors.YELLOW); return
    node_env = {**os.environ, "PATH": NODE_DIR + ";" + os.environ.get("PATH", "")}
    try:
        r = subprocess.run([NPM_CMD, "outdated", "-g", "--json"],
                           capture_output=True, text=True, timeout=60, env=node_env)
        # npm outdated повертає RC=1 якщо є застарілі — це нормально
        outdated_raw = r.stdout.strip()
        if not outdated_raw or outdated_raw == "{}":
            log("   ✅ Всі глобальні пакети актуальні.", Colors.GREEN); return
        try:
            outdated = json.loads(outdated_raw)
        except json.JSONDecodeError:
            log("   ⚠️ Не вдалося розпарсити список застарілих пакетів.", Colors.YELLOW); return
        if not outdated:
            log("   ✅ Всі глобальні пакети актуальні.", Colors.GREEN); return
        log(f"   🔄 Застарілих пакетів: {len(outdated)}", Colors.YELLOW)
        for pkg, info in outdated.items():
            current = info.get("current", "?")
            latest  = info.get("latest", "?")
            log(f"      {pkg}: {current} → {latest}", Colors.YELLOW)
    except subprocess.TimeoutExpired:
        log("   ⚠️ Timeout при перевірці застарілих пакетів.", Colors.YELLOW); return
    except Exception as e:
        log(f"   ⚠️ Помилка перевірки пакетів: {e}", Colors.YELLOW); return
    log("   🚀 Запуск npm update -g...", Colors.CYAN)
    try:
        r = subprocess.run([NPM_CMD, "update", "-g"],
                           capture_output=True, text=True, timeout=300, env=node_env)
        if r.returncode == 0:
            log("   ✅ Глобальні пакети оновлено.", Colors.GREEN)
            if r.stdout.strip():
                for line in r.stdout.strip().splitlines()[:10]:
                    if line.strip(): log(f"      {line.strip()}", Colors.CYAN)
        else:
            log("   ⚠️ npm update -g завершився з помилкою:", Colors.YELLOW)
            for line in (r.stderr or r.stdout).strip().splitlines()[:5]:
                if line.strip(): log(f"      {line.strip()}", Colors.YELLOW)
    except subprocess.TimeoutExpired:
        log("   ⚠️ Timeout при оновленні пакетів (>5 хв).", Colors.YELLOW)
    except Exception as e:
        log(f"   ⚠️ Помилка оновлення пакетів: {e}", Colors.YELLOW)


def check_update() -> None:
    """Check for Node.js LTS update and apply if newer. UA: Перевіряє та застосовує оновлення."""
    cprint("-" * 50, Colors.BLUE)
    log("🌍 ПЕРЕВІРКА ОНОВЛЕННЯ (GitHub Releases)", Colors.HEADER)
    installed_ver = get_installed_version()
    npm_ver = get_npm_version()
    log(f"   Встановлена версія: v{installed_ver} (npm {npm_ver})", Colors.CYAN)
    try:
        latest_ver, download_url = get_latest_lts_release()
        log(f"   Остання LTS:        v{latest_ver}", Colors.CYAN)
        if version.parse(latest_ver) > version.parse(installed_ver):
            log(f"🚀 Знайдено нову версію! Оновлення v{installed_ver} → v{latest_ver}", Colors.YELLOW)
            if update_node(download_url, latest_ver):
                log(f"✅ Node.js оновлено до v{latest_ver}!", Colors.GREEN)
            else: log("⚠️ Оновлення не вдалося. Продовжуємо з поточною версією.", Colors.YELLOW)
        else: log("✅ Встановлена остання LTS-версія.", Colors.GREEN)
    except Exception as e:
        log(f"⚠️ Не вдалося перевірити оновлення: {e}", Colors.YELLOW)


def launch_pwsh_in_node_dir() -> None:
    """Launch PowerShell in NODE_DIR. UA: Запускає PowerShell у директорії apps/node/."""
    cprint("-" * 50, Colors.BLUE)
    log("🚀 Запуск PowerShell (Node.js середовище)...", Colors.GREEN)
    pwsh = PWSH_EXE if os.path.exists(PWSH_EXE) else "pwsh"
    node_env = {**os.environ, "PATH": NODE_DIR + ";" + os.environ.get("PATH", "")}
    DETACHED = 0x00000008; NEW_GROUP = 0x00000200
    try:
        subprocess.Popen(
            [pwsh, "-NoProfile", "-NoExit", "-Command",
             f"Set-Location '{NODE_DIR}'; "
             f"$env:PATH = '{NODE_DIR};' + $env:PATH; "
             f"Write-Host '🟢 Node.js v' + (node --version) + ' | npm v' + (npm --version) -ForegroundColor Green"],
            creationflags=DETACHED | NEW_GROUP, close_fds=True, env=node_env)
        log("   ✅ PowerShell запущено з Node.js у PATH.", Colors.GREEN)
    except Exception as e:
        log(f"   ❌ Не вдалося запустити PowerShell: {e}", Colors.RED)


def main() -> None:
    os.system("cls")
    print("\n")
    cprint("=" * 55, Colors.HEADER)
    cprint(f"  🟢 NODE.JS PORTABLE MANAGER  v{__version__}", Colors.HEADER)
    cprint(f"  Hash: {get_manager_hash()}", Colors.BLUE)
    cprint("  Autonomous Capsule | Oleksii Rovnianskyi", Colors.CYAN)
    cprint("=" * 55 + "\n", Colors.HEADER)

    ensure_in_system_path()
    cleanup_old_logs(7)
    verify_node_tools()
    update_global_packages()
    check_update()
    launch_pwsh_in_node_dir()

    elapsed = time.time() - START_TIME
    cprint(f"\n⏱️  Час виконання: {elapsed:.1f} сек", Colors.BLUE)
    print()
    for i in range(30, 0, -1):
        sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через {i} с...{Colors.RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через 0 с...  {Colors.RESET}   \n")
    sys.stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    main()
