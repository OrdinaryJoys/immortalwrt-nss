#!/usr/bin/env python3
"""Native sanitizer activation and fail-closed controls, not driver qualification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
RUNNER = Path(__file__).with_name('test-ssdk-phy-ops-lifetime.py')
spec = importlib.util.spec_from_file_location('phy_canary_runner', RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    assets = (Path(__file__), RUNNER, runner.source.EXTRACTOR, runner.source.CONTEXT,
              *sorted(runner.SUPPORT.glob('*')))
    runner.source.require(all(p.is_file() for p in assets), 'complete canary input assets')
    inputs = {str(p): runner.source.sha(p.read_bytes()) for p in assets}
    report = dict(status='INCOMPLETE', scope='SANITIZER_CONTROLS_NOT_SOURCE_MUTANTS_OR_TARGET',
                  inputs=inputs, disabled_controls=[], crossed_identity_controls=[])
    env = dict(os.environ)
    try:
        report['compiler'] = runner.invoke([args.cc, '--version'], out, 'compiler')
        runner.source.require(report['compiler']['returncode'] == 0, 'compiler identity')
        report['oracle_controls'] = runner.sanitizer_oracle_controls()
        report['canaries'] = runner.verify_sanitizer_canaries(args.cc, out, env)
        for kind in ('asan', 'ubsan'):
            row = report['canaries'][kind]
            other = 'ubsan' if kind == 'asan' else 'asan'
            crossed = dict(row['run'], returncode={'asan': 97, 'ubsan': 98}[other])
            runner.source.require(not runner.sanitizer_result(crossed, other),
                                  'wrong sanitizer identity must not earn activation')
            report['crossed_identity_controls'].append(dict(actual=kind, rejected_as=other))
            binary, record = runner.compile_program(args.cc, out, 'disabled-' + kind,
                                                     runner.CANARY_PROGRAMS[kind], 'full', None)
            raw = runner.invoke([binary], out, 'disabled-' + kind + '.run', env)
            runner.source.require(not runner.sanitizer_result(raw, kind),
                                  'disabled sanitizer must not earn activation')
            # An uninstrumented probe may crash; it earns no semantic-mutant credit.
            report['disabled_controls'].append(dict(kind=kind, run=raw, **record))
        campaign_flags = runner.host_flags('address,undefined')
        runner.source.require('-fsanitize=address,undefined' in campaign_flags and
                              '-fno-sanitize-recover=all' in campaign_flags,
                              'formal campaign retains both sanitizers')
        report['formal_campaign_flags'] = campaign_flags
        runner.source.require(env == dict(os.environ), 'parent sanitizer environment unchanged')
        runner.source.require(all(runner.source.sha(Path(p).read_bytes()) == h for p, h in inputs.items()),
                              'canary input stability')
        report['generated_files'] = {p.relative_to(out).as_posix(): runner.source.sha(p.read_bytes())
                                     for p in sorted(out.rglob('*')) if p.is_file()}
        report['status'] = 'PASS_SANITIZER_CONTROLS_ONLY'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], activation=2, disabled_controls=2,
                         crossed_identity_controls=2,
                         oracle_rejections=report['oracle_controls']['rejected_pollution'])))


if __name__ == '__main__':
    main()
