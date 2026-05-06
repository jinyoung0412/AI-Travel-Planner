import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = 'http://10.0.2.2:8080';

  static Future<List<String>> suggestTags({required String userText}) async {
    final result = await _post('/suggest/tags', {'user_text': userText});
    if (result == null) return [];
    final tags = result['tags'] ?? result['data']?['tags'];
    if (tags is List) return List<String>.from(tags);
    return [];
  }

  static Future<Map<String, dynamic>?> getSpotRecommendation({
    required String userText,
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
  }) async {
    return _post('/recommend/spot', {
      'user_text': userText,
      'transport': transport,
      'region': region,
      'user_lat': userLat,
      'user_lng': userLng,
      'persona_tags': personaTags,
      'count': count,
    });
  }

  static Future<Map<String, dynamic>?> getCourseRecommendation({
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
    int spotCount = 5,
    List<String> slotTypes = const [],
  }) async {
    return _post('/recommend/course', {
      'transport': transport,
      'region': region,
      'user_lat': userLat,
      'user_lng': userLng,
      'persona_tags': personaTags,
      'count': count,
      'spot_count': spotCount,
      'slot_types': slotTypes,
    });
  }

  static Future<String?> getKakaoPlaceUrl({
    required String name,
    required double lat,
    required double lng,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/kakao/place').replace(
        queryParameters: {
          'name': name,
          'lat': lat.toString(),
          'lng': lng.toString(),
        },
      );
      final response = await http.get(uri);
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        return data['place_url'] as String?;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  static Future<Map<String, dynamic>?> _post(String path, Map<String, dynamic> body) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl$path'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      if (response.statusCode == 200) {
        return jsonDecode(utf8.decode(response.bodyBytes));
      }
      return {'error': '서버 오류 (${response.statusCode})'};
    } catch (e) {
      return {'error': '네트워크 오류: $e'};
    }
  }
}
