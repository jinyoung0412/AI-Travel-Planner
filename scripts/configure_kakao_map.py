#!/usr/bin/env python3
"""Store the map's JavaScript key locally without echoing it or using argv."""
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'android_app' / '.local' / 'kakao-map.json'


def canonical_origin(value):
    uri = urlsplit(value.strip())
    if (uri.scheme != 'https' or not uri.hostname or uri.username or uri.password
            or uri.path not in ('', '/') or uri.query or uri.fragment):
        raise ValueError('출처는 경로 없는 HTTPS 주소여야 합니다.')
    return f'https://{uri.netloc}'


def save_configuration(key, origin, destination=DESTINATION):
    if not re.fullmatch(r'[a-fA-F0-9]{32}', key):
        raise ValueError('카카오 JavaScript 키 형식을 확인해주세요.')
    origin = canonical_origin(origin)
    # A server REST key must never be repackaged into the mobile application.
    env_path = ROOT / '.env'
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            match = re.match(r'\s*KAKAO_API_KEY\s*=\s*(.*?)\s*$', line)
            if match and match[1].strip('\"\'') == key:
                raise ValueError('서버 REST 키 대신 별도의 JavaScript 키를 입력해주세요.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({
                'API_BASE_URL': 'http://127.0.0.1:8080',
                'KAKAO_MAP_JAVASCRIPT_KEY': key,
                'KAKAO_MAP_ORIGIN': origin,
            }, stream, indent=2)
            stream.write('\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if not sys.stdin.isatty():
        print('터미널에서 실행해주세요. 키를 명령행 인수나 파이프로 전달하지 마세요.')
        return 1
    try:
        key = getpass.getpass('카카오 JavaScript 키 (화면에 표시되지 않음): ').strip()
        origin = input('등록한 JavaScript SDK 도메인 [https://localhost]: ').strip()
        save_configuration(key, origin or 'https://localhost')
    except (ValueError, OSError):
        print('저장하지 않았습니다. JavaScript 키와 HTTPS 도메인을 확인해주세요.')
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\n저장하지 않았습니다.')
        return 1
    print('지도 설정을 로컬 전용 파일에 저장했습니다. 키는 출력하지 않았습니다.')
    print(DESTINATION)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
