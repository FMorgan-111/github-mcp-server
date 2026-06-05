"""Policy enforcement layer — repo allowlist, branch protection, dry-run delegation."""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

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

    def load(self, path: str, required: bool = False) -> "PolicyConfig":
        """Load policy from a JSON file."""
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
            return self

        self.repo_allowlist = data.get("repo_allowlist", [])
        self.deny_pr_base = (
            data.get("protected_branches", {}).get("deny_pr_base", [])
        )
        self.deny_force_push = (
            data.get("protected_branches", {}).get("deny_force_push", True)
        )
        self._loaded = True
        return self

    def check_repo(self, repo: str) -> PolicyDecision:
        """Check if `repo` is allowed."""
        if not self._loaded:
            return PolicyDecision("allow", "policy not loaded", "default-allow")

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


# ── Helpers ────────────────────────────────────────────
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
