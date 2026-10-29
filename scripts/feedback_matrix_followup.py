"""Bounded final Korean/contract recheck after the first full pairwise run.

Preserves the 483-row evidence and proves its blank-text paths unchanged by an
AST diff before reusing it. No long Cartesian/pairwise repetition or providers.
"""
import argparse
import ast
import collections
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.feedback_matrix import (ARTIFACTS, FROZEN, PILOT, Findings, digest,
    extract_ui_options, korean_contract_cases, offline_runtime, source_manifest)

EXTRA_FILES = [
    'scripts/feedback_matrix_followup.py', 'tests/test_claude_recommendation_review.py',
    'tests/test_feedback_switch_contract.py', 'tests/test_feedback_recommendation.py',
    'android_app/test/spot_course_switch_contract_test.dart',
    'android_app/lib/network/api_client.dart',
]


def manifest():
    files=source_manifest()['files']
    files.update({name:digest(ROOT/name) for name in EXTRA_FILES})
    return dict(files=files,sha256=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest())


def symbol_map(source):
    result={}
    for node in ast.parse(source).body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            name=node.name
        elif isinstance(node,ast.Assign):
            name='assign:'+','.join(ast.unparse(t) for t in node.targets)
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            name='import:'+','.join(n.name for n in node.names)
        else:
            name='statement:'+ast.dump(node,include_attributes=False)
        result[name]=ast.dump(node,include_attributes=False)
    return result


def influence_review(first,latest,options,folder):
    original=first['source_after']['files']
    changed=[p for p,h in original.items() if latest['files'].get(p)!=h]
    backend=[p for p in changed if p.startswith('Flask_server/') or p in ('place_identity.py','place_quality.py','category_policy.py')]
    allowed={
      'Flask_server/category_policy.py':{'filters_for_activity'},
      'Flask_server/travel_intent.py':{'apply_controls','assign:DATA_VERSION',
          'import:category_matches,normalize_filters','import:category_matches,normalize_filters,filters_for_activity'},
      'Flask_server/intent_context.py':{'context_only','grounded_tags','assign:_CONTEXT_WORDS','assign:TAG_SIGNALS','import:unicodedata'},
    }
    details=[]
    for path in backend:
        old=ARTIFACTS/'claude-final-run/source'/path
        snapshot_matches=old.is_file() and digest(old)==original[path]
        changes=[]
        if snapshot_matches:
            a,b=symbol_map(old.read_text()),symbol_map((ROOT/path).read_text())
            changes=sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
            diff=''.join(difflib.unified_diff(old.read_text().splitlines(True),(ROOT/path).read_text().splitlines(True),
                fromfile='round1/'+path,tofile='followup/'+path))
            (folder/(Path(path).stem+'.diff')).write_text(diff)
        details.append(dict(path=path,snapshot_hash_matches_round1=snapshot_matches,
            changed_symbols=changes,allowed_symbols=sorted(allowed.get(path,set())),
            matches_allowed_scope=snapshot_matches and set(changes)<=allowed.get(path,set())))
    app_file='Flask_server/app.py'
    schema_file='Flask_server/api_request.py'
    stable=lambda p: original.get(p)==latest['files'].get(p)
    blank=all(r['request'].get('user_text')=='' and not r['request'].get('intent_version') for r in first['requests'])
    options_equal=options==first['options']
    proof=dict(changed_since_round1=changed,changed_backend_files=details,
        all_backend_changes_within_allowed_symbols=all(x['matches_allowed_scope'] for x in details),
        app_router_and_blank_selection_unchanged=stable(app_file),api_schema_unchanged=stable(schema_file),
        region_filter_unchanged=stable('Flask_server/service_area.py'),
        category_matching_function_unchanged=all('category_matches' not in d['changed_symbols'] for d in details),
        recorded_pairwise_requests_blank_legacy=blank,recorded_pairwise_request_count=len(first['requests']),
        picker_options_unchanged=options_equal,
        explanation='All483 recorded requests have empty user_text and no intent_version. '
          'Unchanged app.recommend_spot/course route them to the legacy selection branch. '
          'New filters_for_activity is referenced only by manual intent apply_controls; '
          'context/grounded-tag changes and DATA_VERSION affect interpretation/tokens, not these blank requests.')
    proof['retain_first_pairwise_evidence']=all((proof['all_backend_changes_within_allowed_symbols'],
      proof['app_router_and_blank_selection_unchanged'],proof['api_schema_unchanged'],proof['region_filter_unchanged'],
      proof['category_matching_function_unchanged'],blank,options_equal,len(first['requests'])==483))
    return proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ARTIFACTS/'matrix-followup')
    parser.add_argument('--dependency-path',type=Path,default=Path('/private/tmp/today-feedback-matrix-deps'))
    args=parser.parse_args()
    folder=args.output_dir.resolve();folder.mkdir(parents=True,exist_ok=True)
    first=json.loads((ARTIFACTS/'matrix-final-pass1.json').read_text())
    before=manifest();frozen_before={p:digest(ROOT/p) for p in FROZEN}
    findings=Findings()
    findings.check(frozen_before==FROZEN and json.loads(PILOT.read_text()).get('collection_authorized_now') is False,
                   'frozen_precondition')
    options=extract_ui_options()
    review=influence_review(first,before,options,folder)
    findings.check(review['retain_first_pairwise_evidence'],'pairwise_evidence_scope_reuse',review)
    app,pd=offline_runtime()
    # The inherited dependency path is deliberately re-added after the offline
    # boundary removed arbitrary process configuration. No credential settings cross.
    env=dict(os.environ)
    env['PYTHONPATH']=str(args.dependency_path)+os.pathsep+env.get('PYTHONPATH','')
    xml=folder/'regression.xml'
    command=[sys.executable,'-m','pytest','-q','tests/test_claude_recommendation_review.py',
        'tests/test_feedback_matrix.py','tests/test_feedback_switch_contract.py',f'--junitxml={xml}']
    start=time.perf_counter()
    run=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,timeout=120)
    (folder/'regression.log').write_text(run.stdout+run.stderr)
    findings.check(run.returncode==0,'related_regressions_exit',run.returncode)
    test_counts=collections.Counter()
    if xml.exists():
        for case in ET.parse(xml).iter('testcase'):
            status='failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
            test_counts[(case.attrib.get('classname',''),status)]+=1
    dedicated = test_counts.get(('tests.test_claude_recommendation_review', 'passed'), 0)
    findings.check(dedicated >= 55, 'dedicated_regressions_not_reduced',
                   dict((str(k),v) for k,v in test_counts.items()))
    findings.check(not any(status != 'passed' for _, status in test_counts),
                   'related_regressions_no_skips_or_failures')
    from recommender.visits import visit_groups
    frame=app.get_df('')
    korean=korean_contract_cases(app,options,findings,visit_groups(frame),frame)
    requests=1+len(korean['cases'])+sum(c.get('recommendation') is not None for c in korean['cases'])
    findings.check(requests==27,'existing_korean_request_count',requests)
    after=manifest();frozen_after={p:digest(ROOT/p) for p in FROZEN}
    drift=[p for p,h in before['files'].items() if after['files'].get(p)!=h]
    drift += [p for p in after['files'] if p not in before['files']]
    findings.check(not drift,'followup_source_stable',drift)
    findings.check(extract_ui_options()==options,'followup_options_stable')
    findings.check(frozen_after==frozen_before==FROZEN,'frozen_preserved')
    report=dict(status='FINDINGS' if findings.failures else 'PASS_WITH_SCOPE_LIMITS',
        phase='bounded_Korean_and_contract_followup',method='Offline Flask fixture27 requests and related Claude, matrix, and real Dart-to-Flask signature regressions; exact test counts below; no long pairwise repeat.',
        first_pairwise_artifact='matrix-final-pass1.json',influence_review=review,
        source_before=before,source_after=after,source_drift=drift,source_stable=not drift,
        frozen_before=frozen_before,frozen_after=frozen_after,db_preserved=frozen_before==frozen_after,
        test_cases=[dict(module=k[0],status=k[1],count=v) for k,v in sorted(test_counts.items())],
        existing_korean_http_requests=requests,korean_contract_cases=korean,
        new_regression_http_requests='Not instrumented separately; related regression counts are test cases, not HTTP counts.',
        live_provider_calls=0,check_counts=dict(findings.checks),check_total=sum(findings.checks.values()),
        failures=findings.failures,seconds=round(time.perf_counter()-start,2),
        limitations=['No live Korean LLM accuracy or actual phone/IME/GPS validation',
          'Retained pairwise483 rows are earlier evidence backed by scope diff, not replayed against changed files',
          'Full finite UI Cartesian space remains unexecuted'])
    (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','test_cases','existing_korean_http_requests','source_drift','db_preserved','check_total','failures','seconds')},ensure_ascii=False,indent=2))
    return 1 if findings.failures else 0


if __name__=='__main__':
    raise SystemExit(main())
