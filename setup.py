#!/usr/bin/env python3

import os

from setuptools import find_packages, setup

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
with open(os.path.join(this_directory, 'requirements.txt'), encoding='utf-8') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="kato",
    version="3.0.2",
    description="Knowledge Abstraction for Traceable Outcomes - Transparent memory and abstraction for agentic AI systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="KATO Development Team",
    author_email="kato@intelligent-artifacts.com",
    url="https://github.com/intelligent-artifacts/kato",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="ai artificial-intelligence machine-learning explainable-ai transparency memory abstraction",
    project_urls={
        "Documentation": "https://github.com/intelligent-artifacts/kato/blob/main/README.md",
        "Source": "https://github.com/intelligent-artifacts/kato",
        "Tracker": "https://github.com/intelligent-artifacts/kato/issues",
    },
    entry_points={
        "console_scripts": [
            # FastAPI service runs via uvicorn, no console scripts needed
        ],
    },
    package_data={
        "kato": [
            "**/*.py",
        ],
    },
    zip_safe=False,
)
