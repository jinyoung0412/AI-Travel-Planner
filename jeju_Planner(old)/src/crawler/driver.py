# driver.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def create_driver():
    options = webdriver.ChromeOptions()
    
    # 1. [헤드리스 & 기본 설정]
    options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # ----------------------------------------------------------
    # 2. [그래픽 카드 이슈 해결] 7500F 맞춤형 설정 (중요!)
    # ----------------------------------------------------------
    # GPU 가속을 끄고, 소프트웨어 렌더링(SwiftShader)을 강제합니다.
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer") # 소프트웨어 래스터라이저 비활성
    
    # [핵심] 로그에서 요구한 옵션: WebGL 안전모드 무시 (크롤링엔 문제 없음)
    options.add_argument("--enable-unsafe-swiftshader") 
    
    # WebGL(3D 맵) 자체를 최대한 억제
    options.add_argument("--disable-webgl")
    options.add_argument("--disable-webgl2")
    
    # 지긋지긋한 GPU 에러 로그 숨기기
    options.add_argument("--log-level=3") 
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # ----------------------------------------------------------

    # 3. [안전] 봇 탐지 우회
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 4. [속도] 이미지 로딩 차단 (기존 코드 유지)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2, # 알림 팝업 차단
        "profile.managed_default_content_settings.popups": 2,      # 팝업 차단
        "profile.managed_default_content_settings.geolocation": 2  # 위치 정보 차단
    }
    options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )