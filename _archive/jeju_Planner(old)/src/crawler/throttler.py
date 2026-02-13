# throttler.py — Balanced Mode (안전과 속도의 황금비율)

import random
import time

def sleep_random(a, b):
    # 지정된 시간 범위 내에서 랜덤하게 대기
    time.sleep(random.uniform(a, b))

def throttle_click_delay():
    # [타협] 너무 빠르지도(1.2), 너무 느리지도(3.5) 않게
    # 클릭 후 데이터 로딩 대기 (약 1.5초~2.5초)
    sleep_random(1.5, 2.5) 

def throttle_scroll_delay():
    # [타협] 스크롤은 1초 내외가 가장 자연스러움
    sleep_random(0.8, 1.2)

def throttle_page_delay():
    # 페이지 넘길 때는 조금 여유 있게
    sleep_random(2.0, 3.0)

def throttle_task_delay():
    # 지역 이동 시에는 숨 좀 고르기
    sleep_random(3.0, 5.0)