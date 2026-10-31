"""DB identity, region, radius, category and count checks; no server startup."""
def inspect_places(app,catalog,data,body,mode):
    issues=[]; paths=data.get('courses',[]) if mode=='course' else [[x] for x in data.get('places',[])]
    expected=data.get('metadata',{}).get('requested_count',body['count'])
    if len(paths)>expected:issues.append('too_many_results')
    plan=data.get('metadata',{}).get('travel_request',{})
    for path in paths:
        ids=[x.get('place_id') for x in path]
        if len(ids)!=len(set(ids)):issues.append('duplicate_place_in_course')
        if mode=='course' and not body.get('intent_version') and len(path)!=body['spot_count']:issues.append('visit_count_mismatch')
        for i,p in enumerate(path):
            row=catalog.get(p.get('place_id'))
            if row is None:issues.append('unknown_database_place');continue
            if app.candidate_city(row)!=body['region']:issues.append('wrong_region')
            distance=float(app.distances_from((body['user_lat'],body['user_lng']),[[row['latitude'],row['longitude']]])[0])
            if distance>app.RADIUS_KM[body['transport']]+0.001:issues.append('outside_radius')
            category=(plan.get('stages') or [])
            allowed=category[i].get('category_filters') if i<len(category) else app.SLOT_CATEGORY_MAP[body['slot_types'][i]] if mode=='course' and i<len(body['slot_types']) else []
            if allowed and not app.category_matches(row.get('카테고리',''),allowed):issues.append('category_mismatch')
    return sorted(set(issues)),sum(len(x) for x in paths),len(paths)
