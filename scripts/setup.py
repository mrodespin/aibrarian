#!/usr/bin/env python3
# /scripts/setup.py
"""
Script de Instalación Automática - TFM Bibliotecario-IA

Este script automatiza la instalación completa del entorno de desarrollo.
Detecta qué está instalado y qué falta, luego instala sólo lo necesario.

Configuración:
- Ollama: Nativo en macOS (acceso a GPU Metal, ~10x más rápido)
- ChromaDB: Docker (persistencia con volúmenes)
- API: Docker (hot-reload con volume mount)
- Frontend: React + Vite (npm run dev)

¿Qué hace?
1. Verifica el sistema operativo (macOS)
2. Verifica/instala Homebrew
3. Instala Ollama y descarga modelos
4. Verifica Docker y levanta ChromaDB + API
5. Configura entorno Python (venv + dependencias para scripts CLI)
6. Crea archivo .env
7. Configura Frontend (Node.js 18+ + npm install)
8. Ejecuta verify_setup.py para confirmar

Uso:
    python3 scripts/setup.py
"""

import sys
import subprocess
import platform
import shutil
from pathlib import Path

# ============================================================================
# COLORES PARA TERMINAL
# ============================================================================
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_banner():
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║     🚀 INSTALACIÓN - BIBLIOTECARIO-IA 🚀                ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(Colors.ENDC)


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


def run_command(command, check=True, capture_output=True):
    if isinstance(command, str):
        command = command.split()
    return subprocess.run(command, check=check, capture_output=capture_output, text=True)


def is_installed(program):
    return shutil.which(program) is not None


def ask_yes_no(question, default=True):
    choices = " [S/n]: " if default else " [s/N]: "
    choice = input(f"{Colors.CYAN}{question}{choices}{Colors.ENDC}").lower().strip()
    if choice == '':
        return default
    return choice in ['s', 'si', 'sí', 'y', 'yes']


# ============================================================================
# CHECKS DE SISTEMA
# ============================================================================
def check_os():
    print_header("1. Verificando Sistema Operativo")
    os_name = platform.system()
    print_info(f"Sistema detectado: {os_name}")

    if os_name != "Darwin":
        print_error(f"Sistema {os_name} no soportado. Este script es para macOS.")
        print_info("Para otros sistemas, consulta README.md")
        return False

    print_success("macOS detectado")
    return True


def check_internet():
    print_header("2. Verificando Conexión a Internet")
    try:
        result = run_command(["ping", "-c", "1", "-W", "2000", "8.8.8.8"], check=False)
        if result.returncode == 0:
            print_success("Conexión a internet disponible")
            return True
        print_error("Sin conexión a internet")
        return False
    except Exception as e:
        print_warning(f"No se pudo verificar: {e}")
        return ask_yes_no("¿Continuar de todos modos?", default=False)


# ============================================================================
# INSTALACIÓN DE PREREQUISITOS
# ============================================================================
def install_homebrew():
    print_header("3. Verificando Homebrew")

    if is_installed("brew"):
        print_success("Homebrew ya está instalado")
        return True

    print_warning("Homebrew no está instalado")
    if not ask_yes_no("¿Instalar Homebrew?"):
        print_error("Homebrew es necesario para instalar Ollama")
        return False

    print_info("Instalando Homebrew...")
    try:
        subprocess.run(
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            shell=True, check=True
        )
        print_success("Homebrew instalado")
        return True
    except subprocess.CalledProcessError:
        print_error("Falló la instalación de Homebrew")
        return False


def install_ollama():
    print_header("4. Configurando Ollama (Nativo)")
    print_info("Ollama corre nativo en macOS para aprovechar GPU Metal (~10x más rápido)")

    if is_installed("ollama"):
        print_success("Ollama ya está instalado")
    else:
        print_warning("Ollama no está instalado")
        if not ask_yes_no("¿Instalar Ollama con Homebrew?"):
            print_error("Ollama es necesario para el LLM")
            return False

        print_info("Instalando Ollama...")
        try:
            run_command("brew install ollama")
            print_success("Ollama instalado")
        except subprocess.CalledProcessError:
            print_error("Falló la instalación de Ollama")
            return False

    # Iniciar servicio
    print_info("Iniciando servicio Ollama...")
    run_command("brew services start ollama", check=False)

    # Verificar y descargar modelos
    print_info("Verificando modelos...")
    try:
        result = run_command("ollama list")
        models_output = result.stdout

        for model in ["llama3.2", "nomic-embed-text"]:
            if model in models_output:
                print_success(f"Modelo {model} disponible")
            else:
                print_warning(f"Descargando {model}...")
                subprocess.run(["ollama", "pull", model], check=True)
                print_success(f"Modelo {model} descargado")

        return True
    except subprocess.CalledProcessError:
        print_error("Error verificando modelos de Ollama")
        return False


def install_docker():
    print_header("5. Verificando Docker")

    if not is_installed("docker"):
        print_error("Docker no está instalado")
        print_info("Instala Docker Desktop: https://www.docker.com/products/docker-desktop")
        return False

    print_success("Docker está instalado")

    # Verificar daemon
    try:
        run_command("docker ps", check=True, capture_output=True)
        print_success("Docker daemon está corriendo")
        return True
    except:
        print_error("Docker no está corriendo. Inicia Docker Desktop.")
        return False


def setup_docker_services():
    print_header("6. Iniciando Servicios Docker (ChromaDB + API)")

    try:
        # Build y start de todos los servicios
        subprocess.run(
            ["docker-compose", "up", "-d", "--build"],
            check=True,
            cwd=Path(__file__).parent.parent
        )
        print_success("ChromaDB iniciado en puerto 8001")
        print_success("API iniciada en puerto 8000")
        return True
    except subprocess.CalledProcessError:
        print_error("Falló al iniciar servicios Docker")
        return False


# ============================================================================
# CONFIGURACIÓN DE PYTHON
# ============================================================================
def setup_python():
    print_header("7. Configurando Entorno Python")

    python_version = sys.version_info
    print_info(f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")

    if python_version < (3, 11):
        print_error("Se requiere Python 3.11+")
        return False

    print_success("Versión de Python compatible")

    project_root = Path(__file__).parent.parent
    api_dir = project_root / "api"
    venv_dir = api_dir / "venv"

    # Crear venv
    if venv_dir.exists():
        print_success("Virtual environment existe")
    else:
        print_info("Creando virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        print_success("Virtual environment creado")

    # Instalar dependencias
    print_info("Instalando dependencias Python...")
    pip_executable = venv_dir / "bin" / "pip"
    requirements_file = api_dir / "requirements.txt"

    try:
        subprocess.run(
            [str(pip_executable), "install", "-r", str(requirements_file)],
            check=True, capture_output=True
        )
        print_success("Dependencias instaladas")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Falló la instalación: {e.stderr}")
        return False


def setup_env_file():
    print_header("8. Configurando Variables de Entorno")

    api_dir = Path(__file__).parent.parent / "api"
    env_file = api_dir / ".env"
    env_example = api_dir / ".env.example"

    if env_file.exists():
        print_warning("Ya existe .env")
        if not ask_yes_no("¿Sobrescribirlo?", default=False):
            print_info("Conservando .env existente")
            return True

    try:
        shutil.copy(env_example, env_file)
        print_success("Archivo .env creado desde .env.example")
        print_info("Configuración: Ollama en localhost:11434, ChromaDB en localhost:8001")

        # Preguntar por Notion (opcional)
        if ask_yes_no("¿Configurar credenciales de Notion? (opcional)", default=False):
            notion_key = input(f"{Colors.CYAN}NOTION_API_KEY: {Colors.ENDC}").strip()

            with open(env_file, 'r') as f:
                content = f.read()
            content = content.replace("NOTION_API_KEY=", f"NOTION_API_KEY={notion_key}")
            with open(env_file, 'w') as f:
                f.write(content)

            print_success("Notion configurado")

        return True
    except Exception as e:
        print_error(f"Falló la creación del .env: {e}")
        return False


# ============================================================================
# CONFIGURACIÓN DEL FRONTEND
# ============================================================================
def setup_frontend():
    print_header("9. Configurando Frontend")

    project_root = Path(__file__).parent.parent
    frontend_dir = project_root / "frontend"

    if not frontend_dir.exists():
        print_error("Directorio frontend/ no encontrado")
        return False

    # Verificar Node.js
    if not is_installed("node"):
        print_warning("Node.js no está instalado")
        print_info("El frontend requiere Node.js 18+")
        if ask_yes_no("¿Instalar Node.js con Homebrew?"):
            run_command("brew install node")
            print_success("Node.js instalado")
        else:
            print_info("Instala Node.js manualmente: https://nodejs.org/")
            return True

    # Verificar versión de Node.js (requiere 18+)
    try:
        result = run_command("node --version")
        version_str = result.stdout.strip().lstrip('v')
        major_version = int(version_str.split('.')[0])
        print_info(f"Node.js v{version_str} detectado")

        if major_version < 18:
            print_warning(f"Node.js {major_version} es antiguo. Se requiere 18+")
            print_info("Actualiza con: brew upgrade node")
            return False

        print_success("Node.js 18+ disponible")
    except Exception as e:
        print_warning(f"No se pudo verificar versión de Node.js: {e}")

    # Instalar dependencias
    node_modules = frontend_dir / "node_modules"
    if node_modules.exists() and any(node_modules.iterdir()):
        print_success("Dependencias del frontend ya instaladas")
        return True

    print_info("Instalando dependencias del frontend...")
    try:
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        print_success("Dependencias del frontend instaladas")
        return True
    except subprocess.CalledProcessError:
        print_error("Falló npm install")
        return False


# ============================================================================
# VERIFICACIÓN FINAL
# ============================================================================
def run_verification():
    print_header("10. Verificación Final")

    project_root = Path(__file__).parent.parent
    verify_script = Path(__file__).parent / "verify_setup.py"
    venv_python = project_root / "api" / "venv" / "bin" / "python"

    if not verify_script.exists():
        print_warning("Script de verificación no encontrado")
        return True

    print_info("Ejecutando verify_setup.py...\n")
    result = subprocess.run([str(venv_python), str(verify_script)], cwd=project_root, check=False)

    if result.returncode == 0:
        print_success("\n✨ Todas las verificaciones pasaron ✨")
    else:
        print_warning("\nRevisa las advertencias arriba")

    return True


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================
def main():
    try:
        print_banner()

        print_info("Este script configura el entorno de desarrollo:")
        print_info("  - Ollama nativo (GPU Metal)")
        print_info("  - ChromaDB + API en Docker")
        print_info("  - Frontend con npm\n")

        if not ask_yes_no("¿Continuar con la instalación?"):
            print_info("Instalación cancelada")
            return

        # Ejecutar pasos
        if not check_os(): return
        if not check_internet(): return
        if not install_homebrew(): return
        if not install_ollama(): return
        if not install_docker(): return
        if not setup_docker_services(): return
        if not setup_python(): return
        if not setup_env_file(): return
        setup_frontend()
        run_verification()

        # Resumen final
        print_header("✨ Instalación Completada ✨")

        print_success("El entorno está listo")
        print_info("\n📝 Para iniciar el sistema:\n")
        print_info("  # Terminal 1: Ollama (mantener abierto)")
        print_info("  ollama serve")
        print_info("")
        print_info("  # Terminal 2: Docker (ChromaDB + API)")
        print_info("  docker-compose up -d")
        print_info("")
        print_info("  # Terminal 3: Frontend")
        print_info("  cd frontend && npm run dev")
        print_info("")
        print_info("  🌐 Frontend: http://localhost:5173")
        print_info("  📚 API Docs: http://localhost:8000/docs")
        print_info("  💾 ChromaDB: http://localhost:8001")
        print_info("")
        print_info("📚 Documentación:")
        print_info("  - README.md: Guía general")
        print_info("  - docs/USAGE.md: Endpoints de la API")
        print_info("  - .ai/context.md: Contexto del proyecto")

    except KeyboardInterrupt:
        print("\n")
        print_warning("Instalación interrumpida")
        sys.exit(130)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
