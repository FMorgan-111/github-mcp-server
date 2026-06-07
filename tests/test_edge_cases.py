"""Edge case tests for policy + HTTP transport."""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from policy import PolicyConfig


def test_malformed_json_defaults_to_deny():
    """Malformed policy JSON should deny all (fail-safe)."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write("{this is not valid json")
    f.close()
    try:
        cfg = PolicyConfig()
        cfg.load(f.name)
        d = cfg.check_repo("any/repo")
        assert d.action == "deny", f"Malformed JSON should deny, got {d.action}"
        assert getattr(cfg, "_deny_all", False), "Should set _deny_all flag"
    finally:
        os.unlink(f.name)


def test_recovery_from_malformed_json():
    """After malformed JSON, a good reload should clear _deny_all."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    f.write("{this is not valid json")
    f.close()
    try:
        cfg = PolicyConfig()
        cfg.load(f.name)
        assert cfg.check_repo("any/repo").action == "deny"

        # Write valid JSON to the same file and reload
        with open(f.name, "w") as fh:
            json.dump({"repo_allowlist": ["test-org/*"]}, fh)
        cfg.load(f.name)

        d = cfg.check_repo("test-org/anything")
        assert d.action == "allow", (
            f"Recovery failed: _deny_all={getattr(cfg, '_deny_all', 'N/A')}, "
            f"action={d.action}, reason={d.reason}"
        )
    finally:
        os.unlink(f.name)


def test_concurrent_reads_during_reload():
    """5 threads x 200 reads + 10 policy changes = zero errors."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"repo_allowlist": ["test-org/*"]}, f)
    f.close()

    cfg = PolicyConfig()
    cfg.load(f.name)
    cfg.start_watching(f.name)

    try:
        errors = []

        def reader():
            try:
                for _ in range(200):
                    d = cfg.check_repo("test-org/anything")
                    if d.action != "allow":
                        errors.append(f"Expected allow, got {d.action}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()

        for i in range(10):
            time.sleep(0.2)
            with open(f.name, "w") as fh:
                json.dump({"repo_allowlist": ["test-org/*", f"test-org/repo{i}"]}, fh)

        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "Reader thread hung — possible deadlock"

        assert not errors, f"Concurrent errors: {errors[:5]}"
    finally:
        cfg.stop_watching()
        os.unlink(f.name)


def test_stop_watching_cleans_up():
    """stop_watching should clean up thread cleanly."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"repo_allowlist": ["a/b"]}, f)
    f.close()

    cfg = PolicyConfig()
    cfg.load(f.name)
    cfg.start_watching(f.name)

    try:
        assert cfg._watcher_thread is not None
        assert cfg._watcher_thread.is_alive()
    finally:
        cfg.stop_watching()
        os.unlink(f.name)

    time.sleep(0.1)
    assert cfg._watcher_thread is None, "thread ref should be cleared"
    assert cfg._watcher_stop is None, "stop event should be cleared"


def test_double_start_watching_is_noop():
    """Calling start_watching twice should not create duplicate threads."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"repo_allowlist": ["a/b"]}, f)
    f.close()

    cfg = PolicyConfig()
    cfg.load(f.name)
    cfg.start_watching(f.name)

    try:
        t1 = cfg._watcher_thread
        cfg.start_watching(f.name)  # second call
        t2 = cfg._watcher_thread
        assert t1 is t2, "second call should be no-op"
    finally:
        cfg.stop_watching()
        os.unlink(f.name)
