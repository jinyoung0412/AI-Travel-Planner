# Historical 6,916-case QA matrix

`cases.json.gz` contains the agreed 266 base configurations × 26 scenarios. It preserves public origins, counts and tags, with no API credentials or signed tokens. This is the six-activity historical matrix; the subsequently added manual beer visit is covered by `test_manual_beer_course.py` and the Flutter input flow test. Generic tag choices remain unchanged.

`failures.json` contains only the 60 historical error classifications and their inputs. It omits provider responses and signed interpretation tokens. These cases support representative fault injection, not exact replay of the old model outputs.

Run without API access:

```sh
python scripts/offline_qa_matrix.py --output local_artifacts/offline-matrix
python scripts/offline_failure_replay.py
python scripts/benchmark_concurrency.py --label current --profile
```

Matrix interpretation responses are fixtures. Its DB sample is bounded; the concurrency benchmark uses the full database. Neither measures live AI semantic accuracy.
