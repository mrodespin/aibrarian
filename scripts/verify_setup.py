#!/usr/bin/env python3
# /scripts/verify_setup.py
"""
Environment Verification Script - Bibliotecario-IA

This script checks that all the services and dependencies needed to run
Bibliotecario-IA are correctly installed and configured.

When should you use this script?
- After cloning the repository on a new machine
- When something isn't working and you want to check the environment is correct
- Before running the API for the first time

Checks it performs (11 total):
    1. Python version (3.11+ required)
    2. Python dependencies installed
    3. Ollama: installation, service and models
    4. Docker: installation and daemon running
    5. ChromaDB: service availability
    6. Postgres: availability + DATABASE_URL/JWT_SECRET_KEY in api/.env
    7. Project structure: required directories
    8. Data directory: presence of PDFs
    9. API: health check (optional, doesn't fail if not running)
    10. Node.js: version 18+ (for the frontend)
    11. Frontend: dependencies installed (node_modules)

Note about relative paths:
    This script runs from the scripts/ directory and uses paths relative
    to the project root.

Usage:
    python scripts/verify_setup.py
    # or from scripts/
    cd scripts && python verify_setup.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
import sys
import subprocess
import asyncio
import socket
from pathlib import Path
from urllib.parse import urlparse

# ============================================================================
# TERMINAL COLORS
# ============================================================================
# ANSI codes to color the terminal output.
# These codes are escape sequences that terminal emulators interpret to
# change the text color.
# Format: \033[<code>m  where \033 is the ESC (escape) character.
#
# JS/Node.js equivalent: chalk.green(), chalk.red(), etc.
class Colors:
    GREEN = '\033[92m'    # Green (success)
    RED = '\033[91m'      # Red (error)
    YELLOW = '\033[93m'   # Yellow (warning)
    BLUE = '\033[94m'     # Blue (info)
    ENDC = '\033[0m'      # Reset: back to the default color
    BOLD = '\033[1m'      # Bold


# ============================================================================
# OUTPUT FORMATTING FUNCTIONS
# ============================================================================
# Each function wraps the text with the appropriate color codes.
# The pattern is always: color + emoji + text + ENDC (reset).
def print_header(text):
    """Prints a visually distinct header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    """Prints a success message in green."""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text):
    """Prints an error message in red."""
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_warning(text):
    """Prints a warning message in yellow."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text):
    """Prints an informational message in blue."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


# ============================================================================
# VERIFICATION CHECKS
# ============================================================================
# Each function checks one aspect of the environment and returns True/False.
# They all follow the same pattern:
#   1. Print a numbered header
#   2. Perform the check
#   3. Print the result (success/error) with guidance if it fails
#   4. Return a boolean for the final summary

def check_python_version():
    """
    Checks that the Python version is 3.11 or higher.

    Why 3.11+?
    The project uses modern Python features like ExceptionGroup (3.11)
    and significant performance improvements. FastAPI and LangChain also
    recommend recent versions.

    Returns:
        bool: True if the version is compatible
    """
    print_header("1. Checking Python")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    print_info(f"Python version: {version_str}")

    if version.major >= 3 and version.minor >= 11:
        print_success(f"Python {version_str} is compatible")
        return True
    else:
        print_error(f"Python {version_str} is too old. 3.11+ is required")
        return False


def check_dependencies():
    """
    Checks that the main Python dependencies are installed.

    Strategy:
    1. Detect whether the script is running from a virtual environment
    2. If NOT: check the venv at api/venv/ by looking at site-packages
    3. If YES: check by importing the packages normally

    This lets the script run without activating the venv and still
    verify that the dependencies are installed.

    Returns:
        bool: True if all packages are installed
    """
    print_header("2. Checking Python Dependencies")

    # Detect whether we're inside a virtual environment
    # sys.real_prefix exists in old-style virtualenv
    # sys.base_prefix != sys.prefix in modern venv (Python 3.3+)
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )

    project_root = Path(__file__).parent.parent
    venv_path = project_root / "api" / "venv"

    required_packages = [
        'fastapi', 'uvicorn', 'langchain', 'chromadb', 'pydantic', 'httpx',
        # Added alongside observability and auth (see api/requirements.txt);
        # before this, the check passed green even if these 5 were missing.
        'structlog', 'prometheus_client', 'asyncpg', 'bcrypt', 'jwt',
    ]

    # The import name ('jwt') doesn't match either the PyPI distribution
    # name ('PyJWT') or its .dist-info prefix ('pyjwt'). Every other
    # package in the list does match (aside from hyphen/underscore, which
    # the code below already normalizes), so this is the only case that
    # needs an override.
    DIST_NAME_OVERRIDES = {'jwt': 'PyJWT'}

    if not in_venv:
        # Not in a venv, check whether api/venv exists
        if not venv_path.exists():
            print_error("Virtual environment NOT found at api/venv/")
            print_info("Run: python3 scripts/setup.py")
            return False

        print_info(f"Virtual environment: {venv_path.relative_to(project_root)}")
        print_warning("Not inside the venv (that's OK, checking packages anyway...)")

        # Look for the venv's site-packages
        site_packages_candidates = list((venv_path / "lib").glob("python*/site-packages"))

        if not site_packages_candidates:
            print_error("site-packages not found in the venv")
            return False

        site_packages = site_packages_candidates[0]
        all_ok = True

        for package in required_packages:
            # Look for the package in site-packages
            # It can be a directory or a .dist-info
            display_name = DIST_NAME_OVERRIDES.get(package, package)
            package_normalized = package.replace('-', '_')
            dist_prefix = DIST_NAME_OVERRIDES.get(package, package_normalized).replace('-', '_').lower()
            package_dir = site_packages / package_normalized
            dist_info = list(site_packages.glob(f"{dist_prefix}*.dist-info"))

            if package_dir.exists() or dist_info:
                print_success(f"{display_name} installed")
            else:
                print_error(f"{display_name} NOT installed")
                all_ok = False

        if not all_ok:
            print_warning("Install dependencies:")
            print_info("  cd api && source venv/bin/activate")
            print_info("  pip install -r requirements.txt")

        return all_ok

    # We're inside the venv, check by importing directly
    print_success("Running from virtual environment ✓")

    all_ok = True
    for package in required_packages:
        display_name = DIST_NAME_OVERRIDES.get(package, package)
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{display_name} installed")
        except ImportError:
            print_error(f"{display_name} NOT installed")
            all_ok = False

    if not all_ok:
        print_warning("Run: pip install -r requirements.txt")

    return all_ok


def check_ollama():
    """
    Checks Ollama at three levels: installation, service and models.

    This is the most complex check because Ollama has two parts:
    1. The CLI tool (ollama --version)
    2. The background server (ollama serve → port 11434)

    It also checks that the required models are downloaded:
    - llama3.2: LLM model for generating responses
    - nomic-embed-text: embedding model for semantic search

    Why subprocess for the installation but httpx for the service?
    - subprocess: check whether the 'ollama' binary exists on PATH
    - httpx: check whether the HTTP server is running and responds

    Returns:
        bool: True if Ollama is installed and the service is running.
              Missing models produce a warning, not an error.
    """
    print_header("3. Checking Ollama")

    # --- Level 1: Binary installed ---
    try:
        result = subprocess.run(
            ['ollama', '--version'],
            capture_output=True,   # Capture stdout and stderr
            text=True,             # Return strings, not bytes
            timeout=5              # TimeoutExpired if it doesn't respond in 5s
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Ollama installed: {version}")
        else:
            print_error("Ollama installed but not responding correctly")
            return False
    except FileNotFoundError:
        # FileNotFoundError: the 'ollama' command doesn't exist on PATH
        print_error("Ollama is NOT installed")
        print_info("Install it from: https://ollama.ai")
        return False
    except subprocess.TimeoutExpired:
        print_error("Ollama isn't responding (timeout)")
        return False

    # --- Level 2: Service running ---
    # If we got here, Ollama is installed. Now check that the server
    # (ollama serve) is active.
    try:
        import httpx
        # GET /api/tags returns the list of downloaded models.
        # If the service isn't running, the connection fails.
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            print_success("Ollama service is running")

            # --- Level 3: Downloaded models ---
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]

            # Ollama model names can include tags (e.g. 'llama3.2:latest'),
            # hence 'in' instead of an exact comparison
            required_models = ['llama3.2', 'nomic-embed-text']
            for model in required_models:
                if any(model in name for name in model_names):
                    print_success(f"Model {model} downloaded")
                else:
                    # Warning, not error: the service works but the
                    # models will be missing when using the system
                    print_warning(f"Model {model} NOT downloaded")
                    print_info(f"   Run: ollama pull {model}")

            return True
        else:
            print_error(f"Ollama responds with code: {response.status_code}")
            return False
    except Exception as e:
        print_error("Ollama service is NOT running")
        print_info("Run in another terminal: ollama serve")
        return False


def check_docker():
    """
    Checks Docker at two levels: installation and daemon running.

    Why check the daemon separately?
    On macOS/Windows, Docker Desktop can be installed but not started.
    'docker --version' works without the daemon, but 'docker ps' requires
    the daemon to be running.

    Returns:
        bool: True if Docker is installed and running
    """
    print_header("4. Checking Docker")

    # --- Level 1: Installation ---
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Docker installed: {version}")
        else:
            print_error("Docker installed but not responding")
            return False
    except FileNotFoundError:
        print_error("Docker is NOT installed")
        print_info("Install Docker Desktop from: https://www.docker.com/products/docker-desktop")
        return False

    # --- Level 2: Daemon running ---
    # 'docker ps' lists containers. Fails if the daemon isn't running.
    try:
        result = subprocess.run(
            ['docker', 'ps'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success("Docker is running")
            return True
        else:
            print_error("Docker is not running")
            print_info("Start Docker Desktop")
            return False
    except subprocess.TimeoutExpired:
        print_error("Docker isn't responding (timeout)")
        return False


def check_chromadb():
    """
    Checks that ChromaDB is running and responds to the heartbeat.

    ChromaDB exposes an /api/v2/heartbeat endpoint that returns 200 if
    the service is active. It's the equivalent of a health check.
    (v1 of this endpoint was retired — it returns 410 Gone since ChromaDB 1.x)

    Note: ChromaDB runs on port 8001 (not the default 8000) to avoid
    conflicting with the FastAPI API.

    Returns:
        bool: True if ChromaDB responds to the heartbeat
    """
    print_header("5. Checking ChromaDB")

    try:
        import httpx
        response = httpx.get("http://localhost:8001/api/v2/heartbeat", timeout=5.0)
        if response.status_code == 200:
            print_success("ChromaDB is running and responding")
            return True
        else:
            print_error(f"ChromaDB responds with code: {response.status_code}")
            return False
    except Exception as e:
        print_error("ChromaDB is NOT running")
        print_info("Run: docker-compose up -d chromadb")
        return False


def check_postgres():
    """
    Checks Postgres (users/authentication) and that api/.env has
    DATABASE_URL/JWT_SECRET_KEY configured.

    There's no signup UI in the frontend: logging in requires at least
    one user created with scripts/create_user.py, which in turn requires
    Postgres to be up and DATABASE_URL configured. Without this, the
    whole app is unusable even if the rest of the environment is
    perfect — that's why this is a required check, not optional like
    the API one.

    Unlike check_chromadb() (a real HTTP heartbeat), here we only check
    that the port accepts TCP connections: Postgres doesn't speak HTTP,
    and adding asyncpg (the project's driver) just for this check would
    couple a generic infrastructure script to an app-specific dependency.

    Returns:
        bool: True if api/.env has DATABASE_URL/JWT_SECRET_KEY and
              Postgres responds on the configured host:port.
    """
    print_header("6. Checking Postgres (users/authentication)")

    project_root = Path(__file__).parent.parent
    env_file = project_root / 'api' / '.env'

    if not env_file.exists():
        print_error("api/.env does NOT exist")
        print_info("Run: python3 scripts/setup.py")
        return False

    # Simple KEY=VALUE parsing, same as setup.py does when generating
    # the file — no need for python-dotenv here.
    env_vars = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        env_vars[key.strip()] = value.strip()

    database_url = env_vars.get('DATABASE_URL')
    if not database_url:
        print_error("DATABASE_URL is not configured in api/.env")
        return False
    print_success("DATABASE_URL configured")

    jwt_secret = env_vars.get('JWT_SECRET_KEY')
    if not jwt_secret:
        print_error("JWT_SECRET_KEY is not configured in api/.env")
        return False
    if jwt_secret == 'change-me-generate-a-random-secret':
        print_warning("JWT_SECRET_KEY is still the placeholder from .env.example")
        print_info('Generate your own: python3 -c "import secrets; print(secrets.token_hex(32))"')
    else:
        print_success("JWT_SECRET_KEY configured")

    # Raw TCP connection to DATABASE_URL's host:port. Doesn't validate
    # credentials or that the `users` table exists (create_user.py does
    # that when it connects) — only that Postgres is listening.
    try:
        parsed = urlparse(database_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 5432
        with socket.create_connection((host, port), timeout=3):
            print_success(f"Postgres responds at {host}:{port}")
            return True
    except Exception as e:
        print_error(f"Postgres is NOT responding: {e}")
        print_info("Run: docker-compose up -d postgres")
        return False


def check_project_structure():
    """
    Checks that the project's main directories exist.

    Checks the directories the system needs to work:
    - api/app/core: business logic
    - api/app/adapters: concrete implementations
    - api/app/config: configuration
    - data: PDF directory

    Returns:
        bool: True if all directories exist
    """
    print_header("7. Checking Project Structure")

    # Compute paths from the script's location
    project_root = Path(__file__).parent.parent

    required_dirs = [
        project_root / 'api' / 'app' / 'core',
        project_root / 'api' / 'app' / 'adapters',
        project_root / 'api' / 'app' / 'config',
        project_root / 'data'
    ]

    all_ok = True
    for path in required_dirs:
        # Show the relative path for readability
        rel_path = path.relative_to(project_root)
        if path.exists():
            print_success(f"Directory {rel_path} exists")
        else:
            print_error(f"Directory {rel_path} does NOT exist")
            all_ok = False

    return all_ok


def check_data_directory():
    """
    Checks the contents of the data directory.

    Unlike the other checks: this does NOT fail if there are no PDFs.
    An empty data directory is a valid environment (simply no documents
    have been ingested yet). It only fails if the directory itself
    doesn't exist.

    Returns:
        bool: True if the directory exists (regardless of its contents)
    """
    print_header("8. Checking Data Directory")

    # Compute the path from the script's location
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data'

    if not data_dir.exists():
        print_error("Directory /data does NOT exist")
        return False

    pdf_files = list(data_dir.glob('*.pdf'))

    if pdf_files:
        print_success(f"Found {len(pdf_files)} PDF files")
        # Show only the first 5 to avoid flooding the terminal
        for pdf in pdf_files[:5]:
            print_info(f"   - {pdf.name}")
        if len(pdf_files) > 5:
            print_info(f"   ... and {len(pdf_files) - 5} more")
    else:
        # Warning, not error: the directory exists but is empty
        print_warning("No PDF files in /data")
        print_info("Copy some PDFs to test the system")

    return True


async def check_api_health():
    """
    Checks the FastAPI API's health check (optional check).

    This is the script's only async function because it uses
    httpx.AsyncClient. All other checks are synchronous (subprocess or
    sync httpx).

    Why is it optional?
    The API doesn't have to be running for the environment to be
    considered configured. It's an informational check: if the API is
    active, it verifies its internal connections (Ollama, ChromaDB)
    work from its own perspective.

    Returns:
        bool: True if the API is running and responds. False in any
              other case, but that is NOT treated as a critical error.
    """
    print_header("9. Checking API (optional)")

    try:
        import httpx
        # AsyncClient: async version of httpx, for use with await
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                print_success("API is running")

                # The /health endpoint returns the status of the
                # services the API can see (Ollama and ChromaDB)
                services = data.get('services', {})
                if services.get('ollama'):
                    print_success("  API can connect to Ollama")
                else:
                    print_warning("  API can NOT connect to Ollama")

                if services.get('chromadb'):
                    print_success("  API can connect to ChromaDB")
                else:
                    print_warning("  API can NOT connect to ChromaDB")

                return True
            else:
                print_warning(f"API responds with code: {response.status_code}")
                return False
    except Exception as e:
        # Not an error: the API simply isn't running
        print_warning("API is NOT running (this is normal if you haven't started it)")
        print_info("To start it: docker-compose up -d")
        return False


def check_nodejs():
    """
    Checks that Node.js is installed and is version 18+.

    Why Node.js 18+?
    The frontend uses Vite 7 and React 19, which require Node.js 18 or
    higher. Node.js 18+ guarantees compatibility with ESModules and
    modern APIs.

    Returns:
        bool: True if Node.js 18+ is installed
    """
    print_header("10. Checking Node.js")

    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()  # e.g., "v20.11.0"
            print_info(f"Node.js version: {version_str}")

            # Parse the version (strip the leading 'v')
            version_parts = version_str.lstrip('v').split('.')
            major_version = int(version_parts[0])

            if major_version >= 18:
                print_success(f"Node.js {version_str} is compatible")

                # Also check npm
                try:
                    npm_result = subprocess.run(
                        ['npm', '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if npm_result.returncode == 0:
                        print_success(f"npm {npm_result.stdout.strip()} installed")
                except:
                    print_warning("npm not found (should ship with Node.js)")

                return True
            else:
                print_error(f"Node.js {version_str} is too old. 18+ is required")
                print_info("Update Node.js: https://nodejs.org/")
                print_info("Or use nvm/fnm: nvm install 20")
                return False
        else:
            print_error("Node.js isn't responding correctly")
            return False
    except FileNotFoundError:
        print_error("Node.js is NOT installed")
        print_info("Install it from: https://nodejs.org/")
        print_info("Or use nvm: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash")
        return False
    except subprocess.TimeoutExpired:
        print_error("Node.js isn't responding (timeout)")
        return False


def check_frontend():
    """
    Checks that the frontend is correctly configured.

    Checks:
    1. That the frontend/ directory exists
    2. That package.json exists
    3. That node_modules is installed (npm install has run)

    Returns:
        bool: True if the frontend is ready to use
    """
    print_header("11. Checking Frontend")

    project_root = Path(__file__).parent.parent
    frontend_dir = project_root / 'frontend'

    # Check 1: frontend directory exists
    if not frontend_dir.exists():
        print_error("Directory frontend/ does NOT exist")
        print_info("Clone the full repository or run setup.py")
        return False

    print_success("Directory frontend/ exists")

    # Check 2: package.json exists
    package_json = frontend_dir / 'package.json'
    if not package_json.exists():
        print_error("package.json NOT found in frontend/")
        return False

    print_success("package.json found")

    # Check 3: node_modules exists (dependencies installed)
    node_modules = frontend_dir / 'node_modules'
    if not node_modules.exists():
        print_warning("node_modules NOT found")
        print_info("Dependencies aren't installed")
        print_info("Run: cd frontend && npm install")
        return False

    # Check that it has content (isn't empty)
    if not any(node_modules.iterdir()):
        print_warning("node_modules is empty")
        print_info("Run: cd frontend && npm install")
        return False

    print_success("Frontend dependencies installed (node_modules)")

    # Check 4 (optional): check that react is installed
    react_dir = node_modules / 'react'
    if react_dir.exists():
        print_success("React installed correctly")
    else:
        print_warning("React not found in node_modules")

    return True


# ============================================================================
# RESULTS SUMMARY
# ============================================================================
def print_summary(results, optional_results):
    """
    Prints a summary of all checks and the next steps.

    Args:
        results: Dict {check_name: bool} with the required results
        optional_results: Dict {check_name: bool} with the optional results
    """
    print_header("Verification Summary")

    # Only count required checks for pass/fail
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    failed = total - passed

    print(f"Required checks: {total}")
    print_success(f"Passed: {passed}")
    if failed > 0:
        print_error(f"Failed: {failed}")

    # Show optional checks separately
    if optional_results:
        optional_passed = sum(1 for r in optional_results.values() if r)
        print_info(f"Optional checks: {len(optional_results)} ({optional_passed} active)")

    print("\n" + "="*60)

    if failed == 0:
        # Everything is fine: show the next steps to use the system
        print_success("🎉 EVERYTHING IS CORRECTLY CONFIGURED!")
        print_info("\nNext steps:")
        print_info("1. Start Ollama: ollama serve")
        print_info("2. Start Docker: docker-compose up -d")
        print_info("3. Create your user (no signup in the frontend):")
        print_info("   python scripts/create_user.py --email you@email.com")
        print_info("4. Start the Frontend: cd frontend && npm run dev")
        print_info("5. Open in your browser: http://localhost:5173")
        print_info("6. Ingest PDFs from the UI or with: python scripts/ingest_pdfs.py")
    else:
        print_warning("⚠️  There are some issues you need to fix")
        print_info("\nCheck the errors marked with ❌ above")

    print("="*60 + "\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
async def main():
    """
    Main function: runs all 11 checks in sequence and shows the summary.

    Checks run in order of logical dependency:
    1. Python and dependencies first (nothing works without these)
    2. External services (Ollama, Docker, ChromaDB, Postgres)
    3. Local project structure
    4. API (last of the backend checks)
    5. Node.js and frontend (for the web UI)

    Note: checks run sequentially (not in parallel) so the terminal
    output stays readable and ordered.
    """
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     🧪 SETUP VERIFICATION - BIBLIOTECARIO-IA 🧪          ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")

    # Dicts to store results: name -> True/False
    results = {}           # Required checks
    optional_results = {}  # Optional checks (don't affect the exit code)

    # Run checks in sequence
    # Backend checks (required)
    results['python'] = check_python_version()
    results['dependencies'] = check_dependencies()
    results['ollama'] = check_ollama()
    results['docker'] = check_docker()
    results['chromadb'] = check_chromadb()
    results['postgres'] = check_postgres()
    results['structure'] = check_project_structure()
    results['data'] = check_data_directory()

    # Optional check: API (informational only)
    optional_results['api'] = await check_api_health()

    # Frontend checks (required)
    results['nodejs'] = check_nodejs()
    results['frontend'] = check_frontend()

    # Final summary with passed/failed count
    print_summary(results, optional_results)

    # Exit code: 0 = everything OK, 1 = there are errors in REQUIRED checks
    # Optional checks don't affect the exit code
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


# ============================================================================
# ENTRY POINT
# ============================================================================
# Same pattern as the project's other CLI scripts.
# asyncio.run() is needed because check_api_health() is async.
# Exit code 130 for KeyboardInterrupt is the Unix convention
# (128 + signal number SIGINT = 2).
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Verification interrupted by user{Colors.ENDC}")
        sys.exit(130)     # Unix convention: 128 + SIGINT(2)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Unexpected error: {e}{Colors.ENDC}")
        sys.exit(1)
