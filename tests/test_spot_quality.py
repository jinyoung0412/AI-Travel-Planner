"""Quality bounds use each spot's origin distance, never a route between spots."""
import pandas as pd
import pytest

from recommender import spot_quality as sq


def test_individual_origin_cost_and_transport_scale():
    row = dict(origin_distance_km=4.5, score=.7)
    assert sq.cost(row, '대중교통') == pytest.approx(1.3)
    assert sq.cost(row, '차') == pytest.approx(.6)


def test_random_ranking_stays_inside_near_equal_window_at_each_position():
    f = pd.DataFrame([dict(place_id=f'p{i}', origin_distance_km=i*.03, score=.5)
                      for i in range(20)])
    baseline = sq.rank(f, '대중교통')
    best = [sq.cost(r, '대중교통') for r in baseline.to_dict('records')]
    outcomes = set()
    for seed in range(20):
        ranked = sq.rank(f, '대중교통', seed, True)
        actual = [sq.cost(r, '대중교통') for r in ranked.to_dict('records')]
        assert all(cost <= bound + sq.RANDOM_WINDOW for cost, bound in zip(actual, best))
        assert sq.rank(f, '대중교통', seed, True)['place_id'].tolist() == ranked['place_id'].tolist()
        outcomes.add(tuple(ranked.head(3)['place_id']))
    assert len(outcomes) > 1
    assert sq.rank(f, '대중교통', 999, False)['place_id'].tolist() == baseline['place_id'].tolist()


def test_empty_rank_keeps_schema_and_no_exception():
    frame = pd.DataFrame(columns=['place_id','origin_distance_km','score'])
    assert sq.rank(frame,'대중교통',123,True).empty
