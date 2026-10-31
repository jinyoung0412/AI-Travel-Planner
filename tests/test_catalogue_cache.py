import concurrent.futures
import sqlite3
import time
import pandas as pd
import app
from catalogue_cache import CatalogueCache,database_version

def test_concurrent_cold_load_is_shared_but_request_mutation_is_not():
    cache=CatalogueCache();calls=[]
    def load():
        calls.append(1);time.sleep(.02)
        return pd.DataFrame([dict(place_id='one',score=1)]),{'count':1}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(lambda _:cache.get('same',load),range(4)))
    assert len(calls)==1
    values[0][0].loc[0,'score']=999;values[0][1]['count']=999
    for frame,meta in values[1:]:assert frame.loc[0,'score']==1 and meta['count']==1
    assert cache.get('same',load)[0].loc[0,'score']==1

def test_snapshot_invalidates_for_db_replacement_and_wal_write(tmp_path):
    path=tmp_path/'places.db';conn=sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE places (id TEXT)');conn.commit()
    first=database_version(path)
    conn.execute("INSERT INTO places VALUES ('new')");conn.commit()
    assert database_version(path)!=first
    conn.close()
    first=database_version(path);replacement=tmp_path/'other.db';replacement.write_bytes(path.read_bytes());replacement.replace(path)
    assert database_version(path)!=first

def test_cache_is_bounded_and_failed_loads_are_not_remembered():
    cache=CatalogueCache(limit=2)
    for i in range(5):cache.get(i,lambda:i)
    assert len(cache.entries)==2
    try:cache.get('failed',lambda:1/0)
    except ZeroDivisionError:pass
    assert cache.get('failed',lambda:'recovered')=='recovered'

def test_request_parameters_never_reuse_mutated_candidates(monkeypatch,places):
    from place_identity import ensure_ids
    source=ensure_ids(places)
    monkeypatch.setattr(app,'get_df',lambda _:source.copy())
    first,*_=app._base_candidates('천안');first.loc[:,'가게명']='changed'
    second,*_=app._base_candidates('천안')
    assert 'changed' not in second['가게명'].tolist()
