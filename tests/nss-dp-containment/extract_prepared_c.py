#!/usr/bin/env python3
"""Extract complete, byte-preserved definitions from an offline prepared tree.

This is a small lexical reader, not a C parser or an implementation model.
Definitions retain their preprocessor directives; the host compiler selects the
configured branches. Missing, ambiguous, or unterminated definitions fail.
"""
import hashlib
from pathlib import Path
import re


def code_mask(text):
    """Blank comments/literals without changing offsets or line starts."""
    masked = list(text)
    pos, state = 0, 'code'
    while pos < len(text):
        char, following = text[pos], text[pos:pos + 2]
        if state == 'code':
            if following in ('//', '/*'):
                state = 'line' if following == '//' else 'comment'
                masked[pos:pos + 2] = '  '
                pos += 2
                continue
            if char in ('"', "'"):
                state = char
                masked[pos] = ' '
        else:
            if char != '\n':
                masked[pos] = ' '
            if state == 'line' and char == '\n':
                state = 'code'
            elif state == 'comment' and following == '*/':
                masked[pos:pos + 2] = '  '
                state = 'code'
                pos += 2
                continue
            elif state in ('"', "'"):
                if char == '\\':
                    if pos + 1 < len(text) and text[pos + 1] != '\n':
                        masked[pos + 1] = ' '
                    pos += 2
                    continue
                if char == state:
                    state = 'code'
        pos += 1
    return ''.join(masked)


def block_end(text, start):
    depth, pos, state = 0, start, 'code'
    while pos < len(text):
        char = text[pos]
        following = text[pos:pos + 2]
        if state == 'line':
            if char == '\n':
                state = 'code'
        elif state == 'comment':
            if following == '*/':
                state = 'code'
                pos += 1
        elif state in ('"', "'"):
            if char == '\\':
                pos += 1
            elif char == state:
                state = 'code'
        elif following == '//':
            state = 'line'
            pos += 1
        elif following == '/*':
            state = 'comment'
            pos += 1
        elif char in ('"', "'"):
            state = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return pos + 1
            if depth < 0:
                break
        pos += 1
    raise ValueError('unterminated C definition')


def function(text, name, *, occurrence=None):
    pattern = re.compile(r'^[A-Za-z_][A-Za-z_0-9 \t*]*(?:\r?\n[ \t]*)?\b' + re.escape(name) +
                         r'[ \t]*\([^;{}]*\)[ \t\r\n]*\{', re.M)
    matches = list(pattern.finditer(code_mask(text)))
    if not matches or (occurrence is None and len(matches) != 1):
        raise ValueError(f'expected one definition of {name}; found {len(matches)}')
    selected = matches[occurrence if occurrence is not None else 0]
    opening = selected.end() - 1
    return text[selected.start():block_end(text, opening)] + '\n'


def structure(text, name, kind='struct'):
    matches = list(re.finditer(r'^' + re.escape(kind) + r'[ \t]+' + re.escape(name) + r'[ \t\r\n]*\{', code_mask(text), re.M))
    if len(matches) != 1:
        raise ValueError(f'expected one {kind} definition of {name}; found {len(matches)}')
    selected = matches[0]
    end = block_end(text, selected.end() - 1)
    tail = re.match(r'\s*;', text[end:])
    if tail is None:
        raise ValueError(f'{name} is not a standalone struct definition')
    return text[selected.start():end + tail.end()] + '\n'


def variable(text, name):
    matches = list(re.finditer(r'^static[ \t]+struct[ \t]+[A-Za-z_0-9]+[ \t]+' +
                              re.escape(name) + r'[ \t\r\n]*=[ \t\r\n]*\{', code_mask(text), re.M))
    if len(matches) != 1:
        raise ValueError(f'expected one initializer of {name}; found {len(matches)}')
    selected = matches[0]
    end = block_end(text, selected.end() - 1)
    tail = re.match(r'\s*;', text[end:])
    if tail is None:
        raise ValueError('unterminated initializer: ' + name)
    return text[selected.start():end + tail.end()] + '\n'


class Prepared:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('prepared input must be a directory')
        self.files = {}
        self.extracted = []

    def read(self, relative):
        path = self.root / relative
        if path in self.files:
            return self.files[path]['text']
        before = path.stat()
        if not path.is_file() or before.st_size > 2 * 1024 * 1024:
            raise ValueError('missing/nonregular/oversized prepared source: ' + relative)
        data = path.read_bytes()
        after = path.stat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or len(data) != before.st_size:
            raise ValueError('prepared source changed while read: ' + relative)
        self.files[path] = {'path': relative, 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(), 'text': data.decode('utf-8'),
                            'identity': identity(after)}
        return self.files[path]['text']

    def function(self, relative, name, **options):
        text = function(self.read(relative), name, **options)
        self.extracted.append({'source': relative, 'function': name,
                               'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        return text

    def structure(self, relative, name, kind='struct'):
        text = structure(self.read(relative), name, kind)
        self.extracted.append({'source': relative, 'structure': name,
                               'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        return text

    def variable(self, relative, name):
        text = variable(self.read(relative), name)
        self.extracted.append({'source': relative, 'variable': name,
                               'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        return text

    def manifest(self):
        # Compilation takes time: reject a mixed/changed input snapshot instead
        # of silently attributing old extracted functions to a new source tree.
        for path, row in self.files.items():
            info = path.stat()
            identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if identity != row['identity'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('prepared source changed during host run: ' + row['path'])
        return {'prepared_root': str(self.root),
                'sources': [{key: row[key] for key in ('path', 'bytes', 'sha256')} for row in self.files.values()],
                'extracted_definitions': self.extracted}
