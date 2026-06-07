"""Tests for diff_parser.py"""
from src.diff_parser import parse_diff


def test_parse_diff_single_file():
    diff = """diff --git a/src/app.py b/src/app.py
index 123..456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 def hello():
+    print("debug")
     return True"""
    files = parse_diff(diff)
    assert len(files) == 1
    assert files[0].path == "src/app.py"
    assert 2 in files[0].added_lines  # line 2: print("debug")


def test_parse_diff_multiple_files():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
+import os
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -3,0 +4,1 @@
+logger.info("start")"""
    files = parse_diff(diff)
    assert len(files) == 2
    assert {f.path for f in files} == {"a.py", "b.py"}


def test_parse_diff_no_added_lines():
    diff = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -1,1 +1,1 @@
-print("old")
+print("new")"""
    files = parse_diff(diff)
    assert len(files) == 1
    assert len(files[0].added_lines) == 1  # "new" is an addition


def test_parse_diff_tracks_removed_lines_without_returning_delete_only_file():
    diff = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -10,2 +10,1 @@
 context
-old
"""
    files = parse_diff(diff)
    assert files == []


def test_parse_diff_line_numbers_advance_over_context_and_removals():
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -20,4 +20,5 @@
 line 20
-old line
+new line
 line 22
+another new line
"""
    files = parse_diff(diff)
    assert len(files) == 1
    assert files[0].added_lines == {21, 23}
    assert files[0].removed_lines == {21}
