"""Empacota focos_stream para os workers do Dataflow (usado via --setup_file)."""

import setuptools

setuptools.setup(
    name="focos-stream",
    version="1.0.0",
    description="Pipeline de streaming dos focos de calor do INPE",
    packages=setuptools.find_packages(include=["focos_stream", "focos_stream.*"]),
    install_requires=[],  # os workers já trazem apache-beam[gcp]
)
