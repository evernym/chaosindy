import io

import setuptools

name = 'chaosindy'
desc = 'Chaos Toolkit Extension for INDY.'

author = "Evernym"
author_email = 'devin.fisher@evernym.com'

packages = [
    'chaosindy'
]

test_require = []
with io.open('requirements-dev.txt') as f:
    test_require = [l.strip() for l in f if not l.startswith('#')]

install_require = []
with io.open('requirements.txt') as f:
    install_require = [l.strip() for l in f if not l.startswith('#')]

setup_params = dict(
    name=name,
    version='0.1.0',
    description=desc,
    author=author,
    author_email=author_email,
    license=license,
    packages=packages,
    install_requires=install_require,
    tests_require=test_require,
    python_requires='>=3.5.*'
)


def main():
    """Package installation entry point."""
    setuptools.setup(**setup_params)


if __name__ == '__main__':
    main()
