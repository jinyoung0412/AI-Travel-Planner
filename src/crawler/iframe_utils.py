# src/crawler/iframe_utils.py

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def wait_for_list_panel(driver, timeout=10):
    """왼쪽 리스트 프레임(searchIframe)이 뜰 때까지 기다리고 진입"""
    try:
        driver.switch_to.default_content()
        WebDriverWait(driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "searchIframe"))
        )
        return True
    except:
        return False

def open_list_panel_force(driver):
    """혹시 리스트가 닫혀있으면 여는 함수 (보통 검색하면 자동으로 열려서 필수는 아님)"""
    pass 

def lock_to_list_panel(driver):
    """스크롤할 영역(_pcmap_list_scroll_container)을 찾아 반환"""
    try:
        # 이미 searchIframe 안에 있다고 가정
        scroll_box = driver.find_element(By.ID, "_pcmap_list_scroll_container")
        return scroll_box
    except:
        return None