#!/usr/bin/env python3
"""Script de configuração inicial do ScentSearch Scraper."""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent


def check_python_version():
    if sys.version_info < (3, 11):
        print("ERRO: Python 3.11+ é necessário.")
        sys.exit(1)
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} - OK")


def install_dependencies():
    print("\nInstalando dependências...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERRO ao instalar: {result.stderr}")
        sys.exit(1)
    print("Dependências instaladas com sucesso!")


def install_playwright():
    print("\nInstalando browsers do Playwright...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Aviso: Playwright não pôde ser instalado: {result.stderr}")
        print("Os scrapers baseados em HTTP ainda funcionarão.")
    else:
        print("Playwright instalado com sucesso!")


def create_env_file():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        print("\n.env já existe, pulando criação.")
        return

    example = BASE_DIR / ".env.example"
    if example.exists():
        env_file.write_text(example.read_text())
        print("\nArquivo .env criado a partir do .env.example")
        print("Edite o arquivo .env com suas configurações.")
    else:
        print("\nAviso: .env.example não encontrado.")


def create_directories():
    dirs = [
        BASE_DIR / "data",
        BASE_DIR / "logs",
    ]
    for d in dirs:
        d.mkdir(exist_ok=True)
    print("\nDiretórios criados: data/, logs/")


def init_database():
    print("\nInicializando banco de dados...")
    sys.path.insert(0, str(BASE_DIR))
    try:
        from database.db import init_db
        init_db()
        print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"ERRO ao inicializar banco: {e}")


def main():
    print("=" * 50)
    print("ScentSearch Scraper - Setup Inicial")
    print("=" * 50)

    check_python_version()
    create_directories()
    install_dependencies()
    install_playwright()
    create_env_file()
    init_database()

    print("\n" + "=" * 50)
    print("Setup concluído com sucesso!")
    print("=" * 50)
    print("\nPara iniciar o painel de controle:")
    print("  python main.py")
    print("\nPara executar um scrape manualmente:")
    print("  python -c \"from scrapers.manager import ScrapingManager; ScrapingManager().run_all()\"")
    print("\nAcesse o painel em: http://localhost:8000")


if __name__ == "__main__":
    main()
