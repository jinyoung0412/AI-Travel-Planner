import os

target = r"c:\Chungnam-Travel-AI"

print(f"📂 검사 경로: {target}")

if not os.path.exists(target):
    print("❌ 경로 없음.")
else:
    files = os.listdir(target)
    print(f"📄 파일 목록:")
    found = False
    for f in files:
        if f == ".env":
            print("   → .env 발견됨")
            found = True

    if not found:
        print("❌ .env 없음")
