import time
import logging
import sys

from Preprocess.crawler.driver import create_driver
from Preprocess.crawler.iframe_utils import (
    wait_for_list_panel, lock_to_list_panel
)
from Preprocess.crawler.pagination import go_next_page
from Preprocess.crawler.parser import extract_list_items, extract_name_element, parse_detail_page, extract_provider_place_id
from Preprocess.crawler.saver import (
    get_csv_path, save_item, touch_init_file,
    mark_task_completed, is_task_completed, DATA_DIR, load_existing_ids
)
from place_identity import place_id
from Preprocess.crawler.throttler import throttle_click_delay, throttle_page_delay

logger = logging.getLogger(__name__)


class ChungnamCrawler:
    def __init__(self):
        self.driver = None
        self.base_url = "https://map.naver.com/p?c=15.00,0,0,0,dh"
        self.exclude_keywords = [
            "롯데리아", "맥도날드", "버거킹", "맘스터치", "KFC", "노브랜드버거",
            "메가커피", "메가MGC커피", "빽다방", "스타벅스", "이디야", "투썸플레이스",
            "컴포즈커피", "할리스",
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
            except Exception:
                logger.warning("Browser shutdown failed", exc_info=True)
            self.driver = None

    def open_naver_map(self):
        if self.driver:
            self.driver.get(self.base_url)
            time.sleep(2)

    def search_keyword(self, keyword):
        from selenium.webdriver.common.keys import Keys
        for _ in range(3):
            try:
                self.driver.switch_to.default_content()
                box = self.driver.find_element('css selector', "input.input_search")
                # clear()는 React 기반 네이버 지도에서 내부 상태를 초기화하지 못함
                # → OS에 맞는 선택 단축키로 전체 선택 후 새 키워드 입력으로 대체
                box.click()
                modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
                box.send_keys(modifier + 'a')
                box.send_keys(keyword)
                box.send_keys(Keys.ENTER)
                time.sleep(2)
                return True
            except Exception:
                time.sleep(1)
        return False

    def prepare_list(self, keyword):
        if not self.search_keyword(keyword): 
            return "ERROR"
        if wait_for_list_panel(self.driver, timeout=5): 
            return "OK"
        if wait_for_list_panel(self.driver, timeout=5): 
            return "OK"
        return "ERROR"

    def scroll_list(self):
        self.driver.switch_to.default_content()
        frames = self.driver.find_elements('id', "searchIframe")
        if not frames: 
            return False
        self.driver.switch_to.frame(frames[0])

        scroll_area = lock_to_list_panel(self.driver)
        if scroll_area is None:
            return False

        for _ in range(5): 
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_area)
            time.sleep(0.5)
        return True

    def check_and_close_popup(self):
        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return True
        return False

    def load_existing_ids_for_region(self, region):
        existing = set()
        if DATA_DIR.exists():
            prefix = f'충남_{region.replace(" ", "_")}'
            for path in DATA_DIR.glob(prefix + '_*.csv'):
                existing.update(load_existing_ids(path))
        return existing

    def process_page(self, region, category, keyword, csv_path, existing, page):
        self.driver.switch_to.default_content()
        if not wait_for_list_panel(self.driver):
            raise RuntimeError("searchIframe unavailable")
        frames = self.driver.find_elements('id', "searchIframe")
        if frames:
            self.driver.switch_to.frame(frames[0])
        time.sleep(2.0)
        
        initial_items = extract_list_items(self.driver)
        total_count = len(initial_items)
        if total_count == 0:
            raise RuntimeError("No parseable list items; empty result or unsupported DOM")

        need_refresh = True
        current_items = []
        new_count = 0
        failures = []

        for idx in range(total_count):
            try:
                if need_refresh:
                    self.driver.switch_to.default_content()
                    frames = self.driver.find_elements('id', "searchIframe")
                    if not frames:
                        raise RuntimeError("searchIframe disappeared")
                    self.driver.switch_to.frame(frames[0])
                    current_items = extract_list_items(self.driver)
                    need_refresh = False

                if idx >= len(current_items):
                    raise RuntimeError("Search list changed before all items were read")
                item = current_items[idx]
                el, name = extract_name_element(item)

                if not name:
                    raise RuntimeError("Place name unavailable")

                provider_candidates = {extract_provider_place_id(link.get_attribute('href'))
                                       for link in item.find_elements('tag name', 'a')} - {''}
                expected_provider_id = next(iter(provider_candidates)) if len(provider_candidates) == 1 else ''
                is_excluded = any(kw in name for kw in self.exclude_keywords)
                if is_excluded:
                    continue

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(1.0)

                need_refresh = True

                if self.check_and_close_popup():
                    self.driver.switch_to.default_content()
                    frames = self.driver.find_elements('id', "searchIframe")
                    if frames:
                        self.driver.switch_to.frame(frames[0])
                        retry_items = extract_list_items(self.driver)
                        if idx < len(retry_items):
                            retry_item = retry_items[idx]
                            text_el, _ = extract_name_element(retry_item)
                            if text_el:
                                self.driver.execute_script("arguments[0].click();", text_el)
                                time.sleep(1.5)
                                if self.check_and_close_popup():
                                    raise RuntimeError("Repeated popup blocked place detail")
                            else:
                                raise RuntimeError("Popup recovery has no place link")
                        else:
                            raise RuntimeError("Popup recovery lost list item")
                    else:
                        raise RuntimeError("Popup recovery lost searchIframe")

                cat, addr, v_rev, b_rev, op_time, provider_id = parse_detail_page(self.driver)
                if expected_provider_id and provider_id != expected_provider_id:
                    raise RuntimeError("Entry iframe identity does not match clicked list item")
                if not addr and not provider_id:
                    raise RuntimeError("Place identity unavailable")
                identity = place_id({'name': name, 'address': addr,
                                     'provider': 'naver' if provider_id else '',
                                     'provider_place_id': provider_id})
                if identity in existing:
                    continue
                save_item(csv_path, {
                    "page": page, "rank": idx + 1, "name": name,
                    "category": cat if cat else category, "address": addr,
                    "search_region": region, "search_category": category,
                    "category_source": "provider" if cat else "search_fallback",
                    "keyword": keyword, "visitor_review": v_rev,
                    "blog_review": b_rev, "operating_time": op_time,
                    "provider": "naver" if provider_id else "", "provider_place_id": provider_id
                })
                existing.add(identity)
                new_count += 1
                throttle_click_delay()

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures.append(type(exc).__name__)
                logger.warning("Place parse/save failed: %s / %s / page %s / item %s (%s)",
                               region, category, page, idx + 1, type(exc).__name__)
                need_refresh = True
            finally:
                try:
                    self.driver.switch_to.default_content()
                    frames = self.driver.find_elements('id', "searchIframe")
                    if frames:
                        self.driver.switch_to.frame(frames[0])
                except Exception as exc:
                    failures.append(type(exc).__name__)
                    logger.warning("Could not restore search iframe (%s)", type(exc).__name__)

        if failures:
            raise RuntimeError(f"Incomplete page: {len(failures)} failed items")
        return new_count

    def crawl_region_all_categories(self, region, categories, q=None):
        results = []
        try:
            for category in categories:
                result = {'region': region, 'category': category, 'status': 'failed'}
                try:
                    if is_task_completed(region, category):
                        result['status'] = 'skipped'
                        continue
                    # A fresh browser isolates broken sessions between categories.
                    self.start_driver()
                    self.open_naver_map()
                    keyword = f"{region} {category}"
                    csv_path = get_csv_path(region, category)
                    touch_init_file(csv_path)
                    # Deduplicate within a search, keeping category provenance in other CSVs.
                    existing = load_existing_ids(csv_path)
                    if self.prepare_list(keyword) != "OK":
                        raise RuntimeError("Search list unavailable")
                    for page in range(1, 11):
                        if not self.scroll_list():
                            raise RuntimeError("Search list could not be scrolled")
                        self.process_page(region, category, keyword, csv_path, existing, page)
                        if not go_next_page(self.driver):
                            mark_task_completed(region, category)
                            result['status'] = 'completed'
                            break
                        if page == 10:
                            raise RuntimeError("Page limit reached before final page")
                        throttle_page_delay()
                except KeyboardInterrupt:
                    result['status'] = 'interrupted'
                    raise
                except Exception as exc:
                    result['error_type'] = type(exc).__name__
                    logger.warning("Crawl task failed: %s / %s (%s)", region, category, type(exc).__name__)
                finally:
                    results.append(result)
                    if q is not None:
                        q.put(1)  # Compatibility: this means finished, never succeeded.
                    self.stop_driver()
        finally:
            self.stop_driver()
        return results
