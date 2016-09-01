#!/usr/bin/env python
# coding=utf-8

from setuptools import setup


package_name = 'httpstat'
filename = package_name + '.py'


def get_version():
    import ast

    with open(filename) as input_file:
        for line in input_file:
            if line.startswith('__version__'):
                return ast.parse(line).body[0].value.s


def get_long_description():
    try:
        with open('README.md', 'r') as f:
            return f.read()
    except IOError:
        return ''


setup(
    name=package_name,
    version=get_version(),
    author='reorx',
    author_email='novoreorx@gmail.com',
    description='curl statistics made simple',
    url='https://github.com/reorx/httpstat',
    long_description=get_long_description(),
    py_modules=[package_name],
    entry_points={
        'console_scripts': [
            'httpstat = httpstat:main'
        ]
    },
    license='License :: OSI Approved :: MIT License',
)
