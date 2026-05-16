"""
v0.2 declarative part spec system.

A spec is a JSON document declaring a SOLIDWORKS part as an ordered list of
features. The build executor walks the features in order, calls the matching
SW COM API for each one, and reports a manifest describing what was built.

Submodules:
- schema   : the JSON schema (single source of truth for spec format)
- validator: schema + dependency-graph + locals.txt var-reference checks
- builder  : direct-COM build executor (one function per feature type)
- manifest : structured diff between spec intent and resulting SW state
"""

from .schema import SCHEMA, SCHEMA_VERSION
from .validator import validate, ValidationError

__all__ = ["SCHEMA", "SCHEMA_VERSION", "validate", "ValidationError"]
