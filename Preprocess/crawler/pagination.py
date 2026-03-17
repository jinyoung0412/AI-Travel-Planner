# Preprocess/crawler/pagination.py

from selenium.webdriver.common.by import By
import time

def go_next_page(driver):
    """
    [Clean Version] '다음' 버튼 클릭 (시각 효과 제거)
    """
    try:
        driver.switch_to.default_content()
        frames = driver.find_elements(By.ID, "searchIframe")
        if frames: driver.switch_to.frame(frames[0])

        xpath = "//a[@aria-disabled='false' and .//span[contains(text(), '다음')]]"
        next_btns = driver.find_elements(By.XPATH, xpath)
        
        if next_btns:
            btn = next_btns[-1]
            # 스크롤 후 바로 클릭
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(3.0) 
            return True
        else:
            return False
            
    except Exception as e:
        # print(f"   [페이지 이동 에러] {e}")
        return False