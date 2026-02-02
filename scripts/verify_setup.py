#!/usr/bin/env python3
# /scripts/verify_setup.py
"""
Script de Verificación del Entorno - TFM Bibliotecario-IA

Este script comprueba que todos los servicios y dependencias necesarios
para ejecutar Bibliotecario-IA estén correctamente instalados y configurados.

¿Cuándo usar este script?
- Después de clonar el repositorio en un nuevo ordenador
- Cuando algo no funciona y quieres verificar que el entorno está correcto
- Antes de ejecutar la API por primera vez

Checks que realiza (8 en total):
    1. Versión de Python (se requiere 3.11+)
    2. Dependencias Python instaladas
    3. Ollama: instalación, servicio y modelos
    4. Docker: instalación y daemon activo
    5. ChromaDB: disponibilidad del servicio
    6. Estructura del proyecto: directorios necesarios
    7. Directorio de datos: presencia de PDFs
    8. API: health check (opcional, no falla si no está corriendo)

Nota sobre rutas relativas:
    Este script se ejecuta desde el directorio scripts/ y usa rutas
    relativas al directorio raíz del proyecto.

Uso:
    python scripts/verify_setup.py
    # o desde scripts/
    cd scripts && python verify_setup.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
import sys
import subprocess
import asyncio
from pathlib import Path

# ============================================================================
# COLORES PARA TERMINAL
# ============================================================================
# Códigos ANSI para colorear el output en la terminal.
# Estos códigos son secuencias de escape que los emuladores de terminal
# interpretan para cambiar el color del texto.
# Formato: \033[<código>m  donde \033 es el carácter ESC (escape).
#
# Equivalente en JS/Node.js: chalk.green(), chalk.red(), etc.
class Colors:
    GREEN = '\033[92m'    # Verde (éxito)
    RED = '\033[91m'      # Rojo (error)
    YELLOW = '\033[93m'   # Amarillo (advertencia)
    BLUE = '\033[94m'     # Azul (información)
    ENDC = '\033[0m'      # Reset: vuelve al color por defecto
    BOLD = '\033[1m'      # Negrita


# ============================================================================
# FUNCIONES DE FORMATO DE OUTPUT
# ============================================================================
# Cada función envuelve el texto con los códigos de color apropiados.
# El patrón es siempre: color + emoji + texto + ENDC (reset).
def print_header(text):
    """Imprime un encabezado visualmente destacado."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    """Imprime un mensaje de éxito en verde."""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text):
    """Imprime un mensaje de error en rojo."""
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_warning(text):
    """Imprime un mensaje de advertencia en amarillo."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text):
    """Imprime un mensaje informativo en azul."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


# ============================================================================
# CHECKS DE VERIFICACIÓN
# ============================================================================
# Cada función verifica un aspecto del entorno y devuelve True/False.
# Todas siguen el mismo patrón:
#   1. Imprimir encabezado numerado
#   2. Realizar la verificación
#   3. Imprimir resultado (éxito/error) con indicaciones si falla
#   4. Devolver booleano para el resumen final

def check_python_version():
    """
    Verifica que la versión de Python sea 3.11 o superior.

    ¿Por qué 3.11+?
    El proyecto usa funcionalidades modernas de Python como
    ExceptionGroup (3.11) y mejoras de performance significativas.
    FastAPI y LangChain también recomiendan versiones recientes.

    Returns:
        bool: True si la versión es compatible
    """
    print_header("1. Verificando Python")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    print_info(f"Python version: {version_str}")

    if version.major >= 3 and version.minor >= 11:
        print_success(f"Python {version_str} es compatible")
        return True
    else:
        print_error(f"Python {version_str} es demasiado antiguo. Se requiere 3.11+")
        return False


def check_dependencies():
    """
    Verifica que las dependencias Python principales estén instaladas.

    Estrategia:
    1. Detecta si el script se ejecuta desde un virtual environment
    2. Si NO: verifica el venv en api/venv/ mirando site-packages
    3. Si SÍ: verifica importando los paquetes normalmente

    Esto permite ejecutar el script sin activar el venv y aún así
    verificar que las dependencias estén instaladas.

    Returns:
        bool: True si todos los paquetes están instalados
    """
    print_header("2. Verificando Dependencias Python")

    # Detectar si estamos en un virtual environment
    # sys.real_prefix existe en virtualenv antiguo
    # sys.base_prefix != sys.prefix en venv moderno (Python 3.3+)
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )

    project_root = Path(__file__).parent.parent
    venv_path = project_root / "api" / "venv"

    required_packages = ['fastapi', 'uvicorn', 'langchain', 'chromadb', 'pydantic', 'httpx']

    if not in_venv:
        # No estamos en venv, verificar si existe api/venv
        if not venv_path.exists():
            print_error("Virtual environment NO encontrado en api/venv/")
            print_info("Ejecuta: python3 scripts/setup.py")
            return False

        print_info(f"Virtual environment: {venv_path.relative_to(project_root)}")
        print_warning("No estás en el venv (pero está OK, verificando paquetes...)")

        # Buscar site-packages del venv
        site_packages_candidates = list((venv_path / "lib").glob("python*/site-packages"))

        if not site_packages_candidates:
            print_error("No se encontró site-packages en el venv")
            return False

        site_packages = site_packages_candidates[0]
        all_ok = True

        for package in required_packages:
            # Buscar el paquete en site-packages
            # Puede ser un directorio o un .dist-info
            package_normalized = package.replace('-', '_')
            package_dir = site_packages / package_normalized
            dist_info = list(site_packages.glob(f"{package_normalized}*.dist-info"))

            if package_dir.exists() or dist_info:
                print_success(f"{package} instalado")
            else:
                print_error(f"{package} NO instalado")
                all_ok = False

        if not all_ok:
            print_warning("Instala dependencias:")
            print_info("  cd api && source venv/bin/activate")
            print_info("  pip install -r requirements.txt")

        return all_ok

    # Estamos en venv, verificar importando directamente
    print_success("Ejecutando desde virtual environment ✓")

    all_ok = True
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} instalado")
        except ImportError:
            print_error(f"{package} NO instalado")
            all_ok = False

    if not all_ok:
        print_warning("Ejecuta: pip install -r requirements.txt")

    return all_ok


def check_ollama():
    """
    Verifica Ollama en tres niveles: instalación, servicio y modelos.

    Es la verificación más compleja porque Ollama tiene dos partes:
    1. La herramienta CLI (ollama --version)
    2. El servidor en background (ollama serve → puerto 11434)

    Además, verifica que los modelos necesarios estén descargados:
    - llama3.2: modelo LLM para generar respuestas
    - nomic-embed-text: modelo de embeddings para búsqueda semántica

    ¿Por qué subprocess para la instalación pero httpx para el servicio?
    - subprocess: comprobar si el binario 'ollama' existe en PATH
    - httpx: comprobar si el servidor HTTP está corriendo y responde

    Returns:
        bool: True si Ollama está instalado y el servicio está corriendo.
              Los modelos no descargados generan advertencia, no error.
    """
    print_header("3. Verificando Ollama")

    # --- Nivel 1: Instalación del binario ---
    try:
        result = subprocess.run(
            ['ollama', '--version'],
            capture_output=True,   # Captura stdout y stderr
            text=True,             # Devuelve strings, no bytes
            timeout=5              # Si no responde en 5s, TimeoutExpired
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Ollama instalado: {version}")
        else:
            print_error("Ollama instalado pero no responde correctamente")
            return False
    except FileNotFoundError:
        # FileNotFoundError: el comando 'ollama' no existe en PATH
        print_error("Ollama NO está instalado")
        print_info("Instala desde: https://ollama.ai")
        return False
    except subprocess.TimeoutExpired:
        print_error("Ollama no responde (timeout)")
        return False

    # --- Nivel 2: Servicio corriendo ---
    # Si llegamos aquí, Ollama está instalado. Ahora verificamos
    # que el servidor (ollama serve) esté activo.
    try:
        import httpx
        # GET /api/tags devuelve la lista de modelos descargados.
        # Si el servicio no está corriendo, la conexión falla.
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            print_success("Servicio Ollama está corriendo")

            # --- Nivel 3: Modelos descargados ---
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]

            # Los nombres en Ollama pueden incluir tags (ej: 'llama3.2:latest')
            # por eso usamos 'in' en lugar de comparación exacta
            required_models = ['llama3.2', 'nomic-embed-text']
            for model in required_models:
                if any(model in name for name in model_names):
                    print_success(f"Modelo {model} descargado")
                else:
                    # Advertencia, no error: el servicio funciona
                    # pero faltarán los modelos al usar el sistema
                    print_warning(f"Modelo {model} NO descargado")
                    print_info(f"   Ejecuta: ollama pull {model}")

            return True
        else:
            print_error(f"Ollama responde con código: {response.status_code}")
            return False
    except Exception as e:
        print_error("Servicio Ollama NO está corriendo")
        print_info("Ejecuta en otro terminal: ollama serve")
        return False


def check_docker():
    """
    Verifica Docker en dos niveles: instalación y daemon activo.

    ¿Por qué verificar el daemon por separado?
    En macOS/Windows, Docker Desktop puede estar instalado pero no iniciado.
    'docker --version' funciona sin el daemon, pero 'docker ps' requiere
    que el daemon esté corriendo.

    Returns:
        bool: True si Docker está instalado y corriendo
    """
    print_header("4. Verificando Docker")

    # --- Nivel 1: Instalación ---
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Docker instalado: {version}")
        else:
            print_error("Docker instalado pero no responde")
            return False
    except FileNotFoundError:
        print_error("Docker NO está instalado")
        print_info("Instala Docker Desktop desde: https://www.docker.com/products/docker-desktop")
        return False

    # --- Nivel 2: Daemon activo ---
    # 'docker ps' lista contenedores. Falla si el daemon no está corriendo.
    try:
        result = subprocess.run(
            ['docker', 'ps'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success("Docker está corriendo")
            return True
        else:
            print_error("Docker no está corriendo")
            print_info("Inicia Docker Desktop")
            return False
    except subprocess.TimeoutExpired:
        print_error("Docker no responde (timeout)")
        return False


def check_chromadb():
    """
    Verifica que ChromaDB esté corriendo y responda al heartbeat.

    ChromaDB expone un endpoint /api/v2/heartbeat que devuelve 200
    si el servicio está activo. Es el equivalente a un health check.

    Nota: ChromaDB corre en el puerto 8001 (no el por defecto 8000)
    para no conflictar con la API de FastAPI.

    Returns:
        bool: True si ChromaDB responde al heartbeat
    """
    print_header("5. Verificando ChromaDB")

    try:
        import httpx
        response = httpx.get("http://localhost:8001/api/v2/heartbeat", timeout=5.0)
        if response.status_code == 200:
            print_success("ChromaDB está corriendo y responde")
            return True
        else:
            print_error(f"ChromaDB responde con código: {response.status_code}")
            return False
    except Exception as e:
        print_error("ChromaDB NO está corriendo")
        print_info("Ejecuta: docker-compose up -d chromadb")
        return False


def check_project_structure():
    """
    Verifica que los directorios principales del proyecto existan.

    Comprueba los directorios necesarios para que el sistema funcione:
    - api/app/core: lógica de negocio
    - api/app/adapters: implementaciones concretas
    - api/app/config: configuración
    - data: directorio de PDFs

    Returns:
        bool: True si todos los directorios existen
    """
    print_header("6. Verificando Estructura del Proyecto")

    # Calcular rutas desde la ubicación del script
    project_root = Path(__file__).parent.parent

    required_dirs = [
        project_root / 'api' / 'app' / 'core',
        project_root / 'api' / 'app' / 'adapters',
        project_root / 'api' / 'app' / 'config',
        project_root / 'data'
    ]

    all_ok = True
    for path in required_dirs:
        # Mostrar path relativo para mejor legibilidad
        rel_path = path.relative_to(project_root)
        if path.exists():
            print_success(f"Directorio {rel_path} existe")
        else:
            print_error(f"Directorio {rel_path} NO existe")
            all_ok = False

    return all_ok


def check_data_directory():
    """
    Verifica el contenido del directorio de datos.

    Diferente a los otros checks: este NO falla si no hay PDFs.
    Un directorio de datos vacío es un entorno válido (simplemente
    no hay documentos ingestados aún). Solo falla si el directorio
    en sí no existe.

    Returns:
        bool: True si el directorio existe (independientemente de su contenido)
    """
    print_header("7. Verificando Directorio de Datos")

    # Calcular ruta desde la ubicación del script
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data'

    if not data_dir.exists():
        print_error("Directorio /data NO existe")
        return False

    pdf_files = list(data_dir.glob('*.pdf'))

    if pdf_files:
        print_success(f"Encontrados {len(pdf_files)} archivos PDF")
        # Mostrar solo los primeros 5 para no saturar la terminal
        for pdf in pdf_files[:5]:
            print_info(f"   - {pdf.name}")
        if len(pdf_files) > 5:
            print_info(f"   ... y {len(pdf_files) - 5} más")
    else:
        # Advertencia, no error: el directorio existe pero está vacío
        print_warning("No hay archivos PDF en /data")
        print_info("Copia algunos PDFs para probar el sistema")

    return True


async def check_api_health():
    """
    Verifica el health check de la API FastAPI (check opcional).

    Esta es la única función async del script porque usa httpx.AsyncClient.
    Todas las otras verificaciones son síncronas (subprocess o httpx síncrono).

    ¿Por qué es opcional?
    La API no tiene que estar corriendo para que el entorno esté configurado.
    Es un check informativo: si la API está activa, verifica que sus
    conexiones internas (Ollama, ChromaDB) funcionan desde su perspectiva.

    Returns:
        bool: True si la API está corriendo y responde. False en cualquier
              otro caso, pero NO se considera error crítico.
    """
    print_header("8. Verificando API (opcional)")

    try:
        import httpx
        # AsyncClient: versión asíncrona de httpx para usar con await
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                print_success("API está corriendo")

                # El endpoint /health devuelve el estado de los servicios
                # que la API puede ver (Ollama y ChromaDB)
                services = data.get('services', {})
                if services.get('ollama'):
                    print_success("  API puede conectar con Ollama")
                else:
                    print_warning("  API NO puede conectar con Ollama")

                if services.get('chromadb'):
                    print_success("  API puede conectar con ChromaDB")
                else:
                    print_warning("  API NO puede conectar con ChromaDB")

                return True
            else:
                print_warning(f"API responde con código: {response.status_code}")
                return False
    except Exception as e:
        # No es un error: la API simplemente no está corriendo
        print_warning("API NO está corriendo (esto es normal si no la has iniciado)")
        print_info("Para iniciar: uvicorn app.main:app --reload")
        return False


# ============================================================================
# RESUMEN DE RESULTADOS
# ============================================================================
def print_summary(results):
    """
    Imprime un resumen de todos los checks y las siguientes acciones.

    Args:
        results: Diccionario {nombre_check: bool} con los resultados
                 de cada verificación.
    """
    print_header("Resumen de Verificación")

    total = len(results)
    passed = sum(1 for r in results.values() if r)
    failed = total - passed

    print(f"Total checks: {total}")
    print_success(f"Pasados: {passed}")
    if failed > 0:
        print_error(f"Fallidos: {failed}")

    print("\n" + "="*60)

    if failed == 0:
        # Todo correcto: mostrar los próximos pasos para usar el sistema
        print_success("🎉 ¡TODO ESTÁ CONFIGURADO CORRECTAMENTE!")
        print_info("\nPróximos pasos:")
        print_info("1. Iniciar API: uvicorn app.main:app --reload")
        print_info("2. Ingestar PDFs: python ingest_pdfs.py")
        print_info("3. Hacer consultas: curl -X POST http://localhost:8000/ask ...")
    else:
        print_warning("⚠️  Hay algunos problemas que debes solucionar")
        print_info("\nRevisa los errores marcados con ❌ arriba")

    print("="*60 + "\n")


# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================
async def main():
    """
    Función principal: ejecuta los 8 checks en secuencia y muestra el resumen.

    Los checks se ejecutan en orden de dependencia lógica:
    1. Python y dependencias primero (sin estas nada funciona)
    2. Servicios externos (Ollama, Docker, ChromaDB)
    3. Estructura local del proyecto
    4. API (último porque depende de todo lo anterior)

    Nota: los checks se ejecutan secuencialmente (no en paralelo) porque
    el output debe ser legible y ordenado en la terminal.
    """
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     🧪 VERIFICACIÓN DE SETUP - BIBLIOTECARIO-IA 🧪      ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")

    # Diccionario para almacenar resultados: nombre → True/False
    results = {}

    # Ejecutar checks en secuencia
    results['python'] = check_python_version()
    results['dependencies'] = check_dependencies()
    results['ollama'] = check_ollama()
    results['docker'] = check_docker()
    results['chromadb'] = check_chromadb()
    results['structure'] = check_project_structure()
    results['data'] = check_data_directory()
    results['api'] = await check_api_health()   # Único check async

    # Resumen final con conteo de pasados/fallidos
    print_summary(results)

    # Exit code: 0 = todo OK, 1 = hay errores.
    # Permite usar el script en scripts de automatización:
    #   python verify_setup.py && echo "Todo listo"
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


# ============================================================================
# BLOQUE DE ENTRADA
# ============================================================================
# Mismo patrón que en los otros scripts CLI del proyecto.
# asyncio.run() es necesario porque check_api_health() es async.
# El exit code 130 para KeyboardInterrupt es la convención Unix
# (128 + número de señal SIGINT = 2).
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Verificación interrumpida por el usuario{Colors.ENDC}")
        sys.exit(130)     # Convención Unix: 128 + SIGINT(2)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error inesperado: {e}{Colors.ENDC}")
        sys.exit(1)
