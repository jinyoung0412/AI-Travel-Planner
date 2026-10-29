"""Tests of matrix coverage accounting; product tests remain with their owners."""
import itertools
from pathlib import Path
import shutil

import pytest

from scripts.feedback_matrix import (ROOT, covering_array, extract_ui_options, finite_space,
    pairwise_plan, payload_for, required_pairs, row_pairs, source_city, extract_api_count_limits)


@pytest.mark.parametrize('levels', [(1, 1), (2, 3, 4), (3, 5, 2, 4), (16, 4, 13, 14, 8, 3, 7)])
def test_pairwise_array_covers_every_pair_independently(levels):
    rows = covering_array(levels)
    # Independently enumerate concrete pairs rather than trust report counters.
    for a,b in itertools.combinations(range(len(levels)),2):
        observed = {(row[a],row[b]) for row in rows}
        assert observed == set(itertools.product(range(levels[a]),range(levels[b])))
    assert all(len(r)==len(levels) and all(0<=v<levels[i] for i,v in enumerate(r)) for r in rows)
    assert rows == covering_array(levels)


@pytest.mark.parametrize('address,expected',[
    ('충남 천안시 동남구 만남로 1','천안'),('충청남도 아산시 온천대로 1','아산'),
    ('천안시 동남구 1','천안'),('대한민국 충남 아산시 테스트로 2','아산'),
    ('경기 안성시 공도읍 1',None),('충남 천안시티 아파트',None),('',None),
])
def test_service_city_uses_source_address_not_unknown_db_region(address,expected):
    assert source_city({'주소':address,'지역':'기타'})==expected


def test_extracted_hubs_match_independent_checked_fixture():
    import json
    options=extract_ui_options()
    fixture=json.loads((ROOT/'android_app/test/fixtures/transit_hubs.json').read_text())
    actual={(o['region'],o['name'],o['lat'],o['lng']) for o in options['origins'] if o['kind']=='hub'}
    expected={(o['region'],o['name'],o['lat'],o['lng']) for o in fixture['hubs']}
    assert actual == expected
    assert len(actual)==len(fixture['hubs'])
    assert set(options['regions']) == {'내 주변','천안','아산'}
    assert set(options['transports']) == {'대중교통','차'}


def test_every_api_count_value_is_accepted_and_ui_counts_are_a_subset():
    from api_request import parse_recommendation
    options=extract_ui_options()
    limits=extract_api_count_limits()
    base=dict(user_lat=36.8151,user_lng=127.1139,region='천안',transport='대중교통')
    for mode,bounds in limits.items():
        domain=set(range(bounds['min'],bounds['max']+1))
        assert set(options[f'{mode}_counts']) <= domain
        for count in domain:
            assert parse_recommendation({**base,'count':count},course=mode=='course')['count']==count
        for count in (bounds['min']-1,bounds['max']+1):
            with pytest.raises(ValueError):
                parse_recommendation({**base,'count':count},course=mode=='course')


def test_finite_space_counts_optional_and_multiselect_axes_exactly():
    options=extract_ui_options()
    space=finite_space(options)
    groups=options['tag_groups']
    expected=1
    for name,tags in groups.items():
        expected *= 2**len(tags) if name=='어떤 분위기' else len(tags)+1
    assert space['spot_tag_states']==expected==17_891_328
    assert space['direct_course_activity_sequences']==216+1296+7776
    assert space['spot_direct_picker_states']==len(options['origins'])*4*expected
    # Course tag visibility is read from its actual getter, never the spot picker.
    denominator=1
    for name in options['course_hidden_tag_groups']:
        denominator *= len(groups[name])+1
    assert space['course_tag_states']==expected//denominator
    assert 'all GPS coordinates' in space['non_enumerated_axes']


def test_extraction_fails_closed_when_control_syntax_changes(tmp_path):
    for filename in ('input_screen.dart','input_options.dart','transit_hubs.dart'):
        dst=tmp_path/'android_app/lib'/filename
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'android_app/lib'/filename,dst)
    screen=tmp_path/'android_app/lib/input_screen.dart'
    screen.write_text(screen.read_text().replace('_countOptions =>','_newCountOptions =>'))
    with pytest.raises(ValueError,match='extraction failed'):
        extract_ui_options(tmp_path)


@pytest.mark.parametrize('mode',['spot','course'])
def test_pairwise_payloads_use_valid_origins_and_all_ui_choices(mode):
    from api_request import parse_recommendation
    options=extract_ui_options()
    plan=pairwise_plan(options,mode)
    levels=[len(v) for v in plan['factors'].values()]
    expected=required_pairs(levels)
    observed=set()
    for row in plan['rows']:
        values,body=payload_for(options,plan,row,mode)
        parse_recommendation(body,course=mode=='course')
        observed |= row_pairs(row)
        if body['region']!='내 주변' and body['transport']=='대중교통':
            assert any(o['id']==values['origin'] and o['kind']=='hub' for o in options['origins'])
        if mode=='course':
            assert len(body['slot_types'])==body['spot_count']
            assert all(s in options['activities'] for s in body['slot_types'])
            assert not set(body['persona_tags']) & set(options['tag_groups']['어떤 활동'])
    assert observed==expected
    assert plan['covered_pairs']==plan['required_pairs']==len(expected)
    # Partial execution must never be credited as the complete planned cover.
    assert len(set().union(*(row_pairs(row) for row in plan['rows'][:8])))<len(expected)
    prefix=plan['rows'][:48]
    for i,n in enumerate(levels):
        assert {row[i] for row in prefix}==set(range(n))
