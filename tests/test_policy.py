"""Tests for policy.py — allowlist & branch protection."""
import json
import os
import tempfile
import unittest

from src.policy import PolicyConfig, resolve_dry_run


class TestPolicyConfig(unittest.TestCase):

    def _write_policy(self, data: dict) -> str:
        """Write a temporary policy.json and return its path."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, f)
        f.close()
        return f.name

    def test_empty_config_default_allow(self):
        cfg = PolicyConfig()
        # not loaded → allows everything
        self.assertEqual(cfg.check_repo("anything/here").action, "allow")
        self.assertEqual(cfg.check_branch_for_pr("main").action, "allow")

    def test_load_missing_file_not_required(self):
        cfg = PolicyConfig().load("/nonexistent/path.json", required=False)
        # no crash, default allow
        self.assertEqual(cfg.check_repo("x/y").action, "allow")

    def test_load_missing_file_required_raises(self):
        with self.assertRaises(FileNotFoundError):
            PolicyConfig().load("/nonexistent/path.json", required=True)

    def test_repo_allowlist_exact_match(self):
        path = self._write_policy({"repo_allowlist": ["FMorgan-111/test"]})
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.check_repo("FMorgan-111/test").action, "allow")
            self.assertEqual(cfg.check_repo("other/repo").action, "deny")
        finally:
            os.unlink(path)

    def test_repo_allowlist_wildcard(self):
        path = self._write_policy({"repo_allowlist": ["FMorgan-111/*"]})
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.check_repo("FMorgan-111/foo").action, "allow")
            self.assertEqual(cfg.check_repo("FMorgan-111/bar").action, "allow")
            self.assertEqual(cfg.check_repo("other/repo").action, "deny")
        finally:
            os.unlink(path)

    def test_wildcard_match_is_anchored(self):
        path = self._write_policy({"repo_allowlist": ["org/*-service"]})
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.check_repo("org/api-service").action, "allow")
            self.assertEqual(cfg.check_repo("prefix/org/api-service").action, "deny")
            self.assertEqual(cfg.check_repo("org/api-service-extra").action, "deny")
        finally:
            os.unlink(path)

    def test_single_string_policy_values_are_wrapped(self):
        path = self._write_policy({
            "repo_allowlist": "owner/repo",
            "protected_branches": {"deny_pr_base": "release/*"},
        })
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.repo_allowlist, ["owner/repo"])
            self.assertEqual(cfg.deny_pr_base, ["release/*"])
            self.assertEqual(cfg.check_branch_for_pr("release/1.0").action, "deny")
        finally:
            os.unlink(path)

    def test_invalid_policy_required_raises_and_optional_keeps_defaults(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{invalid")
        f.close()
        try:
            with self.assertRaises(RuntimeError):
                PolicyConfig().load(f.name, required=True)
            cfg = PolicyConfig().load(f.name, required=False)
            self.assertEqual(cfg.check_repo("owner/repo").action, "deny")
        finally:
            os.unlink(f.name)

    def test_non_list_values_are_wrapped(self):
        path = self._write_policy({
            "repo_allowlist": 123,
            "protected_branches": {"deny_force_push": False},
        })
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.repo_allowlist, [123])
            self.assertFalse(cfg.deny_force_push)
        finally:
            os.unlink(path)

    def test_allowlist_empty_means_allow_all(self):
        path = self._write_policy({"repo_allowlist": []})
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.check_repo("anything/goes").action, "allow")
        finally:
            os.unlink(path)

    def test_branch_protection_deny_main_master(self):
        path = self._write_policy({
            "repo_allowlist": [],
            "protected_branches": {"deny_pr_base": ["main", "master"]},
        })
        try:
            cfg = PolicyConfig().load(path)
            self.assertEqual(cfg.check_branch_for_pr("main").action, "deny")
            self.assertEqual(cfg.check_branch_for_pr("master").action, "deny")
            self.assertEqual(cfg.check_branch_for_pr("develop").action, "allow")
        finally:
            os.unlink(path)

    def test_resolve_dry_run(self):
        # explicit arg wins
        self.assertTrue(resolve_dry_run(True, False))
        self.assertFalse(resolve_dry_run(False, True))
        # None falls back to env
        self.assertTrue(resolve_dry_run(None, True))
        self.assertFalse(resolve_dry_run(None, False))


if __name__ == "__main__":
    unittest.main()
