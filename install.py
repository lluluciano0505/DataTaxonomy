"""
install.py — Setup helper script
Run this once to prepare your environment

Usage:
    python install.py
"""

import os
import sys
import subprocess
from pathlib import Path


def main():
    print("\n🎯 DataTaxonomy Installation Helper\n")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print("❌ Python 3.9+ required")
        sys.exit(1)
    
    print("✅ Python version OK")
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Create .env if not exists
    env_file = Path(".env")
    if not env_file.exists():
        print("\n📝 Creating .env file...")
        subprocess.run(["cp", ".env.example", ".env"], check=True)
        print("⚠️  Please edit .env and add your OPENROUTER_API_KEY")
    else:
        print("✅ .env already exists")
    
    # Make startup.sh executable
    startup = Path("startup.sh")
    if startup.exists():
        startup.chmod(0o755)
        print("✅ startup.sh is executable")
    
    print("\n" + "="*60)
    print("✅ Installation complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Edit .env and add your OPENROUTER_API_KEY")
    print("2. Edit config.yaml to set your project")
    print("3. Run: python main.py")
    print("\nOr read QUICKSTART.md for detailed instructions.\n")


if __name__ == "__main__":
    main()
