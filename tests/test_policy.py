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


class TestPolicyHotReload(unittest.TestCase):
    """Tests for policy file watching / hot-reload."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._policy_path = os.path.join(self._tmpdir.name, "policy.json")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_policy(self, data: dict) -> str:
        with open(self._policy_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return self._policy_path

    def test_hot_reload_detects_file_change(self):
        """Modify policy file on disk — changes take effect within 2 seconds."""
        import time

        path = self._write_policy({"repo_allowlist": ["org/one"]})
        cfg = PolicyConfig().load(path)
        self.assertEqual(cfg.check_repo("org/one").action, "allow")
        self.assertEqual(cfg.check_repo("org/two").action, "deny")

        cfg.start_watching(path)

        # Rewrite the policy file to allow org/two
        time.sleep(0.1)  # ensure mtime advances
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"repo_allowlist": ["org/one", "org/two"]}, f)

        # Wait for the watcher to pick up the change (up to 2s)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if cfg.check_repo("org/two").action == "allow":
                break
            time.sleep(0.1)
        else:
            self.fail("Hot-reload did not pick up policy change within 2 seconds")

        # org/three is still denied
        self.assertEqual(cfg.check_repo("org/three").action, "deny")
        cfg.stop_watching()

    def test_thread_safety_under_concurrent_reads(self):
        """Heavy concurrent reads against a policy being reloaded."""
        import threading
        import time

        path = self._write_policy({
            "repo_allowlist": ["safe/*"],
            "protected_branches": {"deny_pr_base": ["main"]},
        })
        cfg = PolicyConfig().load(path)

        errors: list[str] = []

        def reader() -> None:
            for _ in range(500):
                try:
                    decision = cfg.check_repo("safe/app")
                    if decision.action != "allow":
                        errors.append(f"unexpected action: {decision.action}")
                    decision = cfg.check_branch_for_pr("main")
                    if decision.action != "deny":
                        errors.append(f"unexpected branch action: {decision.action}")
                    decision = cfg.check_branch_for_pr("dev")
                    if decision.action != "allow":
                        errors.append(f"unexpected branch action: {decision.action}")
                except Exception as e:
                    errors.append(str(e))

        def writer() -> None:
            for _ in range(10):
                cfg.load(path)
                time.sleep(0.01)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        threads.append(threading.Thread(target=writer))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(errors, [], f"Thread-safety errors: {errors}")

    def test_no_watch_disables_watching(self):
        """verify start/stop lifecycle and --no-watch env-var path."""
        import time
        from unittest.mock import patch

        path = self._write_policy({"repo_allowlist": ["org/x"]})
        cfg = PolicyConfig().load(path)

        # 1. Before starting, no watcher thread exists
        self.assertIsNone(cfg._watcher_thread)

        # 2. Verify env-var detection
        with patch.dict("os.environ", {"GITHUB_POLICY_NO_WATCH": "true"}):
            from src.config import get_policy_no_watch
            self.assertTrue(get_policy_no_watch())

        # 3. Manually start watching — verify thread is created
        cfg.start_watching(path)
        self.assertIsNotNone(cfg._watcher_thread)
        assert cfg._watcher_thread is not None  # narrow for mypy
        self.assertTrue(cfg._watcher_thread.is_alive())

        # 4. stop_watching cleans up
        watcher_thread = cfg._watcher_thread
        cfg.stop_watching()
        time.sleep(0.2)
        assert watcher_thread is not None
        self.assertFalse(watcher_thread.is_alive())

        # 5. After stop, _watcher_stop is cleared
        self.assertIsNone(cfg._watcher_stop)


if __name__ == "__main__":
    unittest.main()
