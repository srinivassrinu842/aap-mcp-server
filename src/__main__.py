"""
Entrypoint for: python -m src

Docker ENTRYPOINT uses: python -m src.server
This file handles: python -m src
"""
from src.server import main

main()
