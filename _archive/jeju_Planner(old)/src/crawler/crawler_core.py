# src/crawler/crawler_core.py

import time
import random
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import WebDriverException

# [Import] 절대 경로 사용
from src.crawler.driver import create_driver
from src.crawler.iframe_utils import (
    wait_for_list_panel,
    open_list_panel_force,
    lock_to_list_panel
)
from src.crawler.pagination import go_next_page
from src.crawler.parser import extract_list_items, extract_name_element, parse_detail_page
from src.crawler.saver import (
    get_csv_path, load_existing_names, save_item, log_failed, touch_init_file
)
from src.crawler.throttler import (
    throttle_click_delay, throttle_scroll_delay,
    throttle_page_delay, throttle_task_delay
)
from src.crawler.categories import CATEGORIES
from src.crawler.region_list import REGIONS

# --- [쓰레기 데이터 필터] ---
BAD_KEYWORDS = [
    "화장실", "주차장", "흡연구역", "매표소", "관리사무소", "사무실",
    "START", "FINISH", "출발", "도착", "코스", "반환점",
    "급커브", "굴다리", "오르막", "내리막", "통과", 
    "입구", "출구", "교차로", "삼거리", "사거리",
    "1호기", "2호기", "ATM", "자판기", "공중전화", "엘리베이터",
    "무인민원", "제세동기"
]

def is_junk(name):
    for bad in BAD_KEYWORDS:
        if bad in name:
            return True
    return False
# ---------------------------

class JejuCrawler:
    def __init__(self):
        self.driver = None
        self.base_url = "https://map.naver.com/p?c=15.00,0,0,0,dh"

    def start_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.driver = create_driver()

    def open_naver_map(self):
        try:
            self.driver.get(self.base_url)
        except WebDriverException:
            time.sleep(2)
            self.driver.get(self.base_url)
        time.sleep(2)

    def search_keyword(self, keyword):
        for _ in range(3):
            try:
                self.driver.switch_to.default_content()
                box = self.driver.find_element(By.CSS_SELECTOR, "input.input_search")
                box.clear()
                time.sleep(0.2)
                box.send_keys(keyword)
                box.send_keys(Keys.ENTER)
                time.sleep(2)
                return True
            except:
                time.sleep(1)
        return False

    def check_no_result(self):
        """결과 없음 메시지 확인"""
        try:
            self.driver.switch_to.default_content()
            frames = self.driver.find_elements(By.ID, "searchIframe")
            if frames:
                self.driver.switch_to.frame(frames[0])
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if "조건에 맞는 업체가 없습니다" in body_text or "검색 결과가 없습니다" in body_text:
                    return True
        except:
            pass
        return False

    def prepare_list(self, keyword):
        """리스트 패널 확보 시도"""
        if not self.search_keyword(keyword):
            return "ERROR"

        # [타임아웃] 병렬 처리 시 로딩 지연 대비 15초
        if wait_for_list_panel(self.driver, timeout=15):
            return "OK"

        if self.check_no_result():
            return "NO_RESULT"

        open_list_panel_force(self.driver)
        
        if wait_for_list_panel(self.driver, timeout=15):
            return "OK"
        
        if self.check_no_result():
            return "NO_RESULT"

        return "ERROR"

    def scroll_list(self):
        scroll_area = lock_to_list_panel(self.driver)
        if not scroll_area:
            return False

        last_count = 0
        stable = 3
        
        for _ in range(30):
            items = extract_list_items(self.driver)
            current = len(items)

            if current == 0:
                return False

            if current == last_count:
                stable -= 1
                if stable == 0: break
            else:
                last_count = current
                stable = 3

            try:
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_area)
            except:
                break
            throttle_scroll_delay()
            
        print(f"   📜 스크롤 완료: {last_count}개")
        return True

    def process_page(self, region, category, keyword, csv_path, existing, page):
        items = extract_list_items(self.driver)
        if not items:
            return False

        processed_count = 0
        
        for idx in range(len(items)):
            try:
                self.driver.switch_to.default_content()
                wait_for_list_panel(self.driver)
                
                refreshed_items = extract_list_items(self.driver)
                if idx >= len(refreshed_items): break
                
                item = refreshed_items[idx]
                el, name = extract_name_element(item)

                if not name: continue
                if name in existing: continue
                if is_junk(name): continue

                self.driver.execute_script("arguments[0].click();", el)
                throttle_click_delay()

                cat, addr = parse_detail_page(self.driver)
                
                if cat:
                    save_item(csv_path, {
                        "page": page,
                        "rank": idx + 1,
                        "name": name,
                        "category": cat,
                        "address": addr,
                        "keyword": keyword
                    })
                    existing.add(name)
                    print(f"      💾 저장: {name}")
                    processed_count += 1
                
                wait_for_list_panel(self.driver)

            except Exception:
                continue
        
        return processed_count > 0

    def crawl_region_category(self, region, category):
        keyword = f"제주 {region} {category}"
        csv_path = get_csv_path(region, category)
        
        # [수정] 크롤링 시작 전 빈 파일이라도 생성 (방문 표시)
        touch_init_file(csv_path)
        
        existing = load_existing_names(csv_path)

        if len(existing) > 0:
            pass 

        print(f"\n🔎 [{keyword}] 시작 (기존 {len(existing)}개)")
        self.start_driver()
        self.open_naver_map()

        status = self.prepare_list(keyword)
        if status == "NO_RESULT":
            print("   ❄ 결과 없음 (Pass)")
            return
        elif status == "ERROR":
            print("   ❌ 로딩 실패")
            return

        page = 1
        while page <= 15:
            print(f"   📄 Page {page}")
            
            if not self.scroll_list():
                break
            
            self.process_page(region, category, keyword, csv_path, existing, page)

            if not go_next_page(self.driver):
                print("   🏁 마지막 페이지")
                break
            
            throttle_page_delay()
            page += 1

    def run(self):
        # (기존 run 메서드는 run_crawling.py에서 직접 제어하므로 사용되지 않으나 유지)
        all_tasks = [(r, c) for r in REGIONS for c in CATEGORIES]
        tasks_todo = []
        tasks_done_count = 0
        print(f"⏳ 전체 {len(all_tasks)}개 작업 파일 검사 중... (잠시만 기다려주세요)")
        for r, c in all_tasks:
            csv_path = get_csv_path(r, c)
            # 파일이 존재하기만 하면 완료된 것으로 간주 (0byte 파일 포함)
            if os.path.exists(csv_path):
                tasks_done_count += 1
            else:
                tasks_todo.append((r, c))
        random.shuffle(tasks_todo)
        total_all = len(all_tasks)
        total_todo = len(tasks_todo)
        print(f"\n==================================================")
        print(f"✅ JejuCrawler 시작 - 전체 {total_all}개 작업 중...")
        print(f"⏭️ {tasks_done_count}개 완료됨. 남은 작업: {total_todo}개")
        print(f"==================================================\n")
        for idx, (r, c) in enumerate(tasks_todo, start=1):
            print(f"\n[{idx}/{total_todo}] 실행 → {r} / {c}")
            try:
                self.crawl_region_category(r, c)
            except Exception as e:
                print(f"   🔥 에러: {e}")
                if self.driver:
                    self.driver.quit()
                    self.driver = None
            throttle_task_delay()
        print("\n🎉 전체 수집 완료!")