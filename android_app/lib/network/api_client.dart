import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'tag_suggestion_exception.dart';
import 'request_cancellation.dart';

const defaultApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8080',
);

/// HTTP transport shared by the static app facade and offline contract tests.
class ApiClient {
  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  ApiClient({
    String baseUrl = defaultApiBaseUrl,
    this.timeout = const Duration(seconds: 35),
    http.Client? client,
  }) : baseUrl = baseUrl.replaceFirst(RegExp(r'/+$'), ''),
       _client = client ?? http.Client() {
    final uri = Uri.parse(this.baseUrl);
    if (!['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        timeout <= Duration.zero) {
      throw ArgumentError('Invalid API client configuration');
    }
  }

  void close() => _client.close();

  Future<List<String>> suggestTags({
    required String userText,
    bool throwOnError = false,
  }) async {
    if (userText.trim().isEmpty) return [];
    final result = await post('/suggest/tags', {'user_text': userText});
    if (result.containsKey('error')) {
      // Legacy clients treat suggestions as optional. The interactive facade
      // opts in to failures so it can distinguish an outage from zero tags.
      if (!throwOnError) return [];
      throw TagSuggestionException(
        result['reason'] is String ? result['reason'] as String : 'unavailable',
      );
    }
    final data = result['data'] ?? result;
    final tags = data is Map ? data['tags'] : null;
    if (tags is! List || tags.any((tag) => tag is! String)) {
      if (!throwOnError) return [];
      throw const TagSuggestionException('invalid_response');
    }
    return tags.cast<String>().toSet().toList();
  }

  Future<Map<String, dynamic>> getSpotRecommendation({
    required String userText,
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
    Map<String, dynamic> intentFields = const {},
    RequestCancellation? cancellation,
  }) => post('/recommend/spot', {
    'user_text': userText,
    'transport': transport,
    'region': region,
    'user_lat': userLat,
    'user_lng': userLng,
    'persona_tags': personaTags,
    'count': count,
    ...intentFields,
  }, cancellation: cancellation);

  Future<Map<String, dynamic>> getCourseRecommendation({
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
    int spotCount = 5,
    List<String> slotTypes = const [],
    String userText = '',
    Map<String, dynamic> intentFields = const {},
    RequestCancellation? cancellation,
  }) => post('/recommend/course', {
    'transport': transport,
    'region': region,
    'user_lat': userLat,
    'user_lng': userLng,
    'persona_tags': personaTags,
    'count': count,
    'spot_count': spotCount,
    'slot_types': slotTypes,
    'user_text': userText,
    ...intentFields,
  }, cancellation: cancellation);

  Future<String?> getKakaoPlaceUrl({
    required String name,
    required double lat,
    required double lng,
    String address = '',
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/kakao/place').replace(
        queryParameters: {
          'name': name,
          'address': address,
          'lat': lat.toString(),
          'lng': lng.toString(),
        },
      );
      final response = await _send('GET', uri);
      if (response.statusCode != 200) return null;
      final data = _decode(response);
      final url = data['place_url'];
      // Only a Kakao identity URL may replace the coordinate fallback.
      if (url is String &&
          RegExp(r'^https?://place\.map\.kakao\.com/\d+$').hasMatch(url)) {
        return url.replaceFirst(RegExp(r'^http:'), 'https:');
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<http.Response> _send(
    String method,
    Uri uri, [
    Map<String, dynamic>? body,
    RequestCancellation? cancellation,
  ]) async {
    if (cancellation?.isCancelled == true) throw const FormatException();
    final abort = Completer<void>();
    cancellation?.signal.then((_) {
      if (!abort.isCompleted) abort.complete();
    });
    final request = http.AbortableRequest(
      method,
      uri,
      abortTrigger: abort.future,
    );
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    return _client
        .send(request)
        .then(http.Response.fromStream)
        .timeout(
          timeout,
          onTimeout: () {
            if (!abort.isCompleted) abort.complete();
            throw TimeoutException('API request timed out');
          },
        );
  }

  Map<String, dynamic> _decode(http.Response response) {
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    if (data is! Map<String, dynamic>) throw const FormatException();
    return data;
  }

  bool _validPlace(dynamic value) {
    if (value is! Map<String, dynamic> || value['name'] is! String) {
      return false;
    }
    final lat = value['lat'];
    final lng = value['lng'];
    return lat is num &&
        lat.isFinite &&
        lat.abs() <= 90 &&
        lng is num &&
        lng.isFinite &&
        lng.abs() <= 180 &&
        (value['address'] == null || value['address'] is String) &&
        (value['category'] == null || value['category'] is String);
  }

  bool _validActivityClarification(Map<String, dynamic> data) {
    final clarification = data['clarification'];
    if (clarification is! Map<String, dynamic> ||
        clarification['kind'] != 'activity' ||
        clarification['message'] is! String ||
        clarification['token'] is! String ||
        (clarification['token'] as String).isEmpty ||
        data['travel_request'] is! Map<String, dynamic>) {
      return false;
    }
    final options = clarification['options'];
    const allowed = {'음식', '카페', '자연·산책', '문화·역사', '체험', '실내 오락'};
    if (options is! List ||
        options.isEmpty ||
        options.length > allowed.length) {
      return false;
    }
    final values = <String>{};
    for (final option in options) {
      if (option is! Map<String, dynamic> ||
          !allowed.contains(option['value']) ||
          option['label'] is! String ||
          (option['label'] as String).isEmpty ||
          !values.add(option['value'] as String)) {
        return false;
      }
    }
    return true;
  }

  bool _validData(String path, dynamic data) {
    if (data is! Map<String, dynamic>) return false;
    if (data['metadata'] != null && data['metadata'] is! Map<String, dynamic>) {
      return false;
    }
    return switch (path) {
      '/travel/interpret' =>
        data['clarification_required'] == true
            ? _validActivityClarification(data)
            : data['travel_request'] is Map<String, dynamic> &&
                  data['intent_token'] is String &&
                  data['target_mode'] is String &&
                  data['target_count'] is int &&
                  data['mode_switch_required'] is bool,
      '/suggest/tags' =>
        data['tags'] is List &&
            (data['tags'] as List).every((tag) => tag is String),
      '/recommend/spot' =>
        data['places'] is List && (data['places'] as List).every(_validPlace),
      '/recommend/course' =>
        data['courses'] is List &&
            (data['courses'] as List).every(
              (course) => course is List && course.every(_validPlace),
            ) &&
            (data['course_metrics'] == null || data['course_metrics'] is List),
      _ => true,
    };
  }

  Map<String, dynamic> _error(String message, String reason, [int? status]) => {
    'error': message,
    'reason': reason,
    if (status != null) 'status_code': status,
  };

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    RequestCancellation? cancellation,
  }) async {
    if (cancellation?.isCancelled == true) {
      return _error('추천 요청을 취소했어요.', 'request_cancelled');
    }
    try {
      final response = await _send(
        'POST',
        Uri.parse('$baseUrl$path'),
        body,
        cancellation,
      );
      if (cancellation?.isCancelled == true) {
        return _error('추천 요청을 취소했어요.', 'request_cancelled');
      }
      final status = response.statusCode;
      final Map<String, dynamic> decoded;
      try {
        decoded = _decode(response);
      } on FormatException {
        return _error('서버 응답을 확인하지 못했습니다.', 'invalid_response', status);
      }
      if (status == 200 &&
          decoded['success'] != false &&
          !decoded.containsKey('error')) {
        final data = decoded['data'] ?? decoded;
        if (!_validData(path, data)) {
          return _error('서버 응답을 확인하지 못했습니다.', 'invalid_response', status);
        }
        // Preserve the gateway success envelope expected by existing screens.
        return decoded;
      }
      final nested = decoded['error'];
      final details = nested is Map<String, dynamic> ? nested : decoded;
      final message = details['error'];
      return {
        ...details,
        'error': message is String && message.isNotEmpty
            ? message
            : '서버 요청을 처리하지 못했습니다. ($status)',
        'status_code': status,
      };
    } on TimeoutException {
      return _error('서버 응답 시간이 초과되었습니다. 다시 시도해주세요.', 'network_timeout');
    } on FormatException {
      return _error('서버 응답을 확인하지 못했습니다.', 'invalid_response');
    } catch (_) {
      return _error('서버에 연결하지 못했습니다. 연결 상태를 확인해주세요.', 'network_unavailable');
    }
  }
}
