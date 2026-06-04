"""Local rule-based code review"""
import re
from typing import List, Dict


def review_diff(diff_text: str) -> List[Dict]:
    """Analyze diff text and return code review issues"""
    issues = []
    lines = diff_text.split('\n')
    current_line = 0
    current_file = ""

    for line in lines:
        if line.startswith('+++'):
            current_file = line[6:]  # Remove '+++ b/'
        elif line.startswith('@@'):
            # Parse line number from @@ -old_start,old_count +new_start,new_count @@
            match = re.search(r'\+(\d+)', line)
            if match:
                current_line = int(match.group(1)) - 1
        elif line.startswith('+') and not line.startswith('+++'):
            current_line += 1
            content = line[1:]  # Remove '+' prefix

            # Check for print() statements (skip test files)
            is_test_file = (
                '/tests/' in current_file
                or current_file.startswith('tests/')
                or current_file.endswith('_test.py')
                or '/test_' in current_file
            )
            if 'print(' in content and not is_test_file:
                issues.append({
                    'severity': 'warning',
                    'line': current_line,
                    'message': 'Print statement found - consider using logging instead',
                    'rule': 'no-print'
                })

            # Check for TODO/FIXME/HACK comments
            if re.search(r'\b(TODO|FIXME|HACK)\b', content, re.IGNORECASE):
                issues.append({
                    'severity': 'warning',
                    'line': current_line,
                    'message': 'TODO/FIXME/HACK comment found - should be tracked in issue tracker',
                    'rule': 'no-todo-comments'
                })

            # Check for hardcoded secrets
            secret_patterns = [
                r'password\s*=\s*["\'][^"\']+["\']',
                r'api_key\s*=\s*["\'][^"\']+["\']',
                r'token\s*=\s*["\'][^"\']+["\']'
            ]
            for pattern in secret_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append({
                        'severity': 'error',
                        'line': current_line,
                        'message': 'Hardcoded secret detected - use environment variables',
                        'rule': 'no-hardcoded-secrets'
                    })

            # Check for bare except clauses
            if re.search(r'except\s*:', content):
                issues.append({
                    'severity': 'error',
                    'line': current_line,
                    'message': 'Bare except clause - specify exception type',
                    'rule': 'no-bare-except'
                })
        elif line.startswith(' ') or (line.startswith('-') and not line.startswith('---')):
            if line.startswith(' '):
                current_line += 1

    # Check for long functions (simplified - count added lines between def and next def/class)
    function_lines = 0
    in_function = False
    for line in lines:
        if line.startswith('+'):
            content = line[1:]
            if re.match(r'\s*def\s+', content):
                in_function = True
                function_lines = 0
            elif in_function and re.match(r'\s*(def\s+|class\s+)', content):
                if function_lines > 80:
                    issues.append({
                        'severity': 'warning',
                        'line': current_line - function_lines,
                        'message': f'Function is {function_lines} lines long - consider breaking it down',
                        'rule': 'function-length'
                    })
                in_function = re.match(r'\s*def\s+', content) is not None
                function_lines = 0
            elif in_function:
                function_lines += 1

    return issues