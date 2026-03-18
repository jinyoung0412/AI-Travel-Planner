import time
import os
import csv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from Preprocess.crawler.driver import create_driver
from Preprocess.crawler.iframe_utils import (
    wait_for_list_panel, open_list_panel_force
)
from Preprocess.crawler.pagination import go_next_page
from Preprocess.crawler.parser import extract_list_items, extract_name_element, parse_detail_page
from Preprocess.crawler.saver import (
    get_csv_path, save_item, touch_init_file, 
    mark_task_completed, is_task_completed
)
from Preprocess.crawler.throttler import throttle_page_delay

class ChungnamCrawler:
    def __init__(self):
        self.driver = None
        self.base_url = "https://map.naver.com/p?c=15.00,0,0,0,dh"
        self.exclude_keywords = [ #수집 제외대상
            "롯데리아", "맥도날드", "버거킹", "맘스터치", "KFC", "노브랜드버거",
            "메가커피", "메가MGC커피", "빽다방", "스타벅스", "이디야", "투썸플레이스",
            "컴포즈커피", "할리스"
            "파리바게뜨", "뚜레쥬르", "배스킨라빈스", "던킨",
            "교촌치킨", "BHC", "bhc", "BBQ", "bbq", "굽네치킨",
            "서브웨이", "써브웨이", "김밥천국", "이삭토스트",
            "CU", "GS25", "세븐일레븐", "미니스톱",
            "공인중개사", "부동산", "아파트", "빌라", "오피스텔",
            "학원", "어린이집", "유치원", "독서실", "교습소", "스터디카페",
            "요양원", "주간보호", "치과", "내과", "한의원", "동물병원",
            "세탁소", "크린토피아", "철물점", "인테리어", "카센터", "공업사", "고물상",
            "건설", "정비", "철강", "다이소", "미용실", "화학", "기업", "사무소", "(주)",
            "전자", "전기", "제조", "물류", "화물", "용달", "택배", "운송", "견인", 
            "장례", "납골당", "추모", "묘원",
            "국민은행", "신한은행", "우리은행", "하나은행", "농협", "새마을금고", "신협", "기업은행", 
            "ATM", "우체국", "행정복지센터", "주민센터", "경찰서", "지구대", "소방서", "보험", "세무", "법무", "노무",
            "설비", "자재", "철거", "폐기물", "간판", "인쇄", "방수", "배관", "샷시",
            "네일", "속눈썹", "헬스장", "피트니스", "필라테스", "요가", "안경",
            "정형외과", "산부인과", "조리원", "성형외과", "피부과", "비뇨기과", "이비인후과",
            "타이어", "세차", "썬팅", "광택", "블랙박스", 
            "롯데슈퍼", "GS더프레시", "홈플러스익스프레스",
            "이마트", "홈플러스", "롯데마트", "하나로마트", "주유소", "충전소", "LPG"
        ]

    def start_driver(self):
        self.stop_driver()
        self.driver = create_driver()

    def stop_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def open_naver_map(self):
        if self.driver:
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
            except:
                time.sleep(1)
        return False

    def prepare_list(self, keyword):
        if not self.search_keyword(keyword): 
            return "ERROR"
        if wait_for_list_panel(self.driver, timeout=5): 
            return "OK"
        open_list_panel_force(self.driver)
        if wait_for_list_panel(self.driver, timeout=5): 
            return "OK"
        return "ERROR"

    def scroll_list(self):
        self.driver.switch_to.default_content()
        frames = self.driver.find_elements(By.ID, "searchIframe")
        if not frames: 
            return False
        self.driver.switch_to.frame(frames[0])

        try:
            scroll_area = self.driver.find_element(By.ID, "_pcmap_list_scroll_container")
        except: 
            return False
        
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
        except: 
            pass
        return False

    def load_existing_names_for_region(self, region):
        existing = set()
        folder = r"C:\AI-Travel-Planner\Preprocess\data\chungnam_data"
        if not os.path.exists(folder):
            return existing
        clean_reg = region.replace(" ", "_")
        prefix = f"충남_{clean_reg}"
        for filename in os.listdir(folder):
            if filename.startswith(prefix) and filename.endswith(".csv"):
                filepath = os.path.join(folder, filename)
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if "가게명" in row:
                            existing.add(row["가게명"])
        return existing

    def process_page(self, region, category, keyword, csv_path, existing, page):
        self.driver.switch_to.default_content()
        wait_for_list_panel(self.driver)
        frames = self.driver.find_elements(By.ID, "searchIframe")
        if frames:
            self.driver.switch_to.frame(frames[0])
        time.sleep(2.0)
        initial_items = extract_list_items(self.driver)
        total_count = len(initial_items)
        if total_count == 0:
            return 0
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
                
                if not name or name in existing: 
                    continue
                
                item_text = item.text
                is_excluded = any(kw in item_text for kw in self.exclude_keywords)
                if is_excluded:
                    continue

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(1.0) 
                
                if self.check_and_close_popup():
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
                                if self.check_and_close_popup(): continue
                            else: continue
                    else: continue 
                    
                cat, addr, v_rev, b_rev, op_time = parse_detail_page(self.driver)
                save_item(csv_path, {
                    "page": page, "rank": idx + 1, "name": name,
                    "category": cat if cat else category, "address": addr,
                    "keyword": keyword, "visitor_review": v_rev,
                    "blog_review": b_rev, "operating_time": op_time
                })
                existing.add(name)
            except:
                continue
        return total_count

    def crawl_region_all_categories(self, region, categories, q=None):
        existing_names = self.load_existing_names_for_region(region)

        self.start_driver()
        self.open_naver_map()
        processed_cats = 0

        for category in categories:
            try:
                if is_task_completed(region, category):
                    continue

                if processed_cats > 0 and processed_cats % 10 == 0:
                    self.stop_driver()
                    self.start_driver()
                    self.open_naver_map()

                keyword = f"{region} {category}"
                csv_path = get_csv_path(region, category)
                touch_init_file(csv_path)

                if self.prepare_list(keyword) == "OK":
                    page = 1
                    while page <= 10:
                        if not self.scroll_list(): break
                        time.sleep(1.0)
                        if self.process_page(region, category, keyword, csv_path, existing_names, page) == 0:
                            break
                        self.driver.switch_to.default_content()
                        self.driver.switch_to.frame("searchIframe")
                        if not go_next_page(self.driver): break
                        throttle_page_delay()
                        page += 1
                
                mark_task_completed(region, category)
                processed_cats += 1

            except Exception:
                pass
            finally:
                if q: q.put(1)
        
        self.stop_driver()