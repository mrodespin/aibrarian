#!/usr/bin/env python3
# /setup.py
"""
Script de Instalación Automática - TFM Bibliotecario-IA

Este script automatiza la instalación completa del entorno de desarrollo
para el proyecto Bibliotecario-IA. Detecta qué está instalado y qué falta,
luego instala sólo lo necesario.

Modos de instalación soportados:
    - Modo A (Docker): Todo en contenedores (ollama, chromadb, api)
    - Modo B (Local/Híbrido): Ollama nativo + ChromaDB en Docker

¿Cuándo usar este script?
- Primera instalación después de clonar el repositorio
- Migración a un nuevo ordenador
- Reinstalación completa del entorno

¿Qué hace?
1. Detecta el sistema operativo (sólo macOS soportado por ahora)
2. Pregunta qué modo de instalación prefieres (A o B)
3. Verifica/instala Homebrew (si es necesario)
4. Instala Ollama y descarga modelos (si Modo B)
5. Verifica/instala Docker
6. Inicia servicios con docker-compose
7. Configura entorno Python (venv + dependencias)
8. Crea archivo .env con configuración correcta
9. Ejecuta verify_setup.py para confirmar

Requisitos previos:
- macOS (soporte para Linux/Windows pendiente)
- Conexión a internet (para descargar dependencias)
- Permisos de administrador (para brew install)

Uso:
    python3 setup.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
import sys
import subprocess
import platform
import shutil
from pathlib import Path

# ============================================================================
# COLORES PARA TERMINAL
# ============================================================================
class Colors:
    GREEN = '\033[92m'    # Verde (éxito)
    RED = '\033[91m'      # Rojo (error)
    YELLOW = '\033[93m'   # Amarillo (advertencia)
    BLUE = '\033[94m'     # Azul (información)
    CYAN = '\033[96m'     # Cian (prompts)
    ENDC = '\033[0m'      # Reset
    BOLD = '\033[1m'      # Negrita


# ============================================================================
# FUNCIONES DE FORMATO
# ============================================================================
def print_banner():
    """Imprime el banner de inicio."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     🚀 INSTALACIÓN - BIBLIOTECARIO-IA 🚀                ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(Colors.ENDC)


def print_header(text):
    """Imprime un encabezado de sección."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    """Mensaje de éxito."""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")


def print_error(text):
    """Mensaje de error."""
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")


def print_warning(text):
    """Mensaje de advertencia."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")


def print_info(text):
    """Mensaje informativo."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


def print_step(step_num, total_steps, text):
    """Imprime el paso actual."""
    print(f"\n{Colors.CYAN}[{step_num}/{total_steps}] {text}{Colors.ENDC}")


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================
def run_command(command, check=True, capture_output=True):
    """
    Ejecuta un comando shell y retorna el resultado.

    Args:
        command: Comando a ejecutar (string o lista)
        check: Si True, lanza excepción en caso de error
        capture_output: Si True, captura stdout/stderr

    Returns:
        subprocess.CompletedProcess con el resultado
    """
    if isinstance(command, str):
        command = command.split()

    return subprocess.run(
        command,
        check=check,
        capture_output=capture_output,
        text=True
    )


def is_installed(program):
    """Verifica si un programa está instalado en el PATH."""
    return shutil.which(program) is not None


def ask_yes_no(question, default=True):
    """
    Pregunta sí/no al usuario.

    Args:
        question: Texto de la pregunta
        default: Respuesta por defecto (True=sí, False=no)

    Returns:
        bool: True si la respuesta es sí
    """
    choices = " [S/n]: " if default else " [s/N]: "
    choice = input(f"{Colors.CYAN}{question}{choices}{Colors.ENDC}").lower().strip()

    if choice == '':
        return default
    elif choice in ['s', 'si', 'sí', 'y', 'yes']:
        return True
    elif choice in ['n', 'no']:
        return False
    else:
        print_warning("Respuesta no válida. Usando respuesta por defecto.")
        return default


def ask_choice(question, options):
    """
    Pregunta múltiple opción al usuario.

    Args:
        question: Texto de la pregunta
        options: Lista de tuplas (opción, descripción)

    Returns:
        str: La opción seleccionada
    """
    print(f"\n{Colors.CYAN}{question}{Colors.ENDC}")
    for i, (option, description) in enumerate(options, 1):
        print(f"  {i}. {Colors.BOLD}{option}{Colors.ENDC}")
        print(f"     {description}")

    while True:
        try:
            choice = int(input(f"\n{Colors.CYAN}Selecciona una opción [1-{len(options)}]: {Colors.ENDC}"))
            if 1 <= choice <= len(options):
                return options[choice - 1][0]
            else:
                print_warning(f"Por favor, elige un número entre 1 y {len(options)}")
        except ValueError:
            print_warning("Por favor, introduce un número válido")
        except KeyboardInterrupt:
            print("\n")
            print_warning("Instalación cancelada por el usuario")
            sys.exit(130)


# ============================================================================
# CHECKS DE SISTEMA
# ============================================================================
def check_os():
    """
    Verifica que el sistema operativo sea soportado.
    Por ahora sólo soporta macOS.
    """
    print_header("Verificando Sistema Operativo")

    os_name = platform.system()
    print_info(f"Sistema detectado: {os_name}")

    if os_name != "Darwin":  # Darwin = macOS
        print_error(f"Sistema operativo {os_name} no soportado todavía")
        print_info("Este script actualmente sólo soporta macOS")
        print_info("Para otros sistemas, consulta la documentación manual:")
        print_info("  - README.md")
        print_info("  - .ai/context.md")
        sys.exit(1)

    print_success(f"macOS es soportado")
    return True


def check_internet():
    """Verifica conectividad a internet."""
    print_header("Verificando Conexión a Internet")

    try:
        # Ping a 8.8.8.8 (Google DNS)
        result = run_command(["ping", "-c", "1", "-W", "2000", "8.8.8.8"], check=False)
        if result.returncode == 0:
            print_success("Conexión a internet disponible")
            return True
        else:
            print_error("No se detecta conexión a internet")
            print_info("Necesitas internet para descargar dependencias")
            return False
    except Exception as e:
        print_warning(f"No se pudo verificar conexión: {e}")
        return ask_yes_no("¿Continuar de todos modos?", default=False)


# ============================================================================
# INSTALACIÓN DE PREREQUISITOS
# ============================================================================
def install_homebrew():
    """Instala Homebrew si no está presente."""
    print_header("Verificando Homebrew")

    if is_installed("brew"):
        print_success("Homebrew ya está instalado")
        return True

    print_warning("Homebrew no está instalado")
    print_info("Homebrew es necesario para instalar Ollama y otras dependencias")

    if not ask_yes_no("¿Instalar Homebrew?", default=True):
        print_error("No se puede continuar sin Homebrew")
        return False

    print_info("Instalando Homebrew (esto puede tardar varios minutos)...")

    try:
        # Script oficial de instalación de Homebrew
        install_script = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        subprocess.run(install_script, shell=True, check=True)
        print_success("Homebrew instalado correctamente")
        return True
    except subprocess.CalledProcessError:
        print_error("Falló la instalación de Homebrew")
        print_info("Intenta instalarlo manualmente desde: https://brew.sh")
        return False


def install_ollama():
    """Instala Ollama y descarga los modelos necesarios."""
    print_header("Configurando Ollama")

    # Check si ollama está instalado
    if is_installed("ollama"):
        print_success("Ollama ya está instalado")

        # Check versión
        try:
            result = run_command("ollama --version")
            version = result.stdout.strip()
            print_info(f"Versión: {version}")
        except:
            pass
    else:
        print_warning("Ollama no está instalado")

        if not ask_yes_no("¿Instalar Ollama?", default=True):
            print_error("Ollama es necesario para el Modo B")
            return False

        print_info("Instalando Ollama con Homebrew...")
        try:
            run_command("brew install ollama")
            print_success("Ollama instalado correctamente")
        except subprocess.CalledProcessError:
            print_error("Falló la instalación de Ollama")
            return False

    # Iniciar servicio Ollama
    print_info("Iniciando servicio Ollama...")
    try:
        run_command("brew services start ollama", check=False)
        print_success("Servicio Ollama iniciado")
    except:
        print_warning("No se pudo iniciar el servicio (puede que ya esté corriendo)")

    # Verificar modelos
    print_info("Verificando modelos descargados...")
    try:
        result = run_command("ollama list")
        models_output = result.stdout

        models_needed = ["llama3.2", "nomic-embed-text"]
        models_to_download = []

        for model in models_needed:
            if model in models_output:
                print_success(f"Modelo {model} ya descargado")
            else:
                models_to_download.append(model)

        if models_to_download:
            print_warning(f"Faltan modelos: {', '.join(models_to_download)}")

            if ask_yes_no("¿Descargar modelos ahora? (llama3.2: ~2GB, nomic-embed-text: ~275MB)", default=True):
                for model in models_to_download:
                    print_info(f"Descargando {model}...")
                    try:
                        # No capturamos output para que el usuario vea el progreso
                        subprocess.run(["ollama", "pull", model], check=True)
                        print_success(f"Modelo {model} descargado")
                    except subprocess.CalledProcessError:
                        print_error(f"Falló la descarga de {model}")
                        return False

        print_success("Todos los modelos necesarios están disponibles")
        return True

    except subprocess.CalledProcessError:
        print_error("No se pudo verificar los modelos de Ollama")
        return False


def install_docker():
    """Verifica que Docker esté instalado."""
    print_header("Verificando Docker")

    if not is_installed("docker"):
        print_error("Docker no está instalado")
        print_info("Instala Docker Desktop desde: https://www.docker.com/products/docker-desktop")
        print_info("Después de instalar, vuelve a ejecutar este script")
        return False

    print_success("Docker está instalado")

    # Verificar que Docker esté corriendo
    try:
        run_command("docker ps", check=False, capture_output=True)
        print_success("Docker daemon está corriendo")
        return True
    except:
        print_error("Docker está instalado pero el daemon no está corriendo")
        print_info("Inicia Docker Desktop y vuelve a ejecutar este script")
        return False


def setup_docker_services(mode):
    """
    Inicia los servicios de Docker según el modo elegido.

    Args:
        mode: "A" para todo en Docker, "B" para sólo ChromaDB
    """
    print_header("Configurando Servicios Docker")

    if mode == "A":
        print_info("Iniciando todos los servicios (ollama, chromadb, api)...")
        try:
            subprocess.run(
                ["docker-compose", "up", "-d"],
                check=True,
                cwd=Path(__file__).parent.parent
            )
            print_success("Servicios Docker iniciados")

            # Descargar modelos en el contenedor de Ollama
            print_info("Descargando modelos en el contenedor de Ollama...")
            print_warning("Esto puede tardar varios minutos...")

            try:
                subprocess.run(
                    ["docker", "exec", "ollama", "ollama", "pull", "llama3.2"],
                    check=True
                )
                subprocess.run(
                    ["docker", "exec", "ollama", "ollama", "pull", "nomic-embed-text"],
                    check=True
                )
                print_success("Modelos descargados en Ollama (Docker)")
            except subprocess.CalledProcessError:
                print_warning("No se pudieron descargar los modelos automáticamente")
                print_info("Ejecuta manualmente:")
                print_info("  docker exec ollama ollama pull llama3.2")
                print_info("  docker exec ollama ollama pull nomic-embed-text")

            return True

        except subprocess.CalledProcessError:
            print_error("Falló al iniciar servicios Docker")
            return False

    elif mode == "B":
        print_info("Iniciando sólo ChromaDB...")
        try:
            subprocess.run(
                ["docker-compose", "up", "-d", "chromadb"],
                check=True,
                cwd=Path(__file__).parent.parent
            )
            print_success("ChromaDB iniciado")
            return True
        except subprocess.CalledProcessError:
            print_error("Falló al iniciar ChromaDB")
            return False


# ============================================================================
# CONFIGURACIÓN DE PYTHON
# ============================================================================
def setup_python():
    """Configura el entorno Python (venv + dependencias)."""
    print_header("Configurando Entorno Python")

    # Verificar versión de Python
    python_version = sys.version_info
    print_info(f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")

    if python_version < (3, 11):
        print_error(f"Se requiere Python 3.11+")
        print_info("Instala una versión más reciente de Python")
        return False

    print_success("Versión de Python compatible")

    # Directorio api (script está en scripts/, api/ está en root)
    project_root = Path(__file__).parent.parent
    api_dir = project_root / "api"
    venv_dir = api_dir / "venv"

    # Crear venv si no existe
    if venv_dir.exists():
        print_success("Virtual environment ya existe")
    else:
        print_info("Creando virtual environment...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True
            )
            print_success("Virtual environment creado")
        except subprocess.CalledProcessError:
            print_error("Falló la creación del virtual environment")
            return False

    # Instalar dependencias
    print_info("Instalando dependencias Python (esto puede tardar 1-2 minutos)...")

    pip_executable = venv_dir / "bin" / "pip"
    requirements_file = api_dir / "requirements.txt"

    try:
        subprocess.run(
            [str(pip_executable), "install", "-r", str(requirements_file)],
            check=True,
            capture_output=True
        )
        print_success("Dependencias instaladas correctamente")
        return True
    except subprocess.CalledProcessError as e:
        print_error("Falló la instalación de dependencias")
        print_info(f"Error: {e.stderr}")
        return False


def setup_env_file(mode):
    """
    Crea el archivo .env con la configuración correcta según el modo.

    Args:
        mode: "A" para Docker, "B" para local
    """
    print_header("Configurando Variables de Entorno")

    api_dir = Path(__file__).parent.parent / "api"
    env_file = api_dir / ".env"
    env_example = api_dir / ".env.example"

    if env_file.exists():
        print_warning("Ya existe un archivo .env")
        if not ask_yes_no("¿Sobrescribirlo?", default=False):
            print_info("Conservando .env existente")
            return True

    # Copiar .env.example
    try:
        shutil.copy(env_example, env_file)
        print_success("Archivo .env creado desde .env.example")

        # Si es Modo A, avisar que no necesita cambios
        if mode == "A":
            print_info("Para Modo A (Docker), el .env.example ya tiene valores correctos")
            print_info("docker-compose sobrescribe automáticamente con los nombres de contenedor")
        else:
            print_info("Para Modo B (Local), el .env.example ya tiene valores correctos")
            print_info("(localhost y puertos mapeados)")

        # Preguntar por credenciales de Notion
        print_info("\n¿Quieres configurar las credenciales de Notion ahora?")
        print_info("(Opcional - puedes editarlas después en api/.env)")

        if ask_yes_no("¿Configurar Notion?", default=False):
            notion_key = input(f"{Colors.CYAN}NOTION_API_KEY: {Colors.ENDC}").strip()
            notion_db = input(f"{Colors.CYAN}NOTION_DATABASE_ID (opcional): {Colors.ENDC}").strip()

            # Leer el archivo .env
            with open(env_file, 'r') as f:
                content = f.read()

            # Reemplazar valores
            content = content.replace("NOTION_API_KEY=", f"NOTION_API_KEY={notion_key}")
            if notion_db:
                content = content.replace("NOTION_DATABASE_ID=", f"NOTION_DATABASE_ID={notion_db}")

            # Escribir de vuelta
            with open(env_file, 'w') as f:
                f.write(content)

            print_success("Credenciales de Notion configuradas")

        return True

    except Exception as e:
        print_error(f"Falló la creación del .env: {e}")
        return False


# ============================================================================
# VERIFICACIÓN FINAL
# ============================================================================
def run_verification():
    """Ejecuta el script de verificación."""
    print_header("Verificación Final del Setup")

    api_dir = Path(__file__).parent.parent / "api"
    verify_script = api_dir / "verify_setup.py"
    venv_python = api_dir / "venv" / "bin" / "python"

    if not verify_script.exists():
        print_warning("Script de verificación no encontrado")
        return True

    print_info("Ejecutando verify_setup.py...\n")

    try:
        # Ejecutar verify_setup.py sin capturar output para que el usuario lo vea
        result = subprocess.run(
            [str(venv_python), str(verify_script)],
            cwd=api_dir,
            check=False
        )

        # El script retorna 0 si todo OK, 1 si hay advertencias
        if result.returncode == 0:
            print_success("\n✨ Todas las verificaciones pasaron ✨")
        else:
            print_warning("\nHay algunas advertencias (revisa el output arriba)")

        return True

    except Exception as e:
        print_error(f"Falló la verificación: {e}")
        return False


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================
def main():
    """Orquesta todo el proceso de instalación."""

    try:
        # Banner
        print_banner()

        print_info("Este script instalará y configurará todo el entorno necesario")
        print_info("para ejecutar Bibliotecario-IA en tu ordenador.\n")

        if not ask_yes_no("¿Continuar con la instalación?", default=True):
            print_info("Instalación cancelada")
            return

        # 1. Verificar sistema operativo
        if not check_os():
            return

        # 2. Verificar internet
        if not check_internet():
            print_error("No se puede continuar sin conexión a internet")
            return

        # 3. Seleccionar modo de instalación
        mode = ask_choice(
            "¿Qué modo de instalación prefieres?",
            [
                ("A", "Docker: Todo en contenedores (reproducible, más lento)"),
                ("B", "Local/Híbrido: Ollama nativo + ChromaDB en Docker (más rápido, GPU)")
            ]
        )

        print_info(f"\nModo seleccionado: {mode}")

        if mode == "B":
            print_info("Ollama nativo tendrá acceso a la GPU de Apple Silicon (Metal)")
            print_info("Esto es ~10x más rápido que CPU para inferencia")
        else:
            print_warning("Ollama en Docker NO tendrá acceso a la GPU en macOS")
            print_info("Pero el entorno será 100% reproducible")

        # 4. Instalar Homebrew
        if not install_homebrew():
            return

        # 5. Instalar Ollama (sólo si Modo B)
        if mode == "B":
            if not install_ollama():
                print_error("Falló la configuración de Ollama")
                return

        # 6. Verificar Docker
        if not install_docker():
            return

        # 7. Iniciar servicios Docker
        if not setup_docker_services(mode):
            return

        # 8. Configurar Python
        if not setup_python():
            return

        # 9. Crear archivo .env
        if not setup_env_file(mode):
            return

        # 10. Verificación final
        run_verification()

        # Resumen final
        print_header("✨ Instalación Completada ✨")

        print_success("El entorno está listo para usar")

        print_info("\n📝 Próximos pasos:")
        print_info("  1. Iniciar la API:")
        print_info("     cd api")
        print_info("     source venv/bin/activate")
        print_info("     uvicorn app.main:app --reload")
        print_info("")
        print_info("  2. La API estará en: http://localhost:8000")
        print_info("  3. Documentación: http://localhost:8000/docs")
        print_info("")
        print_info("📚 Recursos:")
        print_info("  - README.md: Guía general")
        print_info("  - docs/USAGE.md: Endpoints de la API")
        print_info("  - .ai/context.md: Contexto completo del proyecto")

    except KeyboardInterrupt:
        print("\n")
        print_warning("Instalación interrumpida por el usuario")
        sys.exit(130)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
