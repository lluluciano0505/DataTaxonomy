"""
setup.py — Installation configuration for DataTaxonomy

Install in development mode:
    pip install -e .

Install with all dependencies:
    pip install -e ".[dev]"
"""

from setuptools import setup, find_packages

setup(
    name="datataxonomy",
    version="0.1.0",
    description="Intelligent file classification and asset taxonomy for architecture projects",
    author="DataTaxonomy Contributors",
    python_requires=">=3.9",
    packages=find_packages(),
    install_requires=[
        "openai>=1.0",
        "pypdf>=4.0",
        "python-docx>=0.8",
        "python-pptx>=0.6",
        "pandas>=2.0",
        "pillow>=10.0",
        "python-dotenv>=1.0",
        "pyyaml>=6.0",
        "streamlit>=1.28",
        "plotly>=5.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "black>=23.0",
            "flake8>=6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "datataxonomy=main:main",
        ],
    },
)
