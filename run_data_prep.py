"""Portable stage runner; default --check does not crawl or call paid APIs."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGES = {
    'crawl': ROOT / 'Preprocess/RunPreprocess/run_crawling.py',
    'prepare': ROOT / 'Preprocess/RunPreprocess/data_pipeline.py',
    'blogs': ROOT / 'Preprocess/RunPreprocess/collect_blog_tags.py',
    'build': ROOT / 'Preprocess/RunPreprocess/build_database.py',
    'migrate': ROOT / 'Preprocess/RunPreprocess/migrate_place_ids.py',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--stage', choices=STAGES)
    args, stage_args = parser.parse_known_args()
    if args.check or not args.stage:
        missing = [str(path) for path in STAGES.values() if not path.is_file()]
        if missing:
            raise SystemExit('없는 단계: ' + ', '.join(missing))
        for name, path in STAGES.items():
            print(f'{name}: {path.relative_to(ROOT)}')
        print('경로 확인 완료. --stage로 실행할 단계를 지정하세요. crawl/prepare/blogs는 외부 API 또는 브라우저를 사용합니다.')
        return
    subprocess.run([sys.executable, str(STAGES[args.stage]), *stage_args], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
