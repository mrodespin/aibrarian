#!/usr/bin/env python3
# /api/verify_setup.py

"""
Script de verificación del setup del sistema Bibliotecario-IA.
Verifica que todos los servicios y dependencias estén correctamente configurados.
"""

import sys
import subprocess
import asyncio
from pathlib import Path

# Colores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


def check_python_version():
    """Verificar versión de Python."""
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
    """Verificar que las dependencias estén instaladas."""
    print_header("2. Verificando Dependencias Python")

    required_packages = [
        'fastapi',
        'uvicorn',
        'langchain',
        'chromadb',
        'pydantic',
        'httpx'
    ]

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
    """Verificar instalación y estado de Ollama."""
    print_header("3. Verificando Ollama")

    # Verificar instalación
    try:
        result = subprocess.run(
            ['ollama', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Ollama instalado: {version}")
        else:
            print_error("Ollama instalado pero no responde correctamente")
            return False
    except FileNotFoundError:
        print_error("Ollama NO está instalado")
        print_info("Instala desde: https://ollama.ai")
        return False
    except subprocess.TimeoutExpired:
        print_error("Ollama no responde (timeout)")
        return False

    # Verificar servicio
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            print_success("Servicio Ollama está corriendo")

            # Verificar modelos
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]

            required_models = ['llama3.2', 'nomic-embed-text']
            for model in required_models:
                if any(model in name for name in model_names):
                    print_success(f"Modelo {model} descargado")
                else:
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
    """Verificar Docker."""
    print_header("4. Verificando Docker")

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

    # Verificar que Docker está corriendo
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
    """Verificar ChromaDB."""
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
    """Verificar estructura del proyecto."""
    print_header("6. Verificando Estructura del Proyecto")

    required_dirs = [
        'app/core',
        'app/adapters',
        'app/config',
        '../data'
    ]

    all_ok = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print_success(f"Directorio {dir_path} existe")
        else:
            print_error(f"Directorio {dir_path} NO existe")
            all_ok = False

    return all_ok


def check_data_directory():
    """Verificar directorio de datos."""
    print_header("7. Verificando Directorio de Datos")

    data_dir = Path('../data')
    if not data_dir.exists():
        print_error("Directorio /data NO existe")
        return False

    pdf_files = list(data_dir.glob('*.pdf'))

    if pdf_files:
        print_success(f"Encontrados {len(pdf_files)} archivos PDF")
        for pdf in pdf_files[:5]:  # Mostrar primeros 5
            print_info(f"   - {pdf.name}")
        if len(pdf_files) > 5:
            print_info(f"   ... y {len(pdf_files) - 5} más")
    else:
        print_warning("No hay archivos PDF en /data")
        print_info("Copia algunos PDFs para probar el sistema")

    return True


async def check_api_health():
    """Verificar health de la API (si está corriendo)."""
    print_header("8. Verificando API (opcional)")

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                print_success("API está corriendo")

                # Verificar servicios
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
        print_warning("API NO está corriendo (esto es normal si no la has iniciado)")
        print_info("Para iniciar: uvicorn app.main:app --reload")
        return False


def print_summary(results):
    """Imprimir resumen de resultados."""
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
        print_success("🎉 ¡TODO ESTÁ CONFIGURADO CORRECTAMENTE!")
        print_info("\nPróximos pasos:")
        print_info("1. Iniciar API: uvicorn app.main:app --reload")
        print_info("2. Ingestar PDFs: python ingest_pdfs.py")
        print_info("3. Hacer consultas: curl -X POST http://localhost:8000/ask ...")
    else:
        print_warning("⚠️  Hay algunos problemas que debes solucionar")
        print_info("\nRevisa los errores marcados con ❌ arriba")

    print("="*60 + "\n")


async def main():
    """Función principal."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     🧪 VERIFICACIÓN DE SETUP - BIBLIOTECARIO-IA 🧪      ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")

    results = {}

    # Ejecutar checks
    results['python'] = check_python_version()
    results['dependencies'] = check_dependencies()
    results['ollama'] = check_ollama()
    results['docker'] = check_docker()
    results['chromadb'] = check_chromadb()
    results['structure'] = check_project_structure()
    results['data'] = check_data_directory()
    results['api'] = await check_api_health()

    # Resumen
    print_summary(results)

    # Exit code
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Verificación interrumpida por el usuario{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error inesperado: {e}{Colors.ENDC}")
        sys.exit(1)
