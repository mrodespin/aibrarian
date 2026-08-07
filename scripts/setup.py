#!/usr/bin/env python3
# /scripts/setup.py
"""
Automated Installation Script - Bibliotecario-IA

This script automates the full development environment setup.
It detects what's already installed and what's missing, then only
installs what's needed.

Configuration:
- Ollama: Native on macOS (Metal GPU access, ~10x faster)
- ChromaDB + Postgres: Docker (persistence via volumes)
- API: Docker (hot-reload via volume mount)
- Frontend: React + Vite (npm run dev)

What does it do? (the number matches the header you'll see on screen)
1. Checks the operating system (macOS)
2. Checks internet connectivity
3. Checks/installs Homebrew
4. Installs Ollama and downloads models
5. Checks Docker (installation + daemon running)
6. Sets up the Python environment (venv + dependencies for the CLI scripts)
7. Creates the .env file (with a generated JWT_SECRET_KEY, not the placeholder)
8. Starts the Docker services (ChromaDB + Postgres + API)
9. Sets up the Frontend (Node.js 18+ + npm install)
10. Runs verify_setup.py to confirm everything
11. Creates your user (no signup in the frontend, see create_user.py)

Usage:
    python3 scripts/setup.py
"""

import sys
import subprocess
import platform
import shutil
from pathlib import Path

# ============================================================================
# TERMINAL COLORS
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
    print("║     🚀 SETUP - BIBLIOTECARIO-IA 🚀                       ║")
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
    choices = " [Y/n]: " if default else " [y/N]: "
    choice = input(f"{Colors.CYAN}{question}{choices}{Colors.ENDC}").lower().strip()
    if choice == '':
        return default
    return choice in ['y', 'yes']


# ============================================================================
# SYSTEM CHECKS
# ============================================================================
def check_os():
    print_header("1. Checking Operating System")
    os_name = platform.system()
    print_info(f"Detected system: {os_name}")

    if os_name != "Darwin":
        print_error(f"System {os_name} is not supported. This script is for macOS.")
        print_info("For other systems, check README.md")
        return False

    print_success("macOS detected")
    return True


def check_internet():
    print_header("2. Checking Internet Connection")
    try:
        result = run_command(["ping", "-c", "1", "-W", "2000", "8.8.8.8"], check=False)
        if result.returncode == 0:
            print_success("Internet connection available")
            return True
        print_error("No internet connection")
        return False
    except Exception as e:
        print_warning(f"Could not check: {e}")
        return ask_yes_no("Continue anyway?", default=False)


# ============================================================================
# PREREQUISITE INSTALLATION
# ============================================================================
def install_homebrew():
    print_header("3. Checking Homebrew")

    if is_installed("brew"):
        print_success("Homebrew is already installed")
        return True

    print_warning("Homebrew is not installed")
    if not ask_yes_no("Install Homebrew?"):
        print_error("Homebrew is required to install Ollama")
        return False

    print_info("Installing Homebrew...")
    try:
        subprocess.run(
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            shell=True, check=True
        )
        print_success("Homebrew installed")
        return True
    except subprocess.CalledProcessError:
        print_error("Homebrew installation failed")
        return False


def install_ollama():
    print_header("4. Setting up Ollama (Native)")
    print_info("Ollama runs natively on macOS to take advantage of the Metal GPU (~10x faster)")

    if is_installed("ollama"):
        print_success("Ollama is already installed")
    else:
        print_warning("Ollama is not installed")
        if not ask_yes_no("Install Ollama with Homebrew?"):
            print_error("Ollama is required for the LLM")
            return False

        print_info("Installing Ollama...")
        try:
            run_command("brew install ollama")
            print_success("Ollama installed")
        except subprocess.CalledProcessError:
            print_error("Ollama installation failed")
            return False

    # Start the service
    print_info("Starting the Ollama service...")
    run_command("brew services start ollama", check=False)

    # Check and download models
    print_info("Checking models...")
    try:
        result = run_command("ollama list")
        models_output = result.stdout

        for model in ["llama3.2", "nomic-embed-text"]:
            if model in models_output:
                print_success(f"Model {model} available")
            else:
                print_warning(f"Downloading {model}...")
                subprocess.run(["ollama", "pull", model], check=True)
                print_success(f"Model {model} downloaded")

        return True
    except subprocess.CalledProcessError:
        print_error("Error checking Ollama models")
        return False


def install_docker():
    print_header("5. Checking Docker")

    if not is_installed("docker"):
        print_error("Docker is not installed")
        print_info("Install Docker Desktop: https://www.docker.com/products/docker-desktop")
        return False

    print_success("Docker is installed")

    # Check the daemon
    try:
        run_command("docker ps", check=True, capture_output=True)
        print_success("Docker daemon is running")
        return True
    except:
        print_error("Docker is not running. Start Docker Desktop.")
        return False


def setup_docker_services():
    print_header("8. Starting Docker Services (ChromaDB + Postgres + API)")

    try:
        # Build and start all services
        subprocess.run(
            ["docker-compose", "up", "-d", "--build"],
            check=True,
            cwd=Path(__file__).parent.parent
        )
        print_success("ChromaDB started on port 8001")
        print_success("Postgres started on port 5432")
        print_success("API started on port 8000")
        return True
    except subprocess.CalledProcessError:
        print_error("Failed to start Docker services")
        return False


# ============================================================================
# PYTHON SETUP
# ============================================================================
def setup_python():
    print_header("6. Setting up the Python Environment")

    python_version = sys.version_info
    print_info(f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")

    if python_version < (3, 11):
        print_error("Python 3.11+ is required")
        return False

    print_success("Python version is compatible")

    project_root = Path(__file__).parent.parent
    api_dir = project_root / "api"
    venv_dir = api_dir / "venv"

    # Create the venv
    if venv_dir.exists():
        print_success("Virtual environment already exists")
    else:
        print_info("Creating the virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        print_success("Virtual environment created")

    # Install dependencies
    print_info("Installing Python dependencies...")
    pip_executable = venv_dir / "bin" / "pip"
    requirements_file = api_dir / "requirements.txt"

    try:
        subprocess.run(
            [str(pip_executable), "install", "-r", str(requirements_file)],
            check=True, capture_output=True
        )
        print_success("Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Installation failed: {e.stderr}")
        return False


def setup_env_file():
    print_header("7. Setting up Environment Variables")

    api_dir = Path(__file__).parent.parent / "api"
    env_file = api_dir / ".env"
    env_example = api_dir / ".env.example"

    if env_file.exists():
        print_warning(".env already exists")
        if not ask_yes_no("Overwrite it?", default=False):
            print_info("Keeping the existing .env")
            return True

    try:
        shutil.copy(env_example, env_file)
        print_success(".env file created from .env.example")
        print_info("Config: Ollama at localhost:11434, ChromaDB at localhost:8001")

        # .env.example ships JWT_SECRET_KEY=change-me-generate-a-random-secret
        # as a documented placeholder (see the comment in that file itself).
        # We generate a real one here so nobody ends up running with that
        # example value — it's local dev only, but it costs nothing to get
        # it right from the start.
        import secrets
        jwt_secret = secrets.token_hex(32)
        with open(env_file, 'r') as f:
            content = f.read()
        content = content.replace(
            "JWT_SECRET_KEY=change-me-generate-a-random-secret",
            f"JWT_SECRET_KEY={jwt_secret}"
        )
        with open(env_file, 'w') as f:
            f.write(content)
        print_success("JWT_SECRET_KEY generated automatically")

        # Ask about Notion (optional)
        if ask_yes_no("Configure Notion credentials? (optional)", default=False):
            notion_key = input(f"{Colors.CYAN}NOTION_API_KEY: {Colors.ENDC}").strip()

            with open(env_file, 'r') as f:
                content = f.read()
            content = content.replace("NOTION_API_KEY=", f"NOTION_API_KEY={notion_key}")
            with open(env_file, 'w') as f:
                f.write(content)

            print_success("Notion configured")

        return True
    except Exception as e:
        print_error(f"Failed to create .env: {e}")
        return False


# ============================================================================
# FRONTEND SETUP
# ============================================================================
def setup_frontend():
    print_header("9. Setting up the Frontend")

    project_root = Path(__file__).parent.parent
    frontend_dir = project_root / "frontend"

    if not frontend_dir.exists():
        print_error("frontend/ directory not found")
        return False

    # Check Node.js
    if not is_installed("node"):
        print_warning("Node.js is not installed")
        print_info("The frontend requires Node.js 18+")
        if ask_yes_no("Install Node.js with Homebrew?"):
            run_command("brew install node")
            print_success("Node.js installed")
        else:
            print_info("Install Node.js manually: https://nodejs.org/")
            return True

    # Check the Node.js version (18+ required)
    try:
        result = run_command("node --version")
        version_str = result.stdout.strip().lstrip('v')
        major_version = int(version_str.split('.')[0])
        print_info(f"Node.js v{version_str} detected")

        if major_version < 18:
            print_warning(f"Node.js {major_version} is old. 18+ is required")
            print_info("Update with: brew upgrade node")
            return False

        print_success("Node.js 18+ available")
    except Exception as e:
        print_warning(f"Could not check the Node.js version: {e}")

    # Install dependencies
    node_modules = frontend_dir / "node_modules"
    if node_modules.exists() and any(node_modules.iterdir()):
        print_success("Frontend dependencies already installed")
        return True

    print_info("Installing frontend dependencies...")
    try:
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        print_success("Frontend dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print_error("npm install failed")
        return False


# ============================================================================
# FINAL VERIFICATION
# ============================================================================
def run_verification():
    print_header("10. Final Verification")

    project_root = Path(__file__).parent.parent
    verify_script = Path(__file__).parent / "verify_setup.py"
    venv_python = project_root / "api" / "venv" / "bin" / "python"

    if not verify_script.exists():
        print_warning("Verification script not found")
        return True

    print_info("Running verify_setup.py...\n")
    result = subprocess.run([str(venv_python), str(verify_script)], cwd=project_root, check=False)

    if result.returncode == 0:
        print_success("\n✨ All checks passed ✨")
    else:
        print_warning("\nCheck the warnings above")

    return True


# ============================================================================
# FIRST USER CREATION
# ============================================================================
def create_first_user():
    """
    Creates the first user in Postgres via scripts/create_user.py.

    There's no signup screen in the frontend (it's a single-user/family
    app, not a public multi-tenant one): without this step, the
    environment ends up perfectly installed but nobody can log in.
    That's why it isn't optional in the happy path, though the user
    can skip it here and do it later by hand if they prefer.
    """
    print_header("11. Creating your User")
    print_info("There's no signup in the frontend: users are created")
    print_info("exclusively with scripts/create_user.py.\n")

    if not ask_yes_no("Create your user now?"):
        print_info("You can create it later with:")
        print_info("  python scripts/create_user.py --email you@email.com")
        return True

    email = input(f"{Colors.CYAN}Email: {Colors.ENDC}").strip()
    if not email:
        print_warning("Empty email, skipping user creation")
        print_info("You can create it later with:")
        print_info("  python scripts/create_user.py --email you@email.com")
        return True

    project_root = Path(__file__).parent.parent
    venv_python = project_root / "api" / "venv" / "bin" / "python"
    create_user_script = Path(__file__).parent / "create_user.py"

    # check=False and no stdout/stderr capture: create_user.py prompts for
    # the password interactively (getpass) and needs to inherit the
    # terminal. If it fails (e.g. Postgres wasn't up in time yet, or the
    # email already exists from a previous setup.py run), don't abort the
    # whole setup because of it — it can be retried by hand afterward.
    subprocess.run(
        [str(venv_python), str(create_user_script), "--email", email],
        cwd=project_root, check=False
    )
    return True


# ============================================================================
# MAIN FUNCTION
# ============================================================================
def main():
    try:
        print_banner()

        print_info("This script sets up the development environment:")
        print_info("  - Native Ollama (Metal GPU)")
        print_info("  - ChromaDB + Postgres + API in Docker")
        print_info("  - Frontend with npm\n")

        if not ask_yes_no("Continue with the installation?"):
            print_info("Installation cancelled")
            return

        # Run the steps
        if not check_os(): return
        if not check_internet(): return
        if not install_homebrew(): return
        if not install_ollama(): return
        if not install_docker(): return
        if not setup_python(): return
        if not setup_env_file(): return
        if not setup_docker_services(): return
        setup_frontend()
        run_verification()
        create_first_user()

        # Final summary
        print_header("✨ Installation Complete ✨")

        print_success("The environment is ready")
        print_info("\n📝 To start the system:\n")
        print_info("  # Terminal 1: Ollama (keep it open)")
        print_info("  ollama serve")
        print_info("")
        print_info("  # Terminal 2: Docker (ChromaDB + Postgres + API)")
        print_info("  docker-compose up -d")
        print_info("")
        print_info("  # Terminal 3: Frontend")
        print_info("  cd frontend && npm run dev")
        print_info("")
        print_info("  🌐 Frontend: http://localhost:5173")
        print_info("  📚 API Docs: http://localhost:8000/docs")
        print_info("  💾 ChromaDB: http://localhost:8001")
        print_info("  🔑 No user yet? python scripts/create_user.py --email you@email.com")
        print_info("")
        print_info("📚 Documentation:")
        print_info("  - README.md: General guide")
        print_info("  - docs/USAGE.md: API endpoints")
        print_info("  - .ai/context.md: Project context")

    except KeyboardInterrupt:
        print("\n")
        print_warning("Installation interrupted")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
