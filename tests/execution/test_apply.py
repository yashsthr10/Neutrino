"""ExecutionService apply / rollback / reflection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.execution import ExecutionService


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_search_replace_apply_and_rollback(repo: Path) -> None:
    svc = ExecutionService(repo)
    patch = """pkg/mod.py
<<<<<<< SEARCH
def hello():
    return 1
=======
def hello():
    return 2
>>>>>>> REPLACE
"""
    result = svc.apply(patch=patch, format="search_replace")
    assert result.success is True
    assert result.change_id is not None
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "def hello():\n    return 2\n"

    rolled = svc.rollback(change_id=result.change_id)
    assert rolled["success"] is True
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "def hello():\n    return 1\n"


def test_search_replace_failure_reflection(repo: Path) -> None:
    svc = ExecutionService(repo)
    patch = """pkg/mod.py
<<<<<<< SEARCH
def missing():
    return 0
=======
def missing():
    return 1
>>>>>>> REPLACE
"""
    result = svc.apply(patch=patch, format="search_replace")
    assert result.success is False
    assert result.failures
    assert result.reflection
    assert "SEARCH" in result.reflection or "retry" in result.reflection.lower() or "exact" in (
        result.reflection or ""
    ).lower()


def test_patch_format_update(repo: Path) -> None:
    svc = ExecutionService(repo)
    patch = """*** Begin Patch
*** Update File: pkg/mod.py
@@
 def hello():
-    return 1
+    return 3
*** End Patch
"""
    result = svc.apply(patch=patch, format="patch")
    assert result.success is True
    assert "return 3" in (repo / "pkg" / "mod.py").read_text(encoding="utf-8")


def test_add_file_ignores_plus_prefixed_end_patch(repo: Path) -> None:
    """Models often emit ``+*** End Patch``; it must not land in the file."""
    svc = ExecutionService(repo)
    patch = """*** Begin Patch
*** Add File: hello.html
+<html>
+  <body>hi</body>
+</html>
+*** End Patch
*** End Patch
"""
    result = svc.apply(patch=patch, format="patch")
    assert result.success is True
    text = (repo / "hello.html").read_text(encoding="utf-8")
    assert "End Patch" not in text
    assert "<html>" in text
    assert text.endswith("</html>\n")


def test_update_file_ignores_plus_prefixed_end_patch(repo: Path) -> None:
    svc = ExecutionService(repo)
    patch = """*** Begin Patch
*** Update File: pkg/mod.py
@@
 def hello():
-    return 1
+    return 9
+*** End Patch
*** End Patch
"""
    result = svc.apply(patch=patch, format="patch")
    assert result.success is True
    text = (repo / "pkg" / "mod.py").read_text(encoding="utf-8")
    assert "End Patch" not in text
    assert "return 9" in text


def test_dry_run_does_not_write(repo: Path) -> None:
    svc = ExecutionService(repo)
    original = (repo / "pkg" / "mod.py").read_text(encoding="utf-8")
    patch = """pkg/mod.py
<<<<<<< SEARCH
def hello():
    return 1
=======
def hello():
    return 9
>>>>>>> REPLACE
"""
    result = svc.apply(patch=patch, format="search_replace", dry_run=True)
    assert result.success is True
    assert result.dry_run is True
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == original


def test_shell_requires_approval(repo: Path) -> None:
    svc = ExecutionService(repo)
    denied = svc.run(command="echo hi", approved=False)
    assert denied.success is False
    assert denied.needs_approval is True
    ok = svc.run(command="echo hi", approved=True)
    assert ok.success is True
    assert "hi" in ok.stdout
