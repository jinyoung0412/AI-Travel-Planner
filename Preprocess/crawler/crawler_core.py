# Preprocess/crawler/crawler_core.py

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from Preprocess.crawler.driver import create_driver
from Preprocess.crawler.iframe_utils import (
    wait_for_list_panel, open_list_panel_force, lock_to_list_panel
)
from Preprocess.crawler.pagination import go_next_page
from Preprocess.crawler.parser import extract_list_items, extract_name_element, parse_detail_page
from Preprocess.crawler.saver import get_csv_path, load_existing_names, save_item, touch_init_file
from Preprocess.crawler.throttler import throttle_click_delay, throttle_page_delay

class ChungnamCrawler:
    def __init__(self):
        self.driver = None
        self.base_url = "https://map.naver.com/p?c=15.00,0,0,0,dh"

    def start_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
        self.driver = create_driver()

    def open_naver_map(self):
        self.driver.get(self.base_url)
        time.sleep(2)

    def search_keyword(self, keyword):
        for _ in range(3):
            try:
                self.driver.switch_to.default_content()
                box = self.driver.find_element(By.CSS_SELECTOR, "input.input_search")
                box.clear()
                time.sleep(0.5)
                box.send_keys(keyword)
                box.send_keys(Keys.ENTER)
                time.sleep(2)
                return True
            except: time.sleep(1)
        return False

    def prepare_list(self, keyword):
        if not self.search_keyword(keyword): return "ERROR"
        if wait_for_list_panel(self.driver, timeout=5): return "OK"
        open_list_panel_force(self.driver)
        if wait_for_list_panel(self.driver, timeout=5): return "OK"
        return "ERROR"

    def scroll_list(self):
        self.driver.switch_to.default_content()
        frames = self.driver.find_elements(By.ID, "searchIframe")
        if not frames: return False
        self.driver.switch_to.frame(frames[0])

        try:
            scroll_area = self.driver.find_element(By.ID, "_pcmap_list_scroll_container")
        except: return False
        
        for _ in range(5): 
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_area)
            time.sleep(0.5)
        return True

    def check_and_close_popup(self):
        try:
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return True
        except: pass
        return False

    def process_page(self, region, category, keyword, csv_path, existing, page):
        self.driver.switch_to.default_content()
        wait_for_list_panel(self.driver)
        initial_items = extract_list_items(self.driver)
        total_count = len(initial_items)
        
        print(f"목록 발견: {total_count}개 -> 수집 시작")
        processed = 0
        
        for idx in range(total_count):
            try:
                self.driver.switch_to.default_content()
                frames = self.driver.find_elements(By.ID, "searchIframe")
                if not frames: break
                self.driver.switch_to.frame(frames[0])
                
                current_items = extract_list_items(self.driver)
                if idx >= len(current_items): break
                
                item = current_items[idx]
                el, name = extract_name_element(item)

                if not name: continue
                if name in existing: continue
                
                # [Clean Version] 빨간 박스 없이 클릭
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(1.0) 
                
                # 팝업 감지 및 재시도
                if self.check_and_close_popup():
                    # print(f"      ⚠️ 팝업 감지됨 -> '{name}' 재시도...")
                    
                    self.driver.switch_to.default_content()
                    frames = self.driver.find_elements(By.ID, "searchIframe")
                    if frames: 
                        self.driver.switch_to.frame(frames[0])
                        retry_items = extract_list_items(self.driver)
                        if idx < len(retry_items):
                            retry_item = retry_items[idx]
                            
                            text_el = None
                            try: text_el = retry_item.find_element(By.CSS_SELECTOR, "span.xBZDS")
                            except:
                                try: text_el = retry_item.find_element(By.CSS_SELECTOR, "span.TYaxT")
                                except: pass
                            
                            if text_el:
                                self.driver.execute_script("arguments[0].click();", text_el)
                                time.sleep(1.5)
                                if self.check_and_close_popup():
                                    # print(f"      재시도 실패: {name}")
                                    continue
                            else: continue
                    else: continue 

                cat, addr, v_rev, b_rev, op_time = parse_detail_page(self.driver)
                final_cat = cat if cat else category
                
                save_item(csv_path, {
                    "page": page,
                    "rank": idx + 1,
                    "name": name,
                    "category": final_cat,
                    "address": addr,
                    "keyword": keyword,
                    "visitor_review": v_rev,
                    "blog_review": b_rev,
                    "operating_time": op_time
                })
                existing.add(name)
                
                t_stat = 'O' if op_time != '시간없음' else 'X'
                print(f"저장: {name} (V:{v_rev}, B:{b_rev}, T:{t_stat})")
                processed += 1
                
            except Exception:
                continue
        
        return processed > 0

    def crawl_region_category(self, region, category):
        keyword = f"충남 {region} {category}"
        csv_path = get_csv_path(region, category)
        touch_init_file(csv_path)
        existing = load_existing_names(csv_path)

        print(f"\n🔎 [{keyword}] 시작 (기존 {len(existing)}개)")
        self.start_driver()
        self.open_naver_map()

        if self.prepare_list(keyword) == "ERROR":
            print("   ❌ 리스트 로딩 실패")
            return

        page = 1
        while page <= 10:
            print(f"   📄 Page {page} 처리 중...")
            if not self.scroll_list(): break
            
            self.process_page(region, category, keyword, csv_path, existing, page)
            
            self.driver.switch_to.default_content()
            self.driver.switch_to.frame("searchIframe")
            if not go_next_page(self.driver): 
                # print("   🏁 마지막 페이지")
                break
            
            throttle_page_delay()
            page += 1