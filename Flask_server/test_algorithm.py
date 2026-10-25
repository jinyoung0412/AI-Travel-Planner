"""Standalone synthetic diagnostic; comprehensive regressions live in tests/."""
import pandas as pd
from recommendation_ai import generate_from_slots, route_metrics


def run_recommendation_algorithm():
    df = pd.DataFrame([{'가게명': f'장소{i}', '주소': f'충남 천안시 테스트로 {i+1}',
                        '카테고리': ['한식', '공원', '카페'][i % 3],
                        'latitude': 36.8151 + i * .0001, 'longitude': 127.1139,
                        '방문자수': 0, '블로그수': 0, 'blog_tags': '{}', 'Cluster': i % 2}
                       for i in range(60)])
    origin = (36.8151, 127.1139)

    def synthetic_filter(frame, categories, tags):
        return frame[frame['카테고리'].isin(categories)]

    courses = generate_from_slots(df, ['음식', '자연·산책', '카페'], [], synthetic_filter,
                                  n=5, start=origin, seed=42)
    assert len(courses) == 5
    for c in courses:
        assert [p['카테고리'] for p in c] == ['한식', '공원', '카페']
        print([p['가게명'] for p in c], route_metrics(c, origin))
    print('오프라인 smoke 검사 통과: 군집 2개, 유효 코스 5개')


if __name__ == '__main__':
    run_recommendation_algorithm()
