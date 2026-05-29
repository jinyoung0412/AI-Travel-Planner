# Preprocess/crawler/iframe_utils.py
#
# 네이버 지도 iframe 진입/제어 유틸리티.
#
# 네이버 지도는 검색 결과 리스트와 장소 상세 페이지가 각각 별도의 iframe
# (searchIframe / entryIframe) 안에 렌더링되는 구조이다. Selenium은 기본적으로
# 최상위 문서(default_content)만 바라보기 때문에, iframe 내부 요소에 접근하려면
# 매번 명시적으로 컨텍스트를 전환(switch_to)해줘야 한다.
#
# 이 모듈은 그 중에서도 "왼쪽 검색 결과 리스트" iframe(searchIframe) 진입과
# 내부 스크롤 컨테이너 탐색을 담당한다.

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def wait_for_list_panel(driver, timeout=10):
    """
    왼쪽 검색 결과 리스트 iframe(searchIframe)이 로드되기를 기다린 뒤
    드라이버 컨텍스트를 해당 iframe 내부로 전환한다.

    동작 흐름:
      1) 일단 최상위 문서로 복귀해 이전 iframe 상태를 초기화한다.
         (이미 다른 iframe 안에 들어가 있을 가능성이 있음)
      2) searchIframe ID를 가진 프레임이 DOM에 나타날 때까지 timeout 초까지 대기.
      3) 사용 가능해지면 자동으로 그 iframe 내부로 switch_to 수행.

    반환값:
      - True  : iframe 진입 성공 (이후 호출되는 find_element 등은 모두 iframe 내부 기준)
      - False : 타임아웃·예외 발생 시 (페이지가 아직 안 떴거나 검색 실패 상태)
    """
    try:
        driver.switch_to.default_content()
        WebDriverWait(driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "searchIframe"))
        )
        return True
    except:
        return False

def open_list_panel_force(driver):
    """
    리스트 패널이 닫혀 있을 경우 강제로 여는 용도로 마련된 자리.

    실제로는 네이버 지도에서 키워드 검색을 수행하면 리스트 패널이 자동으로
    열리기 때문에, 현재 크롤링 플로우에서는 호출이 필수가 아니다.
    추후 UI 변경으로 자동 오픈이 안 되는 케이스가 생길 경우를 대비한 훅(hook).
    """
    pass

def lock_to_list_panel(driver):
    """
    리스트 iframe 내부에서 실제로 스크롤이 동작하는 컨테이너 요소를 찾아 반환.

    네이버 지도의 검색 결과는 무한 스크롤(혹은 페이지네이션) 방식으로 동작하며,
    더 많은 항목을 로드하려면 이 스크롤 컨테이너(_pcmap_list_scroll_container)에
    대해 직접 scroll 이벤트를 발생시켜야 한다.

    전제 조건:
      - 호출 시점에 드라이버는 이미 searchIframe 내부에 진입한 상태여야 한다
        (보통 wait_for_list_panel()이 먼저 호출되어 있어야 함).

    반환값:
      - WebElement : 스크롤 컨테이너 요소
      - None       : 요소를 찾지 못한 경우 (페이지 구조 변경 가능성)
    """
    try:
        # 이미 searchIframe 안에 있다고 가정
        scroll_box = driver.find_element(By.ID, "_pcmap_list_scroll_container")
        return scroll_box
    except:
        return None