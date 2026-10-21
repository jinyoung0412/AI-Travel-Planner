"""Best-effort Naver selectors, validated offline with synthetic elements only."""
import re
import time
from urllib.parse import urlparse


def extract_list_items(driver):
    for selector in ('#_pcmap_list_scroll_container ul > li', 'div.search_list_wrap ul > li'):
        raw_items = driver.find_elements('css selector', selector)
        if raw_items:
            break
    else:
        return []
    return [item for item in raw_items if item.text and
            '내 업체 등록하기' not in item.text and
            not ('광고' in item.text and '리뷰' not in item.text) and
            item.find_elements('tag name', 'a')]


def extract_name_element(item):
    selectors = ('span.YwYLL', 'span.TYaxT', 'span.xBZDS', 'span.O8qbU',
                 'span.place_bluelink', 'div.TaEbI > a')
    for selector in selectors:
        for element in item.find_elements('css selector', selector):
            if element.text.strip():
                # Keep the selected source text for identity. Category suffixes
                # are removed only in derived display fields by the saver.
                return element, element.text.strip()
    links = item.find_elements('tag name', 'a')
    target = links[0] if links else item
    lines = target.text.splitlines()
    return target, lines[0].strip() if lines else ''


def extract_provider_place_id(url):
    parsed = urlparse(url or '')
    if parsed.scheme not in ('https', 'http') or parsed.hostname not in (
            'map.naver.com', 'place.naver.com', 'pcmap.place.naver.com', 'm.place.naver.com'):
        return ''
    match = re.search(r'/(?:place|restaurant|cafe|attraction)/(\d+)(?:/|$)', parsed.path)
    return match.group(1) if match else ''


def first_available_text(driver, *selectors):
    """Prefer the narrow field over a containing directions/category wrapper."""
    for selector in selectors:
        elements = driver.find_elements('css selector', selector)
        if elements and elements[0].text.strip():
            return elements[0].text.strip()
    return ''


def parse_detail_page(driver):
    """Return the existing six-field contract; unavailable iframe fails the task.

    CSS candidates are heuristics. Operating hours remain unknown until a tested
    parser exists; the removed commented parser never produced runtime values.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.switch_to.default_content()
    WebDriverWait(driver, 2).until(
        EC.frame_to_be_available_and_switch_to_it(('id', 'entryIframe')))
    driver.switch_to.default_content()
    frame = driver.find_element('id', 'entryIframe')
    # Top-level map URLs can still identify the previous search/place.
    provider_id = extract_provider_place_id(frame.get_attribute('src'))
    driver.switch_to.frame(frame)
    time.sleep(0.5)

    category = first_available_text(driver, 'span.lnJFt', 'span.DJJvD')
    address = first_available_text(driver, 'span.LDgIH', 'div.vV_z_')
    body = driver.find_element('tag name', 'body').text

    def review_count(label):
        match = re.search(label + r'\s*([\d,]+)', body)
        return int(match.group(1).replace(',', '')) if match else 0

    return (category, address, review_count('방문자 리뷰'), review_count('블로그 리뷰'),
            '시간없음', provider_id)
