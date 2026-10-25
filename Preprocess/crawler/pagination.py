"""Only an explicitly disabled next button proves pagination is complete."""
import time


def go_next_page(driver):
    driver.switch_to.default_content()
    frames = driver.find_elements('id', 'searchIframe')
    if not frames:
        raise RuntimeError('searchIframe unavailable during pagination')
    driver.switch_to.frame(frames[0])
    buttons = driver.find_elements('xpath', "//a[.//span[contains(text(), '다음')]]")
    if not buttons:
        raise RuntimeError('Next-page control unavailable; pagination state unknown')
    button = buttons[-1]
    disabled = button.get_attribute('aria-disabled')
    if disabled == 'true':
        return False
    if disabled != 'false':
        raise RuntimeError('Next-page control has unknown disabled state')
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    time.sleep(0.5)
    driver.execute_script('arguments[0].click();', button)
    time.sleep(3)
    return True
