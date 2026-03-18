import os
import csv

def clean_existing_csv_files():
    folder = r"C:\AI-Travel-Planner\Preprocess\data\chungnam_data"
    
    exclude_keywords = [
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
    ]

    if not os.path.exists(folder):
        print("데이터 폴더가 존재하지 않습니다.")
        return

    cleaned_file_count = 0
    removed_row_count = 0

    for filename in os.listdir(folder):
        if filename.endswith(".csv"):
            filepath = os.path.join(folder, filename)
            
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = list(csv.DictReader(f))
                if not reader:
                    continue
                fieldnames = reader[0].keys()

            cleaned_rows = []
            file_modified = False

            for row in reader:
                name = row.get("가게명", "")
                category = row.get("카테고리", "")
                
                target_text = f"{name} {category}"
                is_excluded = any(kw in target_text for kw in exclude_keywords)
                
                if not is_excluded:
                    cleaned_rows.append(row)
                else:
                    file_modified = True
                    removed_row_count += 1

            if file_modified:
                with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(cleaned_rows)
                cleaned_file_count += 1

    print(f"정제 완료: {cleaned_file_count}개 파일에서 총 {removed_row_count}개의 불필요한 데이터를 삭제했습니다.")

if __name__ == "__main__":
    clean_existing_csv_files()