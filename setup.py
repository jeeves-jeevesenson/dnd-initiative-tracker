"""Setup script for D&D Initiative Tracker."""

from setuptools import setup, find_packages
import os

# Read requirements
with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read README for long description
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="dnd-initiative-tracker",
    version="41.0.0",
    author="Jeeves Jeevesenson",
    description="D&D 5e Initiative Tracker and Combat Management System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jeeves-jeevesenson/dnd-initiative-tracker",
    packages=find_packages(),
    py_modules=["dnd_initative_tracker", "helper_script"],
    install_requires=requirements,
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "dnd-initiative-tracker=dnd_initative_tracker:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": [
            "Monsters/*.yaml",
            "Spells/*.yaml",
            "assets/*",
            "players/*.yaml",
            "presets/*.yaml",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment :: Role-Playing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    keywords="dnd dungeons dragons initiative tracker combat 5e tabletop rpg",
)
