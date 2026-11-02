/// JSON boundaries preserve unknown fields (including identity and tags), but
/// reject malformed list members rather than silently losing a course stop.
Map<String, dynamic> jsonObject(Object? value) {
  if (value is! Map || value.keys.any((key) => key is! String)) {
    throw const FormatException('객체 형식이 올바르지 않습니다.');
  }
  return Map<String, dynamic>.from(value);
}

List<Map<String, dynamic>> jsonObjects(Object? value) {
  if (value is! List) throw const FormatException('목록 형식이 올바르지 않습니다.');
  return value.map(jsonObject).toList();
}

double? finiteNumber(Object? value) {
  final number = value is num ? value.toDouble() : double.tryParse('$value');
  return number != null && number.isFinite ? number : null;
}

enum TravelConsentPlanKind { plain, choice, unknown, invalid }

/// Classify structure, never infer a choice from the sentence or metadata version.
TravelConsentPlanKind classifyTravelConsentPlan(Object? value) {
  if (value is! Map) return TravelConsentPlanKind.unknown;
  final stages = value['stages'];
  if (!value.containsKey('schema_version')) {
    final hasChoiceMarker =
        stages is List &&
        stages.whereType<Map>().any((s) => s.containsKey('alternatives'));
    return hasChoiceMarker
        ? TravelConsentPlanKind.invalid
        : TravelConsentPlanKind.unknown;
  }
  if (value['schema_version'] != 1 ||
      stages is! List ||
      stages.isEmpty ||
      stages.length > 5) {
    return TravelConsentPlanKind.invalid;
  }
  bool categories(Object? items) =>
      items is List &&
      items.isNotEmpty &&
      items.every((item) => item is String && item.trim().isNotEmpty);
  bool atoms(Object? items, {required bool conditions}) =>
      items is List &&
      items.every(
        (atom) =>
            atom is Map &&
            atom['field'] is String &&
            (atom['field'] as String).isNotEmpty &&
            ((atom['quote'] is String &&
                    (atom['quote'] as String).trim().isNotEmpty) ||
                (atom['source'] == 'manual' &&
                    atom.containsKey('quote') &&
                    atom['quote'] == null)) &&
            atom['id'] is String &&
            (atom['id'] as String).isNotEmpty &&
            (!conditions ||
                (atom['required'] is bool && atom['value'] is bool)),
      );
  var choice = false;
  for (var i = 0; i < stages.length; i++) {
    final stage = stages[i];
    if (stage is! Map ||
        stage['id'] != 's${i + 1}' ||
        !categories(stage['category_filters']) ||
        !atoms(stage['conditions'], conditions: true) ||
        !atoms(stage['preferences'], conditions: false)) {
      return TravelConsentPlanKind.invalid;
    }
    if (stage.containsKey('alternatives')) {
      final alternatives = stage['alternatives'];
      if (alternatives is! List ||
          alternatives.isEmpty ||
          alternatives.length > 3 ||
          stage['choice_cardinality'] != 1) {
        return TravelConsentPlanKind.invalid;
      }
      for (var j = 0; j < alternatives.length; j++) {
        final alternative = alternatives[j];
        if (alternative is! Map ||
            alternative['id'] != 's${i + 1}.a${j + 1}' ||
            !categories(alternative['category_filters']) ||
            !atoms(alternative['conditions'], conditions: true) ||
            !atoms(alternative['preferences'], conditions: false)) {
          return TravelConsentPlanKind.invalid;
        }
      }
      choice = true;
    }
  }
  return choice ? TravelConsentPlanKind.choice : TravelConsentPlanKind.plain;
}

/// Keep the interpreted hierarchy independent of later mutable response maps.
Map<String, dynamic> immutableTravelObject(Map<String, dynamic> value) {
  Object? freeze(Object? item) {
    if (item is List) return List<Object?>.unmodifiable(item.map(freeze));
    if (item is Map) {
      return Map<String, dynamic>.unmodifiable({
        for (final entry in item.entries)
          entry.key as String: freeze(entry.value),
      });
    }
    return item;
  }

  return freeze(value) as Map<String, dynamic>;
}

/// Result history contains facts, never credentials for another request.
Map<String, dynamic> publicTravelObject(Map<String, dynamic> value) {
  const requestOnly = {
    'intent_token',
    'clarification_token',
    'consent_offer',
    'plan_id',
    'consent_plan_id',
    'accepted_condition_ids',
    'request_snapshot',
    'grant',
    'accept_unverified',
  };
  Object? clean(Object? item) {
    if (item is List) return item.map(clean).toList();
    if (item is Map) {
      return <String, dynamic>{
        for (final entry in item.entries)
          if (entry.key is String && !requestOnly.contains(entry.key))
            entry.key as String: clean(entry.value),
      };
    }
    return item;
  }

  return clean(value) as Map<String, dynamic>;
}

class PlaceData {
  final Map<String, dynamic> _json;
  PlaceData.fromJson(Object? value) : _json = jsonObject(value);

  String get name => _text('name');
  String get address => _text('address');
  String get category => _text('category');
  String get kakaoUrl => _text('kakao_url');
  Map? get _coordinateQuality => _json['coordinate_quality'] is Map
      ? _json['coordinate_quality'] as Map
      : null;

  // An absent quality object is a legacy record, never proof of accuracy.
  // Only consume the server's explicit restrictions; even eligible coordinates
  // still need the unverified-location notice before opening a pin.
  bool get coordinateMapAllowed =>
      _coordinateQuality?['status'] != 'blocked' &&
      _coordinateQuality?['map_coordinate_eligible'] != false;
  bool get coordinateDistanceAllowed =>
      _coordinateQuality?['status'] != 'blocked' &&
      _coordinateQuality?['distance_eligible'] != false;
  String _text(String key) => _json[key] is String ? _json[key] as String : '';
  double? get lat {
    final value = finiteNumber(_json['lat']);
    return value != null && value.abs() <= 90 ? value : null;
  }

  double? get lng {
    final value = finiteNumber(_json['lng']);
    return value != null && value.abs() <= 180 ? value : null;
  }

  Map<String, dynamic> toJson() => {
    ...publicTravelObject(_json),
    'name': name,
    'address': address,
    'category': category,
    'lat': lat,
    'lng': lng,
  };
}

class RecommendationData {
  final Map<String, dynamic> _json;
  RecommendationData.fromJson(Map<String, dynamic> response)
    : _json = jsonObject(response['data'] ?? response);

  List<Map<String, dynamic>> get places => jsonObjects(
    _json['places'],
  ).map((place) => PlaceData.fromJson(place).toJson()).toList();

  List<List<Map<String, dynamic>>> get courses {
    final value = _json['courses'];
    if (value is! List) throw const FormatException('코스 목록 형식이 올바르지 않습니다.');
    return value
        .map(
          (course) => jsonObjects(
            course,
          ).map((place) => PlaceData.fromJson(place).toJson()).toList(),
        )
        .toList();
  }

  Map<String, dynamic> get metadata => jsonObject(_json['metadata'] ?? {});
  List<Map<String, dynamic>> get courseMetrics =>
      jsonObjects(_json['course_metrics'] ?? []);
}

String distanceNotice(
  Object? metric, {
  Iterable<Map<String, dynamic>> places = const [],
}) {
  if (places.any(
    (place) => !PlaceData.fromJson(place).coordinateDistanceAllowed,
  )) {
    return '';
  }
  final distance = metric is Map
      ? finiteNumber(metric['estimated_distance_km'])
      : null;
  return distance != null && distance >= 0
      ? '직선거리 약 ${distance.toStringAsFixed(1)} km'
      : '';
}
