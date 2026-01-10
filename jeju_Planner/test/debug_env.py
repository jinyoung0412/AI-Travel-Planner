# debug_env.py
import os

# 프로젝트 루트 경로 (직접 수정하거나, 상대 경로로 설정)
# 에러 메시지에 떴던 그 경로를 그대로 적어주세요.
target_path = r"c:\Jeju-Travel-AI"

print(f"📂 검사 경로: {target_path}")

if not os.path.exists(target_path):
    print("❌ 경로가 존재하지 않습니다.")
else:
    files = os.listdir(target_path)
    print(f"📄 파일 목록 ({len(files)}개):")
    found = False
    for f in files:
        if ".env" in f:
            print(f"   -> 발견됨: '{f}' (정확한 철자를 확인하세요)")
            found = True
    
    if not found:
        print("   -> ❌ '.env'가 포함된 파일이 아예 없습니다.")
    
    if ".env.txt" in files:
        print("\n🚨 [진단 결과] 범인을 찾았습니다! 파일명이 '.env.txt' 입니다.")
        print("   -> 해결책: 파일 이름을 바꾸거나, VS Code에서 새로 만드세요.")