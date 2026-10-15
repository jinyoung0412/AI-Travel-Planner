import pandas as pd
import pytest

from Preprocess.RunPreprocess import data_pipeline as pipeline


def write_source(directory, filename='충남_충남_천안시_북면_카페.csv', **values):
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{'가게명': '카페', '주소': '충남 천안시 테스트로 1',
                           '카테고리': '카페', 'provider': 'naver', 'provider_place_id': '00123', **values}])
    frame.to_csv(directory / filename, index=False, encoding='utf-8-sig')
    return frame


def test_flat_csv_metadata_and_id_preserve_source(tmp_path, monkeypatch):
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source, 방문자수='1,200', 블로그수='invalid')
    calls = []
    monkeypatch.setattr(pipeline, 'get_coords', lambda *a: calls.append(a) or (36.8, 127.1))
    frame = pipeline.run_pipeline(source, output, 'mock')
    assert frame.iloc[0]['search_region'] == '충남 천안시 북면'
    assert frame.iloc[0]['eup_myeon_dong'] == '충남 천안시 북면'
    assert frame.iloc[0]['search_category'] == '카페'
    assert frame.iloc[0]['place_id'] == 'naver:00123'
    assert frame.iloc[0]['평점'] == 1200
    pipeline.run_pipeline(source, output, 'mock')
    assert len(calls) == 1


def test_checkpoint_resume_and_failures_remain_retriable(tmp_path, monkeypatch):
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source)
    write_source(source, '충남_충남_아산시_음봉면_카페.csv', 가게명='다른카페', 주소='충남 아산시 다른로 2', provider_place_id='2')
    calls = []
    def geocode(address, _):
        calls.append(address)
        if len(calls) == 2: raise KeyboardInterrupt()
        return 36.8, 127.1
    monkeypatch.setattr(pipeline, 'get_coords', geocode)
    with pytest.raises(KeyboardInterrupt): pipeline.run_pipeline(source, output, 'mock')
    assert not (output / 'chungnam_places_filtered.csv').exists()
    monkeypatch.setattr(pipeline, 'get_coords', lambda address, _: calls.append(address) or (None, None))
    frame = pipeline.run_pipeline(source, output, 'mock')
    assert len(frame) == 1 and len(calls) == 3
    assert pd.read_csv(output / 'preprocess_rejected.csv').iloc[0]['preprocess_error'] == 'geocoding_failed'
    monkeypatch.setattr(pipeline, 'get_coords', lambda address, _: (36.9, 127.2))
    assert len(pipeline.run_pipeline(source, output, 'mock')) == 2


def test_provider_category_wins_over_later_search_fallback(tmp_path):
    write_source(tmp_path, '충남_충남_천안시_북면_카페.csv', category_source='provider', latitude=36.8, longitude=127.1)
    write_source(tmp_path, '충남_충남_천안시_북면_맛집.csv', 카테고리='맛집', category_source='search_fallback', latitude=36.8, longitude=127.1)
    result = pipeline.run_pipeline(tmp_path, tmp_path / 'output')
    assert len(result) == 1 and result.iloc[0]['카테고리'] == '카페'


def test_malformed_source_aborts_without_overwriting_output(tmp_path):
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source, latitude=36.8, longitude=127.1)
    pipeline.run_pipeline(source, output)
    previous = (output / 'chungnam_places_filtered.csv').read_bytes()
    (source / 'broken.csv').write_text('unknown\nvalue\n')
    with pytest.raises(ValueError, match='필수 컬럼'): pipeline.run_pipeline(source, output)
    assert (output / 'chungnam_places_filtered.csv').read_bytes() == previous


def test_geocode_failure_does_not_replace_dataset_with_empty_file(tmp_path, monkeypatch):
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source)
    monkeypatch.setattr(pipeline, 'get_coords', lambda *a: (None, None))
    with pytest.raises(ValueError, match='좌표'): pipeline.run_pipeline(source, output, 'mock')
    assert not (output / 'chungnam_places_filtered.csv').exists()
    assert len(pd.read_csv(output / 'preprocess_rejected.csv')) == 1


def test_all_search_provenance_survives_identity_deduplication(tmp_path):
    import json
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source, '충남_충남_천안시_북면_카페.csv', latitude=36.8, longitude=127.1, category_source='provider')
    write_source(source, '충남_충남_천안시_북면_맛집.csv', latitude=36.8, longitude=127.1, category_source='search_fallback')
    frame = pipeline.run_pipeline(source, output)
    origins = json.loads(frame.iloc[0]['collection_sources'])
    assert {r['search_category'] for r in origins} == {'카페', '맛집'}


def test_excluded_provider_category_cannot_be_reintroduced_by_search_fallback(tmp_path):
    source, output = tmp_path / 'source', tmp_path / 'output'
    write_source(source, '충남_충남_천안시_북면_카페.csv', 카테고리='스크린골프장', latitude=36.8, longitude=127.1, category_source='provider')
    write_source(source, '충남_충남_천안시_북면_맛집.csv', 카테고리='맛집', latitude=36.8, longitude=127.1, category_source='search_fallback')
    with pytest.raises(ValueError, match='좌표'):
        pipeline.run_pipeline(source, output)
    assert not (output / 'chungnam_places_filtered.csv').exists()


def test_cached_geocoding_can_finish_without_credentials(tmp_path, monkeypatch):
    import hashlib
    import json
    from place_identity import ensure_ids
    source, output = tmp_path / 'source', tmp_path / 'output'
    original = write_source(source)
    row = ensure_ids(original).iloc[0]
    journal = output / 'geocoding_checkpoint'
    journal.mkdir(parents=True)
    record = {key: row[key] for key in ('place_id', 'identity_key')}
    record.update(latitude=36.8, longitude=127.1)
    (journal / (hashlib.sha256(row['place_id'].encode()).hexdigest() + '.json')).write_text(json.dumps(record))
    monkeypatch.delenv('KAKAO_API_KEY', raising=False)
    monkeypatch.setattr(pipeline, 'load_dotenv', lambda *a: None)
    monkeypatch.setattr(pipeline, 'get_coords', lambda *a: pytest.fail('cached coordinate must avoid external request'))
    assert len(pipeline.run_pipeline(source, output)) == 1


def test_preprocessor_uses_same_raw_directory_override_as_crawler(tmp_path, monkeypatch):
    source, output = tmp_path / 'custom-raw', tmp_path / 'output'
    write_source(source, latitude=36.8, longitude=127.1)
    monkeypatch.setenv('TRAVEL_DATA_DIR', str(source))
    assert len(pipeline.run_pipeline(output_dir=output)) == 1
