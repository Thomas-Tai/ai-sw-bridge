"""Feature build handlers, relocated from builder.py (Phase 3).

Each family module imports only leaf modules (_common, _build_context,
_edge_selectors, _face_geometry, _sketch_primitives, _version_resolver,
sketches) — never builder.py. builder.py re-exports the handlers back into
its namespace so _wire_handlers and monkeypatch seams resolve unchanged.
"""
