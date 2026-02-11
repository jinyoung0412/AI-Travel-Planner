import sys

print("🔍 환경 설정 검사 중...")

try:
    # 1. AI 핵심
    import sklearn
    import numpy
    print(f"✅ AI 라이브러리 설치 완료 (sklearn: {sklearn.__version__})")
    
    # 2. 크롤링 핵심
    import selenium
    import bs4
    print(f"✅ 크롤링 라이브러리 설치 완료 (selenium: {selenium.__version__})")
    
    # 3. DB 핵심 (가장 중요!)
    import mysql.connector
    print("✅ DB 커넥터(mysql-connector) 설치 완료!")
    
    print("\n🎉 모든 설정이 완벽합니다! 팀원들에게 배포해도 좋습니다.")
    
except ImportError as e:
    print(f"\n🚨 비상! 라이브러리가 빠져 있습니다: {e}")
    print("👉 'conda env update -f environment.yml' 명령어를 다시 실행하세요.")