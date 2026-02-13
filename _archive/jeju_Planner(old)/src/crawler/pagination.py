# pagination.py
import time
from selenium.webdriver.common.by import By
from .iframe_utils import wait_for_list_panel

def go_next_page(driver):
    driver.switch_to.default_content()
    
    # 현재 활성화된 페이지 번호 찾기
    current_idx = -1
    buttons = driver.find_elements(By.CSS_SELECTOR, "a.mBN2s, a[role='button']")
    real_buttons = [b for b in buttons if b.text.isdigit()] # 숫자 버튼만

    for i, btn in enumerate(real_buttons):
        # active 클래스나 aria-selected 속성 확인
        if "active" in btn.get_attribute("class") or \
           "true" == btn.get_attribute("aria-selected") or \
           "qxokY" in btn.get_attribute("class"):
            current_idx = i
            break
    
    # 다음 버튼 찾기
    next_btn = None
    
    # 1. 번호 이동 (1 -> 2)
    if current_idx != -1 and current_idx < len(real_buttons) - 1:
        next_btn = real_buttons[current_idx + 1]
    else:
        # 2. 화살표 이동 (>)
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "a.eUTV2:not([aria-disabled='true'])")
        except:
            return False # 다음 버튼 없음

    # 클릭 시도
    try:
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(1.5)
        return wait_for_list_panel(driver)
    except:
        return False