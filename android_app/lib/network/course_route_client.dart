import 'dart:convert';

import '../course_map_data.dart';
import 'api_client.dart';
import 'request_cancellation.dart';

typedef CourseRouteLoader =
    Future<CourseRouteData> Function({
      required String mode,
      required List<CourseMapStop> stops,
      required RequestCancellation cancellation,
    });

/// Lives with the result screen, so revisiting a course reuses its geometry.
class CourseRouteClient {
  final ApiClient _api;
  final Map<String, CourseRouteData> _cache = {};
  bool _closed = false;
  CourseRouteClient({ApiClient? api})
    : _api = api ?? ApiClient(timeout: const Duration(seconds: 18));

  Future<CourseRouteData> load({
    required String mode,
    required List<CourseMapStop> stops,
    required RequestCancellation cancellation,
  }) async {
    if (_closed || cancellation.isCancelled) {
      return CourseRouteData.unavailable(mode);
    }
    if (!{'car', 'walk', 'transit'}.contains(mode) ||
        stops.length < 2 ||
        stops.length > 5 ||
        stops.map((stop) => stop.index).toSet().length != stops.length ||
        stops.any(
          (stop) =>
              stop.index < 0 ||
              stop.index > 4 ||
              !isKoreanMapCoordinate(stop.lat, stop.lng),
        )) {
      return CourseRouteData.unavailable(mode, 'invalid_upstream_response');
    }
    final key = jsonEncode([mode, stops.map((stop) => stop.toJson()).toList()]);
    if (_cache[key] case final cached?) return cached;
    final response = await _api.post('/routes/course', {
      'mode': mode,
      'stops': stops
          .map(
            (stop) => {
              'index': stop.index,
              'name': stop.name,
              'lat': stop.lat,
              'lng': stop.lng,
            },
          )
          .toList(),
    }, cancellation: cancellation);
    if (_closed || cancellation.isCancelled) {
      return CourseRouteData.unavailable(mode);
    }
    final route = response.containsKey('error')
        ? CourseRouteData.unavailable(
            mode,
            response['reason'] == 'network_timeout'
                ? 'timeout'
                : CourseRouteData.reasons.contains(response['reason'])
                ? response['reason'] as String
                : 'upstream_unavailable',
          )
        : CourseRouteData.parse(response, mode: mode, stops: stops);
    if (route.status == 'ready' || !route.canRetry) _cache[key] = route;
    return route;
  }

  void close() {
    _closed = true;
    _cache.clear();
    _api.close();
  }
}
