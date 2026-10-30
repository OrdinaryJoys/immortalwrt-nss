"""Check complete unified hunks at their declared lines before invoking patch."""
import hashlib
from pathlib import Path, PurePosixPath
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def patch_path(line, prefix):
    value = line.rstrip('\n').split('\t', 1)[0]
    require(value.startswith(prefix), 'unsupported patch path: ' + value)
    value = value[len(prefix):]
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and
            all(p not in ('', '.', '..', '.git') for p in path.parts),
            'unsafe patch path: ' + value)
    return value


def inspect_patch(root, data):
    """Return expected file bytes and provenance; never search for shifted context."""
    root = Path(root).resolve()
    lines = data.decode('utf-8').splitlines(keepends=True)
    require(all(line.endswith('\n') for line in lines), 'unterminated patch line')
    files = {}
    current = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('--- '):
            old = patch_path(line, '--- a/')
            require(i + 1 < len(lines), 'missing new file header')
            new = patch_path(lines[i + 1], '+++ b/')
            require(old == new and old not in files, 'renamed or repeated patch file')
            path = root / old
            require(path.is_file() and path.resolve().is_relative_to(root),
                    'missing or external source file: ' + old)
            original = path.read_bytes()
            text = original.decode('utf-8').splitlines(keepends=True)
            require(all(part.endswith('\n') for part in text),
                    'unterminated source line: ' + old)
            current = {'original': text, 'output': [], 'cursor': 0, 'hunks': [],
                       'before_sha256': digest(original)}
            files[old] = current
            i += 2
            continue
        if line.startswith('@@'):
            require(current is not None, 'hunk without file')
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', line)
            require(match is not None, 'malformed hunk header')
            old_start, old_count, new_start, new_count = (
                int(value) if value is not None else 1 for value in match.groups())
            require((old_count == 0 or old_start > 0) and
                    (new_count == 0 or new_start > 0) and old_count + new_count > 0,
                    'invalid hunk range')
            old_index = old_start - 1 if old_count else old_start
            new_index = new_start - 1 if new_count else new_start
            require(0 <= old_index <= len(current['original']) and
                    old_index + old_count <= len(current['original']),
                    'hunk range outside source')
            old_body, new_body = [], []
            i += 1
            while len(old_body) < old_count or len(new_body) < new_count:
                require(i < len(lines), 'truncated hunk')
                part = lines[i]
                # Existing unified patches may omit the prefix on an empty context line.
                if part == '\n':
                    part = ' \n'
                require(part[0] in ' +-','invalid hunk body')
                if part[0] in ' -':
                    old_body.append(part[1:])
                if part[0] in ' +':
                    new_body.append(part[1:])
                require(len(old_body) <= old_count and len(new_body) <= new_count,
                        'hunk count overflow')
                i += 1
            require(old_index >= current['cursor'], 'overlapping or unordered hunks')
            require(current['original'][old_index:old_index + old_count] == old_body,
                    'declared-line context mismatch: ' + str(old_start))
            current['output'].extend(current['original'][current['cursor']:old_index])
            require(len(current['output']) == new_index, 'declared new-line mismatch')
            current['output'].extend(new_body)
            current['cursor'] = old_index + old_count
            current['hunks'].append({'old_start': old_start, 'old_count': old_count,
                                     'new_start': new_start, 'new_count': new_count,
                                     'offset': 0, 'full_context': True})
            continue
        require(not (line.startswith('+++ ') or line.startswith('\\ ') or
                     (current is not None and line[0] in ' +-'
                      and line != '\n' and line != '-- \n')),
                'unconsumed or unsupported patch content')
        i += 1
    require(files, 'no patch files')
    expected, report = {}, {}
    for name, item in files.items():
        require(item['hunks'], 'file without hunks: ' + name)
        item['output'].extend(item['original'][item['cursor']:])
        expected[name] = ''.join(item['output']).encode('utf-8')
        report[name] = {'before_sha256': item['before_sha256'],
                        'after_sha256': digest(expected[name]), 'hunks': item['hunks']}
    return expected, report


def verify_applied(root, expected):
    for name, data in expected.items():
        require((Path(root) / name).read_bytes() == data,
                'patch output differs from declared-context result: ' + name)
