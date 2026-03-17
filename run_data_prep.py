import subprocess
import sys
import os
import time

def print_header(step_num, title):
    print("\n" + "=" * 60)
    print(f"🚀 [Step {step_num}] {title} 시작")
    print("=" * 60)

def run_script(script_path):
    if not os.path.exists(script_path):
        print(f"❌ [Error] 파일을 찾을 수 없습니다: {script_path}")
        return False

    try:
        subprocess.run([sys.executable, script_path], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n🔥 [Critical Error] 스크립트 실행 중 오류 발생!")
        print(f"   -> 파일: {script_path}")
        print(f"   -> 종료 코드: {e.returncode}")
        return False

def main():
    total_start_time = time.time()
    
    print("\n🌄 [Chungnam Travel AI] 데이터 수집 및 전처리 파이프라인 가동")
    print(f"📂 실행 위치: {os.getcwd()}")
    print("ℹ️ AI 클러스터링 단계는 서버 요청 시 실행됩니다.")

    pipeline_steps = [
        {
            "name": "1. 데이터 크롤링 (Data Crawling)",
            "path": os.path.join("Preprocess", "crawler", "run_crawling.py")
        },
        {
            "name": "2. 데이터 통합 (Data Integration)",
            "path": os.path.join("Preprocess", "preprocessing", "data_integration.py")
        },
        {
            "name": "3. 지오코딩 (Geocoding - 좌표 변환)",
            "path": os.path.join("Preprocess", "preprocessing", "geocoding.py")
        }
    ]

    for i, step in enumerate(pipeline_steps, start=1):
        print_header(i, step["name"])
        
        success = run_script(step["path"])
        
        if not success:
            print(f"\n❌ {step['name']} 단계 실패! 전체 작업 중단합니다.")
            sys.exit(1)
        
        print(f"✅ {step['name']} 완료!")
        time.sleep(1)

    final_output = os.path.join(
        "data", "processed", "chungnam_places_with_coords_safe.csv"
    )

    total_end_time = time.time()
    duration = total_end_time - total_start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    print("\n" + "#" * 60)
    print(f"🎉 데이터 준비 작업이 모두 완료되었습니다!")
    print(f"⏱️ 총 소요 시간: {minutes}분 {seconds}초")
    
    if os.path.exists(final_output):
        print(f"📂 최종 데이터 생성됨: {final_output}")
        print("👉 이제 Flask 서버(app.py)를 실행할 수 있습니다.")
    else:
        print("⚠️ 최종 파일이 보이지 않습니다.")
        
    print("#" * 60)

if __name__ == "__main__":
    main()
