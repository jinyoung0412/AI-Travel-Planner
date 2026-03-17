# Preprocess/crawler/parser.py

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time

def extract_list_items(driver):
    """리스트에서 광고/함정 카드를 제외하고 진짜 가게만 가져옵니다."""
    selectors = [
        "#_pcmap_list_scroll_container ul > li",
        "div.search_list_wrap ul > li"
    ]
    
    raw_items = []
    for sel in selectors:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        if found:
            raw_items = found
            break
            
    valid_items = []
    for item in raw_items:
        try:
            text = item.text
            # [함정 카드 제거]
            if "내 업체 등록하기" in text: continue
            if "새로 오픈했어요" in text: continue
            if "광고" in text and "리뷰" not in text: continue
            
            # [유효성 체크] 링크가 있어야 진짜 가게
            try: item.find_element(By.CSS_SELECTOR, "a.place_bluelink, div.TaEbI")
            except: continue

            valid_items.append(item)
        except: continue

    return valid_items

def extract_name_element(item):
    """이름과 클릭 타겟 추출"""
    click_target = None
    name = ""
    try:
        try: click_target = item.find_element(By.CSS_SELECTOR, "a.place_bluelink")
        except:
            try: click_target = item.find_element(By.CSS_SELECTOR, "div.TaEbI > a")
            except: click_target = item

        try: name = item.find_element(By.CSS_SELECTOR, "span.xBZDS").text.strip()
        except:
            try: name = item.find_element(By.CSS_SELECTOR, "span.TYaxT").text.strip()
            except: 
                if click_target: name = click_target.text.split("\n")[0]
        return click_target, name
    except:
        return None, ""

def parse_detail_page(driver):
    """상세 정보 수집 (스마트 플레이스 차단 + 영업시간 정제)"""
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 2).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "entryIframe"))
        )
    except:
        return "", "", 0, 0, "시간없음"

    time.sleep(0.5)

    # (1) 카테고리 & 주소
    try: cat = driver.find_element(By.CSS_SELECTOR, "span.lnJFt").text.strip()
    except: cat = ""
    try: addr = driver.find_element(By.CSS_SELECTOR, ".LDgIH").text.strip()
    except: addr = ""

    # (2) 리뷰 수
    v, b = 0, 0
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        v_match = re.search(r"방문자 리뷰\s*([\d,]+)", body)
        if v_match: v = int(v_match.group(1).replace(",", ""))
        b_match = re.search(r"블로그 리뷰\s*([\d,]+)", body)
        if b_match: b = int(b_match.group(1).replace(",", ""))
    except: pass

    # (3) 영업 시간
    op_time = ""
    try:
        # 버튼 클릭 (수정 제안 버튼 차단)
        candidates = driver.find_elements(By.CSS_SELECTOR, "svg.DNzQ2, a[aria-expanded='false'], span._UCia")
        for el in candidates:
            try:
                target_btn = el
                if el.tag_name == 'svg':
                    target_btn = el.find_element(By.XPATH, "./..")
                
                href = target_btn.get_attribute("href")
                if href and ("suggestion" in href or "smartplace" in href): continue
                if "수정" in target_btn.text or "제안" in target_btn.text: continue

                driver.execute_script("arguments[0].click();", target_btn)
                time.sleep(0.1)
            except: pass
        
        time.sleep(0.5)

        # 텍스트 수집 (요일 우선)
        day_elements = driver.find_elements(By.CSS_SELECTOR, "span.i8cJw")
        time_list = []
        
        if day_elements:
            for day_el in day_elements:
                try:
                    row_text = day_el.find_element(By.XPATH, "./../..").text.strip()
                    time_list.append(row_text.replace("\n", " "))
                except: pass
        else:
            backup_els = driver.find_elements(By.CSS_SELECTOR, "div.A_cdD, span.A_cdD")
            for el in backup_els:
                t = el.text.strip().replace("\n", " ")
                if "원" not in t and any(c.isdigit() for c in t) and ("매일" in t or "영업" in t):
                    time_list.append(t)

        # [불필요한 정보 필터링]
        bad_keywords = ["방송", "투데이", "고향", "생생", "2TV", "회,", "출연", "접기", "방영", "맛집", "수요미식회"]
        clean_times = []
        for t in time_list:
            if not any(bad in t for bad in bad_keywords):
                clean_times.append(t)

        if clean_times:
            seen = set()
            unique_times = []
            for t in clean_times:
                if t not in seen:
                    unique_times.append(t)
                    seen.add(t)
            op_time = " | ".join(unique_times)
        else:
            op_time = "시간없음"

    except Exception:
        op_time = "시간없음"

    return cat, addr, v, b, op_time