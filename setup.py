import os
import re
import imp
from setuptools import setup


def build_install_requires(path):
    """Support pip-type requirements files"""
    basedir = os.path.dirname(path)
    with open(path) as f:
        reqs = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line[0] == '#':
                continue
            elif line.startswith('-r '):
                nested_req = line[3:].strip()
                nested_path = os.path.join(basedir, nested_req)
                reqs += build_install_requires(nested_path)
            elif line[0] == '-':
                continue
            else:
                reqs.append(line)
        return reqs


def find_files(pattern, *paths):
    regex = re.compile(pattern)
    matches = []
    for path in paths:
        for root, dirnames, filenames in os.walk(path):
            for filename in filter(regex.match, filenames):
                matches.append(os.path.join(root, filename)[len(path)+1:])
    return matches


root = os.path.dirname(__file__)
from_root = lambda *p: os.path.join(root, *p)
pkg_root = from_root('minesweeper')
from_pkg_root = lambda *p: os.path.join(pkg_root, *p)

_version_module = imp.load_source('minesweeper.version',
                                  os.path.join(root, 'minesweeper/version.py'))
version = str(_version_module.VERSION)

with open(from_root('README.rst')) as fp:
    long_description = fp.read()


if __name__ == '__main__':
    setup(
        name='minesweeper-hints',
        version=version,
        author='Zach "theY4Kman" Kanzler',
        author_email='they4kman@gmail.com',
        description='Minesweeper game ripe for AI development',
        long_description=long_description,
        packages=['minesweeper'],
        package_data={
            'minesweeper': find_files(r'^.+\.(?!py|pyc)[^.]*$',
                                      from_pkg_root('fonts'),
                                      from_pkg_root('images'))
        },
        include_package_data=True,
        install_requires=build_install_requires(from_root('requirements.txt')),
        entry_points={
            'console_scripts': ['minesweeper=minesweeper.main:main'],
        },
        classifiers=[
            'Programming Language :: Python',
            'Operating System :: OS Independent',
            'License :: OSI Approved :: MIT License',
        ],
    )
