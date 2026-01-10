import subprocess
import sys
import os
import time

def print_header(step_num, title):
    print("\n" + "=" * 60)
    print(f"🚀 [Step {step_num}] {title} 시작")
    print("=" * 60)

def run_script(script_path):
    """
    지정된 파이썬 스크립트를 서브 프로세스로 실행합니다.
    """
    # 스크립트 파일 존재 여부 확인
    if not os.path.exists(script_path):
        print(f"❌ [Error] 파일을 찾을 수 없습니다: {script_path}")
        return False

    try:
        # 현재 파이썬 인터프리터(sys.executable)를 사용하여 실행 (가상환경 유지)
        # check=True: 에러 발생 시 즉시 예외 발생
        subprocess.run([sys.executable, script_path], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n🔥 [Critical Error] 스크립트 실행 중 오류 발생!")
        print(f"   -> 파일: {script_path}")
        print(f"   -> 종료 코드: {e.returncode}")
        return False

def main():
    total_start_time = time.time()
    
    print("\n🏝️  [Jeju Travel AI] 데이터 수집 및 전처리 파이프라인 가동 🏝️")
    print(f"📂 실행 위치: {os.getcwd()}")
    print("ℹ️  AI 분석(Clustering) 단계는 제외되었습니다. (서버에서 사용자 요청 시 실행됨)")

    # ----------------------------------------------------------------
    # 📋 실행할 단계 정의 (순서대로 실행됨)
    # ----------------------------------------------------------------
    pipeline_steps = [
        {
            "name": "1. 데이터 크롤링 (Data Crawling)",
            "path": os.path.join("src", "crawler", "run_crawling.py")
        },
        {
            "name": "2. 데이터 통합 (Data Integration)",
            "path": os.path.join("src", "preprocessing", "data_integration.py")
        },
        {
            "name": "3. 지오코딩 (Geocoding - 좌표 변환)",
            "path": os.path.join("src", "preprocessing", "geocoding.py")
        }
    ]
    # ----------------------------------------------------------------

    for i, step in enumerate(pipeline_steps, start=1):
        step_name = step["name"]
        script_path = step["path"]

        print_header(i, step_name)
        
        # 스크립트 실행
        success = run_script(script_path)
        
        # 실패 시 파이프라인 즉시 중단 (다음 단계로 넘어가면 데이터 꼬임)
        if not success:
            print(f"\n❌ {step_name} 단계에서 실패하여 전체 작업을 중단합니다.")
            sys.exit(1)
        
        print(f"✅ {step_name} 완료!")
        time.sleep(1) # 로그 가독성을 위해 잠시 대기

    # 전체 완료 메시지
    total_end_time = time.time()
    duration = total_end_time - total_start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    # 최종 결과물 경로 확인
    final_output = os.path.join("data", "processed", "jeju_places_with_coords_safe.csv")
    
    print("\n" + "#" * 60)
    print(f"🎉 데이터 준비 작업이 모두 완료되었습니다! 🎉")
    print(f"⏱️  총 소요 시간: {minutes}분 {seconds}초")
    
    if os.path.exists(final_output):
         print(f"📂 최종 데이터 생성됨: {final_output}")
         print("👉 이제 Flask 서버(app.py)를 실행할 준비가 되었습니다.")
    else:
         print("⚠️ 경고: 모든 과정이 끝났으나 최종 파일이 보이지 않습니다.")
         
    print("#" * 60)

if __name__ == "__main__":
    main()