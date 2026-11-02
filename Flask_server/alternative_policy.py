"""Candidate-specific OR witnesses and explicit unknown-condition grants."""
from category_policy import category_matches


def alternatives(stage):
    return stage.get('alternatives') or [dict(id=f'{stage["id"]}.a1',
        quote=stage.get('quote'), category_filters=stage['category_filters'], conditions=[], preferences=[])]


def effective(stage, alternative, field='conditions'):
    return stage[field] + alternative[field]


def all_conditions(plan):
    return {c['id']: c for stage in plan['stages'] for alt in alternatives(stage)
            for c in effective(stage, alt) if c['required']}


def grant_ids(plan, data, error):
    explicit = any(s.get('alternatives') for s in plan['stages'])
    ids = data.get('accepted_condition_ids', [])
    accepted = data.get('accept_unverified', False)
    if not explicit:
        if ids:
            raise error('intent_conflict', '동의한 조건 범위를 다시 확인해주세요.',
                failure_code='intent_consent_scope')
        return set(all_conditions(plan)) if accepted else set()
    if accepted and not ids and all_conditions(plan):
        raise error('intent_conflict', '선택지별 미확인 조건을 선택해 확인해주세요.',
            failure_code='intent_consent_scope_required')
    if ids and not accepted:
        raise error('intent_conflict', '동의한 조건 범위를 다시 확인해주세요.',
            failure_code='intent_consent_scope')
    if ids and data.get('consent_plan_id') != plan.get('plan_id'):
        raise error('intent_expired', '여행 요청을 다시 확인해주세요.', 400)
    if not set(ids).issubset(all_conditions(plan)):
        raise error('intent_conflict', '동의한 조건 범위를 다시 확인해주세요.',
            failure_code='intent_consent_scope')
    return set(ids)


def witness(row, stage, grants, *, allow_unknown=False):
    choices = []
    for alt in alternatives(stage):
        if not category_matches(row.get('카테고리', ''), alt['category_filters']):
            continue
        conditions = effective(stage, alt)
        # No verified operational data exists. False-valued requirements are
        # unknown too: a park/cafe category proves neither indoor nor not-indoor.
        hard = [c for c in conditions if c['required']]
        if not allow_unknown and any(c['id'] not in grants for c in hard):
            continue
        choices.append(dict(alternative_id=alt['id'], alternative_label=' / '.join(alt['category_filters']),
            alternative_quote=alt.get('quote'), conditions=conditions,
            preferences=effective(stage, alt, 'preferences'), consent_used=bool(hard),
            required_unknown=hard))
    if not choices:
        return None
    chosen = min(choices, key=lambda c: (len(c['required_unknown']), c['alternative_id']))
    chosen['eligible_alternative_ids'] = [c['alternative_id'] for c in choices]
    chosen['matched_alternative_ids'] = [a['id'] for a in alternatives(stage)
        if category_matches(row.get('카테고리', ''), a['category_filters'])]
    return chosen


def filter_stage(frame, stage, grants):
    records, potentials, withheld = [], [], []
    for row in frame.to_dict('records'):
        possible = witness(row, stage, grants, allow_unknown=True)
        if possible:
            potentials.append({**row, '_alternative_witness': possible})
        chosen = witness(row, stage, grants)
        if chosen:
            records.append({**row, '_alternative_witness': chosen})
    for alt in alternatives(stage):
        missing = [c for c in effective(stage, alt) if c['required'] and c['id'] not in grants]
        count = sum(category_matches(row.get('카테고리', ''), alt['category_filters'])
                    for row in frame.to_dict('records'))
        if missing and count:
            label = ' / '.join(alt['category_filters'])
            withheld.append(dict(stage_id=stage['id'], alternative_id=alt['id'], label=label,
                reason='required_condition_unknown', candidate_count=count,
                conditions=[dict(c, label=label + ': ' + condition_label(c) + ' 여부 미확인',
                                 status='unknown') for c in missing]))
    def build(rows):
        import pandas as pd
        return pd.DataFrame(rows) if rows else frame.iloc[:0].copy()
    return build(records), build(potentials), withheld


def condition_label(condition):
    labels = {'indoor': '실내', 'outdoor': '야외', 'outdoor_seating': '야외 좌석',
              'open_now': '현재 영업', 'accessible': '이동 약자 접근성'}
    return labels[condition['field']] + (' 아님' if condition['value'] is False else '')


def unknown_metadata(stage, chosen):
    return [dict(stage_id=stage['id'], alternative_id=chosen['alternative_id'],
        condition_id=c['id'], label=chosen['alternative_label'] + ': ' + condition_label(c) + ' 여부 미확인')
        for c in chosen['required_unknown']]
