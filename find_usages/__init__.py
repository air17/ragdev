"""
Find Usages Package

This package provides tools for indexing Python projects and finding usages of symbols
using Jedi static analysis.

Main functions:
- index_project: Index a Python project and save the index to a JSON file
- find_usages: Find all usages of a symbol in a Python project using the index
"""

from .indexer import index_project
from .finder import find_usages

__all__ = ["index_project", "find_usages"]
