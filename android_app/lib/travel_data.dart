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

class PlaceData {
  final Map<String, dynamic> _json;
  PlaceData.fromJson(Object? value) : _json = jsonObject(value);

  String get name => _text('name');
  String get address => _text('address');
  String get category => _text('category');
  String get kakaoUrl => _text('kakao_url');
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
    ..._json,
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

String distanceNotice(Object? metric) {
  final distance = metric is Map
      ? finiteNumber(metric['estimated_distance_km'])
      : null;
  final prefix = distance != null && distance >= 0
      ? '출발점부터 약 ${distance.toStringAsFixed(1)}km (직선거리 추정)\n'
      : '';
  return '$prefix교통 경로시간과 영업시간은 방문 전 확인해주세요.';
}
