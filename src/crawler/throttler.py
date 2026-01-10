# src/crawler/throttler.py
import time
import random

def throttle_click_delay():
    time.sleep(random.uniform(1.0, 1.5))

def throttle_scroll_delay():
    time.sleep(0.5)

def throttle_page_delay():
    time.sleep(2.0)