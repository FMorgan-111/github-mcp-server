"""Policy enforcement layer — repo allowlist, branch protection, dry-run delegation."""
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)

# ── Data structures ────────────────────────────────────
@dataclass
class PolicyDecision:
    action: str          # "allow" | "deny" | "dry_run"
    reason: str          # human-readable explanation
    matched_rule: str    # which rule triggered (for audit)

@dataclass
class PolicyConfig:
    """Loads and holds runtime policy from policy.json."""
    repo_allowlist: list[str] = field(default_factory=list)
    deny_pr_base: list[str] = field(default_factory=list)
    deny_force_push: bool = True

    _required: bool = False
    _loaded: bool = False

    # ── Thread safety & file watching ────────────────
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _watcher_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _watcher_stop: Optional[threading.Event] = field(default=None, repr=False)

    def load(self, path: str, required: bool = False) -> "PolicyConfig":
        """Load policy from a JSON file."""
        with self._lock:
            self._required = required

            if not os.path.exists(path):
                if required:
                    raise FileNotFoundError(
                        f"Policy file not found: {path} (GITHUB_POLICY_REQUIRED=true)"
                    )
                return self  # empty config → default-allow

            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                if required:
                    raise RuntimeError(f"Failed to load policy file {path}: {e}")
                # Invalid JSON → default-deny (safer than default-allow)
                self._loaded = True
                self._deny_all = True
                self.repo_allowlist = []
                self.deny_pr_base = []
                return self

            self.repo_allowlist = _ensure_list(data.get("repo_allowlist"))
            deny_list = (
                data.get("protected_branches", {}).get("deny_pr_base")
            )
            self.deny_pr_base = _ensure_list(deny_list) if deny_list is not None else []
            self.deny_force_push = (
                data.get("protected_branches", {}).get("deny_force_push", True)
            )
            self._loaded = True
            self._deny_all = False
            return self

    # ── File watching (hot-reload) ──────────────────
    def start_watching(self, policy_path: str) -> None:
        """Watch policy_path for changes and reload automatically.

        Spawns a daemon thread that polls the file's mtime every 500ms.
        When a modification is detected the policy is re-read and the
        in-memory config updated.
        """
        if self._watcher_thread is not None:
            return  # already watching

        stop_evt = threading.Event()
        self._watcher_stop = stop_evt

        def _watch_loop() -> None:
            try:
                last_mtime = os.path.getmtime(policy_path)
            except OSError:
                last_mtime = 0.0

            while not stop_evt.is_set():
                try:
                    current_mtime = os.path.getmtime(policy_path)
                except OSError:
                    current_mtime = 0.0

                if current_mtime > last_mtime:
                    logger.info("policy file changed on disk — reloading")
                    _reload_policy(self, policy_path)
                    try:
                        last_mtime = os.path.getmtime(policy_path)
                    except OSError:
                        last_mtime = current_mtime

                stop_evt.wait(timeout=0.5)

        self._watcher_thread = threading.Thread(
            target=_watch_loop,
            daemon=True,
            name="policy-watcher",
        )
        self._watcher_thread.start()
        logger.info("Policy hot-reload watcher started for %s", policy_path)

    def stop_watching(self) -> None:
        """Stop the file watcher thread (no-op if not watching)."""
        if self._watcher_stop is not None:
            self._watcher_stop.set()
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)
        self._watcher_thread = None
        self._watcher_stop = None

    # ── Policy checks (thread-safe) ─────────────────
    def check_repo(self, repo: str) -> PolicyDecision:
        """Check if `repo` is allowed."""
        with self._lock:
            if not self._loaded:
                return PolicyDecision("allow", "policy not loaded", "default-allow")

            if getattr(self, "_deny_all", False):
                return PolicyDecision("deny", "policy load failed — denying all", "policy:invalid-config")

            for pattern in self.repo_allowlist:
                if _wildcard_match(pattern, repo):
                    return PolicyDecision(
                        "allow", f"repo {repo} matches allowlist {pattern}",
                        f"repo_allowlist:{pattern}"
                    )

            if self.repo_allowlist:
                return PolicyDecision(
                    "deny", f"repo {repo} not in allowlist",
                    "repo_allowlist:deny_unlisted"
                )

            return PolicyDecision("allow", "allowlist empty", "default-allow")

    def check_branch_for_pr(self, base_branch: str) -> PolicyDecision:
        """Check if `base_branch` is protected from PR."""
        with self._lock:
            if not self._loaded:
                return PolicyDecision("allow", "policy not loaded", "default-allow")

            for protected in self.deny_pr_base:
                if _wildcard_match(protected, base_branch):
                    return PolicyDecision(
                        "deny",
                        f"PR to protected branch '{base_branch}' is blocked",
                        f"protected_branch:{protected}"
                    )

            return PolicyDecision("allow", f"branch {base_branch} is not protected", "branch_unprotected")


# ── Watcher helpers (module-level so they can be pickled) ──
def _reload_policy(cfg: "PolicyConfig", policy_path: str) -> None:
    """Reload policy from disk — called by watcher thread."""
    try:
        cfg.load(policy_path, required=cfg._required)
        logger.info("policy reloaded successfully")
    except Exception:
        logger.exception(
            "Failed to reload policy from %s — keeping current policy",
            policy_path,
        )


# ── Helpers ────────────────────────────────────────────
def _ensure_list(v: object) -> list[Any]:
    """Return v as a list, wrapping a single string if needed."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [v]
    return [v]


def _wildcard_match(pattern: str, value: str) -> bool:
    """Match a glob-like pattern (e.g. 'FMorgan-111/*') against a value."""
    if pattern == "*":
        return True
    if "*" in pattern:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return bool(re.match(regex, value))
    return pattern == value


def resolve_dry_run(dry_run: Optional[bool], env_enabled: bool) -> bool:
    """Resolve effective dry-run state: explicit arg > env > default False."""
    if dry_run is not None:
        return dry_run
    return env_enabled
