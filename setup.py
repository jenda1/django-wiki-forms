#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'wiki',
    'celery[redis]',
    'django-websocket-redis',
    'pyparsing'
]

setup_requirements = [
    'pytest-runner',
    # TODO(jenda1): put setup requirements (distutils extensions, etc.) here
]

test_requirements = [
    'pytest',
    # TODO: put package test requirements here
]

setup(
    name='django_wiki_forms',
    version='0.1.0',
    description="Python django_wiki_forms contains plugin to create forms in the wiki pages.",
    long_description=readme + '\n\n' + history,
    author="Jan Lána",
    author_email='lana.jan@gmail.com',
    url='https://github.com/jenda1/django-wiki-forms',
    packages=['django_wiki_forms', 'django_wiki_forms.mdx', 'django_wiki_forms.migrations'],
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords='django_wiki_forms',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    setup_requires=setup_requirements,
)
