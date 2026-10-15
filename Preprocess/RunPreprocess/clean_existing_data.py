"""Offline CSV filtering with recoverable, atomic file replacement."""
import csv
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXCLUDE_KEYWORDS = (
    "롯데리아", "맥도날드", "버거킹", "맘스터치", "KFC", "노브랜드버거",
    "메가커피", "메가MGC커피", "빽다방", "스타벅스", "이디야", "투썸플레이스",
    "컴포즈커피", "할리스", "파스쿠찌", "탐앤탐스",
    "파리바게뜨", "뚜레쥬르", "배스킨라빈스", "던킨",
    "교촌치킨", "BHC", "bhc", "BBQ", "bbq", "굽네치킨",
    "서브웨이", "써브웨이", "김밥천국", "이삭토스트",
    "CU", "GS25", "세븐일레븐", "이마트24", "미니스톱",
    "공인중개사", "부동산", "아파트", "빌라", "오피스텔",
    "학원", "어린이집", "유치원", "독서실", "교습소", "스터디카페",
    "요양원", "주간보호", "치과", "내과", "한의원", "동물병원",
    "세탁소", "크린토피아", "철물점", "인테리어", "카센터", "공업사", "고물상",
    "건설", "정비", "철강", "다이소", "미용실", "화학", "기업", "사무소", "(주)",
    "전자", "전기", "제조", "물류", "화물", "용달", "택배", "운송", "견인",
    "장례", "납골당", "추모", "묘원",
    "국민은행", "신한은행", "우리은행", "하나은행", "농협", "새마을금고", "신협", "기업은행",
    "ATM", "우체국", "행정복지센터", "주민센터", "경찰서", "지구대", "소방서", "보험", "세무", "법무", "노무",
    "설비", "자재", "철거", "폐기물", "간판", "인쇄", "방수", "배관", "샷시",
    "네일", "속눈썹", "헬스장", "피트니스", "필라테스", "요가", "안경",
    "정형외과", "산부인과", "조리원", "성형외과", "피부과", "비뇨기과", "이비인후과",
    "타이어", "세차", "썬팅", "광택", "블랙박스",
    "롯데슈퍼", "GS더프레시", "이마트에브리데이", "홈플러스익스프레스",
    "이마트", "홈플러스", "롯데마트", "하나로마트", "주유소", "충전소", "LPG"
)


def _replace_csv(path, write):
    """Prepare the entire output before backing up and replacing the source."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        write(Path(temporary))
        if path.exists():
            backup = Path(str(path) + '.bak')
            if backup.exists():
                backup = Path(f'{path}.backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}')
            shutil.copy2(path, backup)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clean_existing_csv_files(folder=None):
    folder = Path(folder) if folder is not None else Path(__file__).resolve().parents[1] / 'data/chungnam_data'
    if not folder.is_dir():
        print('데이터 폴더가 존재하지 않습니다.')
        return
    cleaned_file_count = removed_row_count = 0
    for path in sorted(folder.glob('*.csv')):
        with path.open('r', encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            fieldnames = reader.fieldnames
            rows = list(reader)
        kept = [row for row in rows if not any(
            keyword in f"{row.get('가게명', '')} {row.get('카테고리', '')}" for keyword in EXCLUDE_KEYWORDS)]
        if len(kept) == len(rows):
            continue
        def write(temporary):
            with temporary.open('w', encoding='utf-8-sig', newline='') as target:
                writer = csv.DictWriter(target, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(kept)
        _replace_csv(path, write)
        cleaned_file_count += 1
        removed_row_count += len(rows) - len(kept)
    print(f'정제 완료: {cleaned_file_count}개 파일에서 총 {removed_row_count}개의 불필요한 데이터를 삭제했습니다.')


if __name__ == '__main__':
    clean_existing_csv_files()
