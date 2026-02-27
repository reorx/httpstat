#!/usr/bin/env python3

from pathlib import Path

from setuptools import setup


PACKAGE_NAME = "httpstat"
MODULE_FILE = Path(__file__).with_name(f"{PACKAGE_NAME}.py")


def get_version():
    for line in MODULE_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("__version__ not found")


setup(
    name=PACKAGE_NAME,
    version=get_version(),
    author="reorx",
    author_email="novoreorx@gmail.com",
    description="curl statistics made simple",
    url="https://github.com/reorx/httpstat",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    py_modules=[PACKAGE_NAME],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": ["httpstat = httpstat:main"],
    },
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
