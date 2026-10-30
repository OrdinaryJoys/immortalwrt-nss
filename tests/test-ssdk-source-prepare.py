#!/usr/bin/env python3
"""Actual SSDK preparation gates with isolated synthetic parameter controls.

The helper bodies are imported from byte-identical per-case copies. SOURCE,
PACKAGE and PIN describe a synthetic recipe and real Git tree, not production
SSDK provenance. Git blob/tree objects need no index, add, commit or checkout.
Only this runner and SSDK-PREP-CONTROLS-* evidence are written. No C or make.
"""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import traceback
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')
HELPER = HERE / 'ssdk_source_prepare.py'
PARSER = HERE / 'edma_patch_context.py'
REAL_RUN = subprocess.run
ORIGINAL = {
    'src/main.txt': b'anchor\nold\nend\nuntouched-tail\n',
    'include/stable.txt': b'stable-data\n',
}
FINAL = {
    'src/main.txt': b'anchor\nfinal\nadded\nend\nuntouched-tail\n',
    'include/stable.txt': b'stable-data\n',
}
PATCHES = {
    '001-first.patch': b'--- a/src/main.txt\n+++ b/src/main.txt\n'
                       b'@@ -1,3 +1,3 @@\n anchor\n-old\n+new\n end\n',
    '002-second.patch': b'--- a/src/main.txt\n+++ b/src/main.txt\n'
                        b'@@ -1,3 +1,4 @@\n anchor\n-new\n+final\n+added\n end\n',
}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_record(directory, number, argv, kwargs, actual, observed, note):
    prefix = directory / ('%03d' % number)
    for label, process in [('actual', actual), ('observed', observed)]:
        if process is None:
            continue
        (prefix.with_suffix('.' + label + '.stdout')).write_bytes(process.stdout)
        (prefix.with_suffix('.' + label + '.stderr')).write_bytes(process.stderr)
    write_json(prefix.with_suffix('.json'), {
        'argv': [str(x) for x in argv], 'cwd': str(kwargs.get('cwd', '')),
        'stdin_sha256': sha(kwargs['input']) if 'input' in kwargs else None,
        'actual_executed': actual is not None, 'injection': note,
        'actual': None if actual is None else {
            'returncode': actual.returncode, 'stdout_sha256': sha(actual.stdout),
            'stderr_sha256': sha(actual.stderr)},
        'observed': {'returncode': observed.returncode,
                     'stdout_sha256': sha(observed.stdout),
                     'stderr_sha256': sha(observed.stderr)}})


def make_git_tree(cache, log):
    cache.mkdir()
    calls = []

    def git(*args, data=None):
        argv = ['git', '-C', str(cache), *args]
        process = REAL_RUN(argv, input=data, capture_output=True, timeout=30)
        require(process.returncode == 0, 'synthetic Git setup: ' + repr(process.stderr))
        # git init emits informational stderr on some hosts; retain it as setup,
        # not as a helper archive result or a semantic gate rejection.
        calls.append({'argv': argv, 'returncode': process.returncode,
                      'stdout': process.stdout.decode(), 'stderr': process.stderr.decode()})
        return process.stdout.strip().decode()

    git('init', '--bare', '--quiet')
    root = {}
    for path, data in ORIGINAL.items():
        directory, name = path.split('/')
        blob = git('hash-object', '-w', '--stdin', data=data)
        root.setdefault(directory, []).append('100644 blob ' + blob + '\t' + name + '\n')
    entries = []
    for directory, children in sorted(root.items()):
        tree = git('mktree', data=''.join(sorted(children)).encode())
        entries.append('040000 tree ' + tree + '\t' + directory + '\n')
    pin = git('mktree', data=''.join(entries).encode())
    write_json(log, {'kind': 'SYNTHETIC_GIT_TREE_NOT_PRODUCTION_COMMIT',
                     'pin': pin, 'commands': calls,
                     'original_files': {p: sha(d) for p, d in ORIGINAL.items()}})
    return pin


def archive_bytes(kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        members = list(ORIGINAL.items())
        if kind == 'duplicate':
            members.append(('src/main.txt', b'duplicate\n'))
        elif kind == 'normalized-duplicate':
            members.append(('src/./main.txt', b'duplicate\n'))
        elif kind in ('absolute', 'traversal', 'git-path'):
            name = {'absolute': '/unsafe.txt', 'traversal': '../unsafe.txt',
                    'git-path': '.git/config'}[kind]
            members.append((name, b'unsafe\n'))
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if kind in ('symlink', 'hardlink', 'fifo'):
            info = tarfile.TarInfo('special')
            info.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE,
                         'fifo': tarfile.FIFOTYPE}[kind]
            info.linkname = 'src/main.txt'
            archive.addfile(info)
    return stream.getvalue()


def exception_data(error):
    frames = []
    current = error.__traceback__
    while current:
        frames.append({'path': current.tb_frame.f_code.co_filename,
                       'function': current.tb_frame.f_code.co_name,
                       'line': current.tb_lineno})
        current = current.tb_next
    return {'type': type(error).__name__, 'message': str(error), 'frames': frames}


def exact_rejection(record, expected, helper_path, parser_path):
    if record['type'] != expected['type'] or record['message'] != expected['message']:
        return False
    target = parser_path if expected['origin'] == 'parser' else helper_path
    frames = record['frames']
    return (any(f['path'] == str(target) and f['function'] == 'require' for f in frames)
            and any(f['path'] == str(target) and f['function'] == expected['function']
                    for f in frames))


class Control:
    def __init__(self, output, name, pin, cache, helper_data, parser_data, parser):
        self.name, self.root = name, output / 'cases' / name
        self.root.mkdir(parents=True)
        self.package = self.root / 'source/package/qca-nss/qca-ssdk'
        self.package.mkdir(parents=True)
        self.patches = self.package / 'patches'
        self.patches.mkdir()
        self.recipe = self.package / 'Makefile'
        self.recipe.write_text('PKG_SOURCE_VERSION:=' + pin + '\n')
        self.tests = self.root / 'source/tests'
        self.tests.mkdir()
        self.helper_path = self.tests / 'ssdk_source_prepare.py'
        self.helper_path.write_bytes(helper_data)
        (self.tests / 'edma_patch_context.py').write_bytes(parser_data)
        for filename, data in PATCHES.items():
            (self.patches / filename).write_bytes(data)
        self.h = load_module(self.helper_path, 'ssdk_prepare_control_' + name.replace('-', '_'))
        self.h.PIN = pin
        require(self.h.SOURCE == self.root / 'source' and self.h.PACKAGE == self.package,
                'synthetic SOURCE/PACKAGE were not isolated')
        require(self.h.AUDIT == AUDIT, 'do not weaken actual output boundary')
        require(self.h.inspect_patch is parser.inspect_patch and
                self.h.verify_applied is parser.verify_applied, 'actual parser delegation')
        self.cache, self.prepared = cache, self.root / 'prepare'
        self.commands = self.root / 'commands'
        self.commands.mkdir()
        self.calls, self.events = [], []
        self.patch_calls = 0
        self.inventory_calls = 0
        self.verified = 0
        self.post_calls = 0
        self.expected = None
        self.post_action = None
        self.before_inspect = None
        self.after_verify = None
        self.first_inventory = None
        self.process_action = None

    def reject(self, message, function='prepare', origin='wrapper'):
        self.expected = {'type': 'ValueError' if origin == 'parser' else 'RuntimeError',
                         'message': message, 'function': function, 'origin': origin}

    def event(self, name):
        self.events.append(name)

    def spy(self, argv, **kwargs):
        kind = 'patch' if argv[0] == 'patch' else 'archive'
        require(kind == 'patch' or argv[:1] == ['git'], 'unexpected helper command')
        if kind == 'patch':
            self.patch_calls += 1
        actual = REAL_RUN(argv, **kwargs)
        observed, note = actual, None
        if self.process_action:
            observed, note = self.process_action(kind, actual)
        command_record(self.commands, len(self.calls), argv, kwargs, actual, observed, note)
        self.calls.append({'kind': kind, 'actual_returncode': actual.returncode,
                           'observed_returncode': observed.returncode, 'injection': note})
        return observed

    def run(self):
        h = self.h
        inventory, inspect = h.inventory, h.inspect_patch
        verify, stable = h.verify_applied, h.check_stable_inputs

        def inventory_hook(root):
            self.inventory_calls += 1
            if self.inventory_calls == 1 and self.first_inventory:
                self.first_inventory()
                self.event('first-inventory-injected')
            return inventory(root)

        def inspect_hook(root, data):
            if self.before_inspect:
                self.before_inspect()
                self.event('before-inspect-injected')
            return inspect(root, data)

        def verify_hook(root, expected):
            verify(root, expected)
            self.verified += 1
            if self.after_verify:
                self.after_verify()

        def stable_hook(root, result):
            self.post_calls += 1
            if self.post_action:
                self.post_action()
                self.event('post-stability-injected')
            return stable(root, result)

        error = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(h.subprocess, 'run', self.spy))
            stack.enter_context(mock.patch.object(h, 'inventory', inventory_hook))
            stack.enter_context(mock.patch.object(h, 'inspect_patch', inspect_hook))
            stack.enter_context(mock.patch.object(h, 'verify_applied', verify_hook))
            stack.enter_context(mock.patch.object(h, 'check_stable_inputs', stable_hook))
            stdout = stack.enter_context((self.root / 'helper.stdout').open('w'))
            stderr = stack.enter_context((self.root / 'helper.stderr').open('w'))
            stack.enter_context(contextlib.redirect_stdout(stdout))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            try:
                tree, result = h.prepare(self.cache, self.prepared)
                require(self.expected is None, 'intended rejection did not occur')
                require(result['status'] == 'PASS_TEXT_ONLY', 'positive status')
                require(result['upstream_files'] == {p: sha(d) for p, d in ORIGINAL.items()},
                        'independent complete upstream manifest')
                require(result['prepared_files'] == {p: sha(d) for p, d in FINAL.items()},
                        'independent complete final manifest')
                require(all((tree / p).read_bytes() == d for p, d in FINAL.items()),
                        'independent literal final bytes')
                require(self.verified == 2 and self.patch_calls == 2 and self.post_calls == 1,
                        'positive actual calls')
                require(h.check_stable_inputs(self.prepared, result) ==
                        'PASS_FIXED_INPUTS_INVENTORIES_AND_PREPARED_BYTES_NOT_ATOMIC_LOCK',
                        'repeated actual stability gate')
            except Exception as caught:
                error = caught
        require(not (self.root / 'helper.stdout').read_bytes() and
                not (self.root / 'helper.stderr').read_bytes(), 'helper stream pollution')
        observation = None if error is None else exception_data(error)
        if error is not None:
            (self.root / 'exception.txt').write_text(''.join(traceback.format_exception(
                type(error), error, error.__traceback__)))
        record = {'name': self.name, 'expected_rejection': self.expected,
                  'observed_exception': observation, 'events': self.events,
                  'calls': self.calls, 'verified_patch_outputs': self.verified,
                  'post_stability_calls': self.post_calls,
                  'helper_sha256_at_import': sha(HELPER_BYTES),
                  'parameter_substitution': 'Synthetic SOURCE/PACKAGE and Git tree PIN; unchanged AUDIT',
                  'status': 'INCOMPLETE'}
        write_json(self.root / 'CONTROL.json', record)
        if self.expected is None:
            require(error is None, self.name + ' positive failed: ' + repr(observation))
        else:
            require(error is not None and exact_rejection(observation, self.expected,
                    self.helper_path, PARSER), self.name + ' wrong rejection: ' + repr(observation))
            require(not self.expected['message'].startswith('patch ') or self.calls,
                    'failure without archive witness')
        record['status'] = 'PASS_VALID' if self.expected is None else 'PASS_EXACT_TARGET_REJECTION'
        write_json(self.root / 'CONTROL.json', record)
        return record


def configure(control, kind):
    c, h = control, control.h
    tree = c.prepared / 'prepared'
    saved = c.prepared / 'patches'
    first = '001-first.patch'
    if kind == 'valid':
        return
    if kind == 'existing-output':
        c.prepared.mkdir()
        c.reject('fresh output required')
    elif kind == 'audit-root-output':
        c.prepared = AUDIT
        c.reject('output outside phase3 evidence')
    elif kind in ('outside-output', 'resolved-outside-output'):
        # Both rejection targets already exist: even a missing boundary check
        # would hit the fresh-output guard before any outside mkdir/write.
        require(AUDIT.parent.is_dir(), 'existing outside rejection target')
        c.prepared = AUDIT.parent
        if kind == 'resolved-outside-output':
            c.prepared = c.root / 'outside-link'
            c.prepared.symlink_to(AUDIT.parent, target_is_directory=True)
        c.event('existing-read-only-outside-rejection-target')
        c.reject('output outside phase3 evidence')
    elif kind == 'wrong-pin':
        c.recipe.write_text('PKG_SOURCE_VERSION:=' + '0' * 40 + '\n')
        c.reject('unexpected SSDK source train')
    elif kind == 'bad-patch-name':
        (c.patches / 'invalid.patch').write_bytes(PATCHES[first])
        c.reject('invalid patch inventory')
    elif kind.startswith('archive-'):
        subtype = kind[len('archive-'):]
        if subtype == 'command-error':
            c.reject('exact upstream Git archive failed')
        elif subtype == 'stderr':
            c.reject('exact upstream Git archive failed')
        elif subtype in ('duplicate', 'normalized-duplicate'):
            c.reject('duplicate archive file')
        else:
            member = {'absolute': '/unsafe.txt', 'traversal': '../unsafe.txt',
                      'git-path': '.git/config'}.get(subtype, 'special')
            c.reject('unsupported archive member: ' + member)

        def archive_action(command, p):
            if command != 'archive':
                return p, None
            c.event('archive-result-injected')
            data = p.stdout if subtype in ('command-error', 'stderr') else archive_bytes(subtype)
            return subprocess.CompletedProcess(p.args, 7 if subtype == 'command-error' else 0,
                data, b'injected archive diagnostic\n' if subtype == 'stderr' else b''), subtype
        c.process_action = archive_action
    elif kind == 'extraction-corrupt':
        c.first_inventory = lambda: (tree / 'include/stable.txt').write_bytes(b'changed\n')
        c.reject('archive extraction differs from derived bytes')
    elif kind == 'patch-before-replay':
        c.first_inventory = lambda: (c.patches / first).write_bytes(PATCHES[first] + b'changed\n')
        c.reject('patch changed before replay')
    elif kind in ('preimage-corrupt', 'second-preimage-corrupt'):
        def before_inspect():
            if kind == 'preimage-corrupt' or c.verified == 1:
                path = tree / 'src/main.txt'
                path.write_bytes(path.read_bytes().replace(b'untouched-tail', b'changed-tail'))
        c.before_inspect = before_inspect
        c.reject('patch preimage differs from derived bytes: src/main.txt')
    elif kind.startswith('tool-'):
        subtype = kind[len('tool-'):]
        c.reject('patch tool rejection/shift: ' + first)

        def tool_action(command, p):
            if command != 'patch' or c.patch_calls != 1:
                return p, None
            c.event('patch-result-injected')
            code, stdout, stderr = p.returncode, p.stdout, p.stderr
            if subtype == 'status':
                code = 9
            elif subtype == 'stderr':
                stderr += b'injected tool diagnostic\n'
            else:
                stdout += subtype.encode() + b'\n'
            return subprocess.CompletedProcess(p.args, code, stdout, stderr), subtype
        c.process_action = tool_action
    elif kind == 'output-corrupt':
        c.reject('patch output differs from declared-context result: src/main.txt',
                 'verify_applied', 'parser')

        def output_action(command, p):
            if command == 'patch' and c.patch_calls == 1:
                (tree / 'src/main.txt').write_bytes(b'wrong output\n')
                c.event('touched-output-corrupted')
            return p, 'output-corrupt' if command == 'patch' else None
        c.process_action = output_action
    elif kind in ('orig', 'rej', 'final-untouched-corrupt', 'final-extra'):
        def after_verify():
            if c.verified == 2:
                path = tree / {'orig': 'leftover.orig', 'rej': 'leftover.rej',
                               'final-untouched-corrupt': 'include/stable.txt',
                               'final-extra': 'extra.txt'}[kind]
                path.write_bytes(b'changed before final expected snapshot\n')
                c.event('after-final-verify-injected')
        c.after_verify = after_verify
        c.reject('unexpected replay backups/rejects' if kind in ('orig', 'rej')
                 else 'final source differs from derived bytes')
    else:
        def post_action():
            if kind == 'live-add':
                (c.patches / '003-added.patch').write_bytes(PATCHES[first])
            elif kind == 'live-remove':
                (c.patches / first).unlink()
            elif kind == 'live-rename':
                (c.patches / first).rename(c.patches / '009-renamed.patch')
            elif kind.startswith('live-content-'):
                name = kind[len('live-content-'):]
                path = {'recipe': c.recipe, 'patch': c.patches / first,
                        'helper': c.helper_path, 'parser': c.tests / 'edma_patch_context.py'}[name]
                path.write_bytes(path.read_bytes() + b'\nchanged bound bytes\n')
            elif kind in ('saved-add', 'saved-directory'):
                path = saved / 'extra'
                path.mkdir() if kind == 'saved-directory' else path.write_bytes(b'extra\n')
            elif kind == 'saved-remove':
                (saved / first).unlink()
            elif kind == 'saved-rename':
                (saved / first).rename(saved / '009-renamed.patch')
            elif kind == 'saved-content':
                (saved / first).write_bytes(b'changed saved patch\n')
            elif kind == 'saved-archive':
                path = c.prepared / 'upstream.tar'
                path.write_bytes(path.read_bytes() + b'changed archive\n')
            elif kind.startswith('prepared-'):
                action = kind[len('prepared-'):]
                path = tree / 'include/stable.txt'
                if action == 'content':
                    path.write_bytes(b'changed prepared\n')
                elif action == 'remove':
                    path.unlink()
                elif action == 'add':
                    (tree / 'extra.txt').write_bytes(b'extra\n')
                elif action == 'symlink':
                    path.unlink()
                    path.symlink_to(c.recipe)
                elif action == 'directory-symlink':
                    path.unlink()
                    path.parent.rmdir()
                    path.parent.symlink_to(c.tests, target_is_directory=True)
                else:
                    raise AssertionError('unknown prepared action')
            else:
                raise AssertionError('unknown control ' + kind)
        c.post_action = post_action
        function, message = 'check_stable_inputs', None
        if kind in ('live-add', 'live-remove', 'live-rename'):
            message = 'patch inventory drift'
        elif kind.startswith('live-content-'):
            name = kind[len('live-content-'):]
            path = {'recipe': c.recipe, 'patch': c.patches / first,
                    'helper': c.helper_path, 'parser': c.tests / 'edma_patch_context.py'}[name]
            message = 'live input drift: ' + str(path)
        elif kind in ('saved-add', 'saved-remove', 'saved-rename', 'saved-directory'):
            message = 'saved inventory drift'
        elif kind == 'saved-content':
            message = 'saved patch drift'
        elif kind == 'saved-archive':
            message = 'archive drift'
        elif kind in ('prepared-symlink', 'prepared-directory-symlink'):
            function, message = 'inventory', 'symlink in prepared tree'
        elif kind.startswith('prepared-'):
            message = 'prepared tree drift'
        require(message is not None, 'missing exact expected gate')
        c.reject(message, function)


CONTROL_KINDS = [
    'valid', 'existing-output', 'audit-root-output', 'outside-output',
    'resolved-outside-output', 'wrong-pin', 'bad-patch-name',
    'archive-command-error', 'archive-stderr', 'archive-duplicate',
    'archive-normalized-duplicate', 'archive-absolute', 'archive-traversal',
    'archive-git-path', 'archive-symlink', 'archive-hardlink', 'archive-fifo',
    'extraction-corrupt', 'patch-before-replay', 'preimage-corrupt',
    'second-preimage-corrupt', 'tool-status', 'tool-stderr', 'tool-offset',
    'tool-fuzz', 'tool-FAILED', 'tool-reject', 'tool-malformed', 'tool-Reversed',
    'tool-previously applied', 'output-corrupt', 'orig', 'rej',
    'final-untouched-corrupt', 'final-extra', 'live-add', 'live-remove',
    'live-rename', 'live-content-recipe', 'live-content-patch', 'live-content-helper',
    'live-content-parser', 'saved-add', 'saved-remove', 'saved-rename',
    'saved-directory', 'saved-content', 'saved-archive', 'prepared-content',
    'prepared-remove', 'prepared-add', 'prepared-symlink', 'prepared-directory-symlink',
]


def oracle_controls(record, control):
    observed, expected = record['observed_exception'], record['expected_rejection']
    tests = [('valid-exact', observed, True)]
    for name in ('type', 'message', 'substring', 'require-frame', 'target-frame'):
        changed = copy.deepcopy(observed)
        if name == 'type':
            changed['type'] = 'ValueError'
        elif name == 'message':
            changed['message'] += ' extra'
        elif name == 'substring':
            changed['message'] = 'prefix ' + changed['message'] + ' suffix'
        else:
            function = 'require' if name == 'require-frame' else expected['function']
            changed['frames'] = [f for f in changed['frames'] if f['function'] != function]
        tests.append(('reject-' + name, changed, False))
    result = []
    for name, value, wanted in tests:
        actual = exact_rejection(value, expected, control.helper_path, PARSER)
        require(actual == wanted, 'exact rejection predicate control: ' + name)
        result.append({'name': name, 'expected_accept': wanted, 'actual_accept': actual})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    output = args.output.resolve()
    require(output.parent == AUDIT and output.name.startswith('SSDK-PREP-CONTROLS-'),
            'only direct SSDK-PREP-CONTROLS-* evidence output is allowed')
    require(not output.exists(), 'fresh controls output required')
    global HELPER_BYTES
    HELPER_BYTES, parser_bytes = HELPER.read_bytes(), PARSER.read_bytes()
    owned = {str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())}
    protected = {str(p): sha(p.read_bytes()) for p in [HELPER, PARSER,
                 SOURCE / 'package/qca-nss/qca-ssdk/Makefile',
                 *sorted((SOURCE / 'package/qca-nss/qca-ssdk/patches').glob('*.patch'))]}
    output.mkdir()
    result = {'status': 'INCOMPLETE', 'qualification': 'AUTHOR_WRAPPER_CONTROLS_NOT_INDEPENDENT_SIGNOFF',
              'frozen_files': owned, 'helper_and_protected_inputs': protected,
              'controls': [], 'limits': [
                  'Synthetic SOURCE/PACKAGE/recipe and Git tree PIN are control parameter substitutes, not SSDK d9a1964 provenance.',
                  'Actual helper bodies and shared parser functions are used; old 29 parser controls are not rerun or claimed as wrapper coverage.',
                  'Fault-injected process observations are labeled separately from retained actual command streams.',
                  'No C/make/target/device execution, production edits, index staging or commits; no independent review of this newly authored test.']}
    write_json(output / 'RESULTS.json', result)
    try:
        parser = load_module(PARSER, 'edma_patch_context')
        with mock.patch.dict(sys.modules, {'edma_patch_context': parser}):
            pin = make_git_tree(output / 'synthetic-git', output / 'GIT-SETUP.json')
            result['synthetic_tree_pin'] = pin
            first_rejected = None
            for number, kind in enumerate(CONTROL_KINDS):
                name = '%02d-' % number + kind.replace(' ', '-')
                control = Control(output, name, pin, output / 'synthetic-git',
                                  HELPER_BYTES, parser_bytes, parser)
                configure(control, kind)
                record = control.run()
                result['controls'].append(record)
                if record['expected_rejection'] and first_rejected is None:
                    first_rejected = (record, control)
                write_json(output / 'RESULTS.json', result)
            require([r['name'].split('-', 1)[1] for r in result['controls']] ==
                    [k.replace(' ', '-') for k in CONTROL_KINDS], 'complete frozen case ledger')
            result['oracle_controls'] = oracle_controls(*first_rejected)
        for path, expected in {**protected, **owned}.items():
            require(sha(Path(path).read_bytes()) == expected, 'protected/test input drift: ' + path)
        result['valid_controls'] = sum(r['expected_rejection'] is None for r in result['controls'])
        result['exact_rejections'] = sum(r['expected_rejection'] is not None for r in result['controls'])
        result['status'] = 'PASS_ACTUAL_WRAPPER_CONTROLS'
    except Exception as error:
        result['failure'] = exception_data(error)
        (output / 'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        write_json(output / 'RESULTS.json', result)
    print(json.dumps({'status': result['status'], 'output': str(output),
                      'valid': result['valid_controls'], 'exact_rejections': result['exact_rejections'],
                      'oracle_controls': len(result['oracle_controls'])}))


if __name__ == '__main__':
    main()
