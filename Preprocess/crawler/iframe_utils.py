"""Naver list iframe helpers. Context changes are explicit at each entry point."""


def wait_for_list_panel(driver, timeout=10):
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        driver.switch_to.default_content()
        WebDriverWait(driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it(('id', 'searchIframe')))
        return True
    except WebDriverException:
        return False


def open_list_panel_force(driver):
    """Compatibility entry point: wait for the search-created panel, no placeholder click."""
    return wait_for_list_panel(driver, timeout=5)


def lock_to_list_panel(driver):
    from selenium.common.exceptions import WebDriverException
    try:
        return driver.find_element('id', '_pcmap_list_scroll_container')
    except WebDriverException:
        return None
