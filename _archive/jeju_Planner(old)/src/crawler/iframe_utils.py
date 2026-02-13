# iframe_utils.py
import time
from selenium.webdriver.common.by import By

def detect_list_panel(driver):
    selectors = ["#_pcmap_list_scroll_container", "div.search_list_wrap", "div[data-view-type='list']"]
    for sel in selectors:
        if driver.find_elements(By.CSS_SELECTOR, sel): return True
    return False

def wait_for_list_panel(driver, timeout=10):
    driver.switch_to.default_content()
    for _ in range(timeout):
        # iframe 체크
        frames = driver.find_elements(By.CSS_SELECTOR, "#searchIframe")
        if frames:
            driver.switch_to.frame(frames[0])
            return True
        # div 체크 (모바일뷰 등)
        if detect_list_panel(driver):
            return True
        time.sleep(1)
    return False

def lock_to_list_panel(driver):
    selectors = ["#_pcmap_list_scroll_container", "div.search_list_wrap", "div[data-view-type='list']"]
    for sel in selectors:
        try:
            return driver.find_element(By.CSS_SELECTOR, sel)
        except: continue
    return None

def open_list_panel_force(driver):
    driver.switch_to.default_content()
    driver.execute_script("document.querySelector('#sidebar > button')?.click();")

def wait_for_entry_iframe(driver, timeout=10):
    driver.switch_to.default_content()
    for _ in range(timeout):
        frames = driver.find_elements(By.ID, "entryIframe")
        if frames:
            driver.switch_to.frame(frames[0])
            return True
        time.sleep(1)
    return False