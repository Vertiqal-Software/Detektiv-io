# tools/validate_migrations.py
"""
Validate Alembic migrations graph without importing project code.

Checks:
- Each migration's `down_revision` references an existing revision (or None).
- No duplicate `revision` IDs.
- Exactly one head (unless intentionally branched/merged).

Exit code:
- 0 = OK
- 1 = Problems found

Usage:
    python tools/validate_migrations.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


VERSIONS_DIR = Path("db/migrations/versions")


@dataclass(frozen=True)
class Mig:
    file: Path
    revision: str
    down_revision: Optional[Union[str, tuple[str, ...], list[str]]]


def _extract_rev_fields(py_file: Path) -> Optional[Mig]:
    """
    Parse a migration file's AST to extract `revision` and `down_revision`.

    Supports:
        revision = "..."
        revision: str = "..."
        down_revision = "..."
        down_revision: str | None = "..."
        down_revision = None
        down_revision = ("rev1", "rev2")   # merge
        down_revision = ["rev1", "rev2"]   # merge (list)
    """
    try:
        src = py_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Cannot read {py_file}: {e}")
        return None

    try:
        tree = ast.parse(src, filename=str(py_file))
    except SyntaxError as e:
        print(f"[ERROR] Syntax error in {py_file}: {e}")
        return None

    revision = None
    down_revision = None

    def _lit(node):
        # Extract literal value safely
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)):
            vals = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant):
                    vals.append(elt.value)
                else:
                    return None
            return tuple(vals) if isinstance(node, ast.Tuple) else list(vals)
        if isinstance(node, ast.NameConstant):  # Py <3.8 compat
            return node.value
        return None

    for node in tree.body:
        # Handle "x: type = value" (AnnAssign)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            key = node.target.id
            val = _lit(node.value)
            if key == "revision":
                revision = val
            elif key == "down_revision":
                down_revision = val

        # Handle "x = value" (Assign)
        if isinstance(node, ast.Assign):
            # targets can be multiple, but Alembic files use one
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    key = tgt.id
                    val = _lit(node.value)
                    if key == "revision":
                        revision = val
                    elif key == "down_revision":
                        down_revision = val

    if not revision or not isinstance(revision, str):
        print(f"[WARN] Skipping {py_file.name}: no valid 'revision' found")
        return None

    # Normalize None to None, list->tuple
    if isinstance(down_revision, list):
        down_revision = tuple(down_revision)

    return Mig(py_file, revision, down_revision)  # type: ignore[arg-type]


def _flatten(dr: Optional[Union[str, Iterable[str]]]) -> list[str]:
    if dr is None:
        return []
    if isinstance(dr, str):
        return [dr]
    return list(dr)


def main() -> int:
    if not VERSIONS_DIR.exists():
        print(f"[ERROR] Versions dir not found: {VERSIONS_DIR}")
        return 1

    files = sorted(VERSIONS_DIR.glob("*.py"))
    if not files:
        print(f"[ERROR] No migration files in {VERSIONS_DIR}")
        return 1

    migs: list[Mig] = []
    for f in files:
        m = _extract_rev_fields(f)
        if m:
            migs.append(m)

    # Basic set checks
    revisions = [m.revision for m in migs]
    dupes = {r for r in revisions if revisions.count(r) > 1}
    if dupes:
        print("\n[FAIL] Duplicate revision IDs detected:")
        for r in sorted(dupes):
            culprit_files = [m.file for m in migs if m.revision == r]
            for cf in culprit_files:
                print(f"  - {r}  <- {cf}")
        print("Fix: ensure each migration has a unique 'revision' string.")
        return 1

    known = set(revisions)

    # Validate down_revision references exist
    bad_links: list[tuple[Mig, str]] = []
    for m in migs:
        for parent in _flatten(m.down_revision):
            if parent not in known:
                bad_links.append((m, parent))

    if bad_links:
        print("\n[FAIL] Broken down_revision references:")
        for m, parent in bad_links:
            print(f"  - {m.file.name}: down_revision -> {parent!r} (not found)")
        # Suggest the likely correct parent (the current head)
        tips = compute_heads(migs)
        if tips:
            print("\nHint: your likely parent is the current head revision.")
            print("Current heads:")
            for h in tips:
                print(f"  - {h}")
            print("Edit the migration and set down_revision to the correct head.")
        return 1

    # Head computation: head == a revision that is not listed as someone else's parent
    heads = compute_heads(migs)

    if len(heads) == 0:
        print("\n[FAIL] No head found (graph might be cyclic).")
        return 1
    if len(heads) > 1:
        print("\n[FAIL] Multiple heads detected (unmerged branches):")
        for h in heads:
            print(f"  - {h}")
        print("Fix: create a merge migration that sets down_revision to both branch heads.")
        return 1

    print("[OK] Migrations look good.")
    print(f"Head: {next(iter(heads))}")
    return 0


def compute_heads(migs: list[Mig]) -> set[str]:
    children = {m.revision for m in migs}
    parents: set[str] = set()
    for m in migs:
        for p in _flatten(m.down_revision):
            parents.add(p)
    # heads = nodes that are children but never appear as a parent
    return children - parents


if __name__ == "__main__":
    sys.exit(main())
