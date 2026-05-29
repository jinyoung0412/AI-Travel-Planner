import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def extract_list_items(driver):
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
            if not text: 
                continue
            
            if "내 업체 등록하기" in text: continue
            if "새로 오픈했어요" in text: continue
            if "광고" in text and "리뷰" not in text: continue
            
            # 클래스 이름에 의존하지 않고, a 태그의 존재 여부만으로 유효성 검증
            links = item.find_elements(By.TAG_NAME, "a")
            if not links: 
                continue

            valid_items.append(item)
        except: 
            continue

    return valid_items

def extract_name_element(item):
    click_target = None
    name = ""
    try:
        links = item.find_elements(By.TAG_NAME, "a")
        if links:
            click_target = links[0]
        else:
            click_target = item
        
        # 네이버의 과거 및 최신 클래스를 모두 순회하며 확인
        name_selectors = ["span.YwYLL", "span.TYaxT", "span.xBZDS", "span.O8qbU", "span.place_bluelink", "div.TaEbI > a"]
        for sel in name_selectors:
            try: 
                name_el = item.find_element(By.CSS_SELECTOR, sel)
                if name_el.text:
                    name = name_el.text.strip()
                    break
            except: 
                pass
        
        if not name and click_target:
            lines = click_target.text.split("\n")
            if lines: 
                name = lines[0].strip()

        return click_target, name
    except:
        return None, ""

def parse_detail_page(driver):
    """
    장소 상세 정보 페이지(entryIframe)에서 카테고리·주소·리뷰 수를 추출한다.
    네이버 지도는 CSS 클래스명이 수시로 갱신되므로,
    각 항목마다 복수의 클래스 후보를 순차 탐색해 누락을 최소화한다.
    """
    # ── 상세 정보 iframe(entryIframe) 진입 ─────────────────────────
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 2).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "entryIframe"))
        )
    except:
        return "", "", 0, 0, "시간없음"

    time.sleep(0.5)  # iframe 내부 요소 렌더링 안정화 대기

    # ── 카테고리 추출 (예: "한식", "카페") ────────────────────────
    cat = ""
    try:
        # 두 가지 클래스 후보를 동시에 탐색 → UI 개편으로 클래스가 바뀌어도 대응 가능
        cat_els = driver.find_elements(By.CSS_SELECTOR, "span.lnJFt, span.DJJvD")
        if cat_els:
            cat = cat_els[0].text.strip()
    except:
        pass

    # ── 주소 추출 ─────────────────────────────────────────────────
    addr = ""
    try:
        addr_els = driver.find_elements(By.CSS_SELECTOR, "span.LDgIH, div.vV_z_")
        if addr_els:
            addr = addr_els[0].text.strip()
    except:
        pass

    # ── 방문자 리뷰 수 / 블로그 리뷰 수 추출 ──────────────────────
    # 리뷰 수는 클래스 변동이 잦아 CSS 선택자 대신 페이지 본문 전체 텍스트에서
    # 정규표현식으로 "방문자 리뷰 1,234" 형태 패턴을 매칭하는 방식이 더 안정적
    v, b = 0, 0
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        v_match = re.search(r"방문자 리뷰\s*([\d,]+)", body)
        if v_match:
            v = int(v_match.group(1).replace(",", ""))
        b_match = re.search(r"블로그 리뷰\s*([\d,]+)", body)
        if b_match:
            b = int(b_match.group(1).replace(",", ""))
    except:
        pass

    op_time = "시간없음"
    # try:
    #     candidates = driver.find_elements(By.CSS_SELECTOR, "svg.DNzQ2, a[aria-expanded='false'], span._UCia")
    #     for el in candidates:
    #         try:
    #             target_btn = el
    #             if el.tag_name == 'svg':
    #                 target_btn = el.find_element(By.XPATH, "./..")
    #
    #             href = target_btn.get_attribute("href")
    #             if href and ("suggestion" in href or "smartplace" in href):
    #                 continue
    #             if "수정" in target_btn.text or "제안" in target_btn.text:
    #                 continue
    #
    #             driver.execute_script("arguments[0].click();", target_btn)
    #             time.sleep(0.1)
    #         except:
    #             pass
    #
    #     time.sleep(0.5)
    #
    #     day_elements = driver.find_elements(By.CSS_SELECTOR, "span.i8cJw")
    #     time_list = []
    #
    #     if day_elements:
    #         for day_el in day_elements:
    #             try:
    #                 row_text = day_el.find_element(By.XPATH, "./../..").text.strip()
    #                 time_list.append(row_text.replace("\n", " "))
    #             except:
    #                 pass
    #     else:
    #         backup_els = driver.find_elements(By.CSS_SELECTOR, "div.A_cdD, span.A_cdD")
    #         for el in backup_els:
    #             t = el.text.strip().replace("\n", " ")
    #             if "원" not in t and any(c.isdigit() for c in t) and ("매일" in t or "영업" in t):
    #                 time_list.append(t)
    #
    #     bad_keywords = ["방송", "투데이", "고향", "생생", "2TV", "회,", "출연", "접기", "방영", "맛집", "수요미식회"]
    #     clean_times = []
    #     for t in time_list:
    #         if not any(bad in t for bad in bad_keywords):
    #             clean_times.append(t)
    #
    #     if clean_times:
    #         seen = set()
    #         unique_times = []
    #         for t in clean_times:
    #             if t not in seen:
    #                 unique_times.append(t)
    #                 seen.add(t)
    #         op_time = " | ".join(unique_times)
    #     else:
    #         op_time = "시간없음"
    #
    # except Exception:
    #     op_time = "시간없음"

    return cat, addr, v, b, op_time