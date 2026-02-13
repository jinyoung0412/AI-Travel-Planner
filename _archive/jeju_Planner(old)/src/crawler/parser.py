# parser.py
from selenium.webdriver.common.by import By
from .iframe_utils import detect_list_panel, wait_for_entry_iframe

def extract_list_items(driver):
    """리스트 아이템들을 찾아 반환"""
    if not detect_list_panel(driver):
        return []
    
    selectors = [
        "#_pcmap_list_scroll_container ul > li",
        "div.search_list_wrap ul > li",
        "div[data-view-type='list'] ul > li"
    ]
    for sel in selectors:
        items = driver.find_elements(By.CSS_SELECTOR, sel)
        if items: return items
    return []

def extract_name_element(item):
    """클릭할 요소와 가게 이름 추출"""
    # 1. 주요 텍스트 선택자
    name_selectors = [
        "span.TYaxT", "span.PlaceListTitle_text__Q5pE3", 
        "strong.place_bluelink", "span.YwYLL"
    ]
    for sel in name_selectors:
        try:
            el = item.find_element(By.CSS_SELECTOR, sel)
            name = el.text.strip()
            if name: return el, name
        except:
            continue
            
    # 2. 링크의 title 속성 등 시도
    try:
        el = item.find_element(By.CSS_SELECTOR, "a")
        # title 속성 확인
        name = el.get_attribute("title")
        if name: return el, name.strip()
        # 텍스트 확인
        text = el.text.strip().split("\n")[0]
        if text: return el, text
    except:
        pass

    return None, ""

def parse_detail_page(driver):
    """상세 정보(카테고리, 주소) 추출"""
    if not wait_for_entry_iframe(driver, timeout=8):
        return None, None

    try:
        cat = driver.find_element(By.CSS_SELECTOR, "span.lnJFt").text.strip()
    except:
        cat = "기타" # 카테고리가 없어도 저장은 되게 함

    try:
        addr = driver.find_element(By.CSS_SELECTOR, ".LDgIH").text.strip()
    except:
        addr = ""

    return cat, addr