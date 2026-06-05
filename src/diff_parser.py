"""Parse unified diff → changed files + line map."""
import re
from dataclasses import dataclass, field


@dataclass
class ChangedFile:
    path: str
    added_lines: set[int] = field(default_factory=set)
    removed_lines: set[int] = field(default_factory=set)


def parse_diff(diff_text: str) -> list[ChangedFile]:
    """Parse unified diff, return changed files with line numbers."""
    files: dict[str, ChangedFile] = {}
    current_file = ""
    new_line = 0

    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            current_file = line[6:]
            files[current_file] = ChangedFile(path=current_file)
            new_line = 0
        elif line.startswith("@@") and current_file:
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line = int(m.group(1)) - 1
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            new_line += 1
            files[current_file].added_lines.add(new_line)
        elif line.startswith(" ") and current_file:
            new_line += 1
        elif line.startswith("-") and not line.startswith("---") and current_file:
            files[current_file].removed_lines.add(new_line + 1)

    return [f for f in files.values() if f.added_lines]
