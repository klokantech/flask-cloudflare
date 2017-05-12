from setuptools import setup

setup(
    name='Flask-CloudFlare',
    version='1.0',
    description='CloudFlare API integration for Flask',
    py_modules=['flask_cloudflare'],
    install_requires=[
        'Flask>=0.11',
        'requests>=2.12',
    ])
