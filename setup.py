from setuptools import setup, find_packages

setup(
    name='plasma-cli',
    version='2.3.0',
    packages=find_packages(exclude=['tests', 'docs']),
    install_requires=[
        'rich>=13.0.0',
    ],
    entry_points={
        'console_scripts': [
            'plasma-cli=client.multi_target_cli:entrypoint',
        ],
    },
    author='physicslu',
    author_email='physicslu@gmail.com',
    description='Plasma Multi-Channel Programmer CLI Tool',
    url='https://github.com/physicslu/plasma',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.7',
)

