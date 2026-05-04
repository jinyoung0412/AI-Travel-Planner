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
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
  }) async {
    return _post('/recommend/spot', {
      'user_text': userText,
      'transport': transport,
      'user_lat': userLat,
      'user_lng': userLng,
      'persona_tags': personaTags,
      'count': count,
    });
  }

  static Future<Map<String, dynamic>?> getCourseRecommendation({
    required String transport,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
  }) async {
    return _post('/recommend/course', {
      'transport': transport,
      'user_lat': userLat,
      'user_lng': userLng,
      'persona_tags': personaTags,
      'count': count,
    });
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
