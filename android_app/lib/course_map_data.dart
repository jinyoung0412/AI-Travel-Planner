import 'travel_data.dart';

class KakaoMapConfiguration {
  final String javascriptKey;
  final String origin;

  const KakaoMapConfiguration({
    this.javascriptKey = const String.fromEnvironment(
      'KAKAO_MAP_JAVASCRIPT_KEY',
    ),
    this.origin = const String.fromEnvironment(
      'KAKAO_MAP_ORIGIN',
      defaultValue: 'https://localhost',
    ),
  });

  bool get isConfigured {
    final uri = Uri.tryParse(origin);
    return javascriptKey.trim().isNotEmpty &&
        uri != null &&
        uri.scheme == 'https' &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        (uri.path.isEmpty || uri.path == '/') &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }
}

class CourseMapStop {
  final int index;
  final String name;
  final double lat;
  final double lng;

  const CourseMapStop({
    required this.index,
    required this.name,
    required this.lat,
    required this.lng,
  });

  Map<String, dynamic> toJson() => {
    'index': index,
    'sequence': index + 1,
    'name': name,
    'lat': lat,
    'lng': lng,
  };
}

List<CourseMapStop> courseMapStops(List<Map<String, dynamic>> places) => [
  for (var index = 0; index < places.length; index++)
    if (_mapStop(places[index], index) case final CourseMapStop stop) stop,
];

CourseMapStop? _mapStop(Map<String, dynamic> json, int index) {
  final place = PlaceData.fromJson(json);
  final lat = place.lat;
  final lng = place.lng;
  if (!place.coordinateMapAllowed ||
      lat == null ||
      lng == null ||
      !isKoreanMapCoordinate(lat, lng)) {
    return null;
  }
  return CourseMapStop(index: index, name: place.name, lat: lat, lng: lng);
}

bool isKoreanMapCoordinate(num lat, num lng) =>
    lat.isFinite &&
    lng.isFinite &&
    lat >= 33 &&
    lat <= 39.5 &&
    lng >= 124 &&
    lng <= 132;

String courseRouteMode(String transport) => switch (transport) {
  'car' || '차' || '자차' || '자동차' => 'car',
  'walk' || '도보' => 'walk',
  _ => 'transit',
};

class CourseRoutePath {
  final String mode;
  final List<List<double>> points;
  const CourseRoutePath._(this.mode, this.points);
  Map<String, dynamic> toJson() => {'mode': mode, 'points': points};
}

class CourseRouteSegment {
  final int fromIndex;
  final int toIndex;
  final String status;
  final String? reason;
  final List<CourseRoutePath> paths;
  const CourseRouteSegment._(
    this.fromIndex,
    this.toIndex,
    this.status,
    this.reason,
    this.paths,
  );
  Map<String, dynamic> toJson() => {
    'fromIndex': fromIndex,
    'toIndex': toIndex,
    'status': status,
    if (reason != null) 'reason': reason,
    'paths': paths.map((path) => path.toJson()).toList(),
  };
}

/// Only bounded, finite provider geometry for original adjacent visits crosses
/// into the map document. A missing visit can never become a shortcut.
class CourseRouteData {
  static const maxPoints = 50000;
  static const reasons = {
    'not_configured',
    'permission_denied',
    'quota_exceeded',
    'no_route',
    'timeout',
    'upstream_unavailable',
    'invalid_upstream_response',
  };
  final String mode;
  final String status;
  final List<CourseRouteSegment> segments;
  final String? failureReason;
  const CourseRouteData._(
    this.mode,
    this.status,
    this.segments,
    this.failureReason,
  );

  factory CourseRouteData.unavailable(
    String mode, [
    String reason = 'upstream_unavailable',
  ]) => CourseRouteData._(mode, 'unavailable', const [], reason);

  bool get hasPaths => segments.any((segment) => segment.paths.isNotEmpty);
  bool get canRetry =>
      !{
        'permission_denied',
        'not_configured',
        'quota_exceeded',
      }.contains(failureReason) &&
      !segments.any(
        (segment) => {
          'permission_denied',
          'not_configured',
          'quota_exceeded',
        }.contains(segment.reason),
      );

  factory CourseRouteData.parse(
    Object? response, {
    required String mode,
    required List<CourseMapStop> stops,
  }) {
    CourseRouteData invalid() =>
        CourseRouteData.unavailable(mode, 'invalid_upstream_response');
    if (response is! Map || response['success'] != true) return invalid();
    final data = response['data'];
    if (data is! Map ||
        data['mode'] != mode ||
        !{'ready', 'partial', 'unavailable'}.contains(data['status'])) {
      return invalid();
    }
    final raw = data['segments'];
    if (raw is! List || raw.length > 4 || stops.length > 5) return invalid();
    final indices = stops.map((stop) => stop.index).toSet();
    final seen = <int>{};
    final segments = <CourseRouteSegment>[];
    var count = 0;
    for (final segment in raw) {
      if (segment is! Map) return invalid();
      final from = segment['fromIndex'], to = segment['toIndex'];
      final status = segment['status'], reason = segment['reason'];
      final paths = segment['paths'];
      if (from is! int ||
          to is! int ||
          to != from + 1 ||
          !indices.contains(from) ||
          !indices.contains(to) ||
          !seen.add(from) ||
          !{'ready', 'unavailable'}.contains(status) ||
          (reason != null && !reasons.contains(reason)) ||
          paths is! List ||
          paths.length > 100 ||
          (status == 'unavailable' && paths.isNotEmpty) ||
          (status == 'ready' && paths.isEmpty)) {
        return invalid();
      }
      final parsed = <CourseRoutePath>[];
      for (final path in paths) {
        if (path is! Map ||
            !{'car', 'walk', 'transit'}.contains(path['mode']) ||
            (mode == 'car' && path['mode'] != 'car') ||
            (mode == 'walk' && path['mode'] != 'walk') ||
            (mode == 'transit' && path['mode'] == 'car')) {
          return invalid();
        }
        final points = path['points'];
        if (points is! List || points.length < 2) return invalid();
        count += points.length;
        if (count > maxPoints) return invalid();
        final coordinates = <List<double>>[];
        for (final point in points) {
          if (point is! List ||
              point.length != 2 ||
              point[0] is! num ||
              point[1] is! num ||
              !isKoreanMapCoordinate(point[1] as num, point[0] as num)) {
            return invalid();
          }
          coordinates.add(
            List.unmodifiable([
              (point[0] as num).toDouble(),
              (point[1] as num).toDouble(),
            ]),
          );
        }
        parsed.add(
          CourseRoutePath._(
            path['mode'] as String,
            List.unmodifiable(coordinates),
          ),
        );
      }
      segments.add(
        CourseRouteSegment._(
          from,
          to,
          status as String,
          reason as String?,
          List.unmodifiable(parsed),
        ),
      );
    }
    final expected = stops
        .where((stop) => indices.contains(stop.index + 1))
        .length;
    if (segments.length != expected) return invalid();
    final readyCount = segments
        .where((segment) => segment.status == 'ready')
        .length;
    final expectedStatus = readyCount == 0
        ? 'unavailable'
        : readyCount == expected
        ? 'ready'
        : 'partial';
    if (data['status'] != expectedStatus) return invalid();
    return CourseRouteData._(
      mode,
      expectedStatus,
      List.unmodifiable(segments),
      null,
    );
  }

  Map<String, dynamic> toJson() => {
    'mode': mode,
    'status': status,
    'segments': segments.map((segment) => segment.toJson()).toList(),
  };
}

bool courseMapHasLeg(List<CourseMapStop> stops, int fromIndex) =>
    stops.any((stop) => stop.index == fromIndex) &&
    stops.any((stop) => stop.index == fromIndex + 1);
