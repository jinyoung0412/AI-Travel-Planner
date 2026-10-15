"""Run installed offline regression suites and preserve the frozen source data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FROZEN = (ROOT / 'Flask_server/places.db', ROOT / 'Preprocess/pilots/homonym_5.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commands(component, flutter):
    if component in ('all', 'python'):
        for args in (
            ['-m', 'pytest', '-q'],
            ['Flask_server/test_algorithm.py'],
            ['run_data_prep.py', '--check'],
            ['scripts/validate_real_db.py'],
            ['scripts/validate_rebuild_preservation.py'],
        ):
            yield [sys.executable, *args], ROOT
    if component in ('all', 'node'):
        yield ['npm', 'test', '--prefix', 'NodeJs_server'], ROOT
        for path in sorted((ROOT / 'NodeJs_server').glob('*.js')):
            yield ['node', '--check', str(path)], ROOT
    if component in ('all', 'flutter'):
        yield [flutter, 'analyze', '--no-pub'], ROOT / 'android_app'
        yield [flutter, 'test', '--no-pub'], ROOT / 'android_app'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=('all', 'python', 'node', 'flutter'), default='all')
    parser.add_argument('--flutter', default='flutter', help='Installed Flutter executable')
    args = parser.parse_args()
    hashes = {path: digest(path) for path in FROZEN}
    manifest = json.loads(FROZEN[1].read_text())
    if hashes[FROZEN[0]] != manifest['baseline_db_sha256'] or manifest['collection_authorized_now'] is not False:
        raise SystemExit('Frozen DB or collection authorization differs from the reviewed baseline')
    env = os.environ.copy()
    for key in ('ANTHROPIC_API_KEY', 'KAKAO_API_KEY', 'NAVER_API_ID', 'NAVER_API_SECRET'):
        env[key] = ''
    try:
        for command, cwd in commands(args.component, args.flutter):
            print(f'[{cwd.relative_to(ROOT) or "."}] {" ".join(command)}', flush=True)
            subprocess.run(command, cwd=cwd, env=env, check=True)
    finally:
        changed = [str(p.relative_to(ROOT)) for p, before in hashes.items() if digest(p) != before]
        if changed:
            raise RuntimeError('Frozen source data changed: ' + ', '.join(changed))
        print('Frozen DB and pilot SHA-256 preserved.', flush=True)


if __name__ == '__main__':
    main()
