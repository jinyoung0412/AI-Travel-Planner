import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // ngrok 사용 시: static const String baseUrl = 'https://[생성된주소].ngrok.app';
  // 공인 IP 사용 시: static const String baseUrl = 'http://[집의_공인_IP]:8080';
  //static const String baseUrl = 'https://nonschematized-pseudofeverish-ka.ngrok-free.dev';
  static const String baseUrl = 'http://10.0.2.2:8080';
  static Future<Map<String, dynamic>?> getRecommendation({
    required String transport,
    required int personCount,
    required String region,
    required String duration,
    required int days,
    required List<String> themes,
    double? userLat,
    double? userLng,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/ai-predict'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'transport': transport,
          'personCount': personCount,
          'region': region,
          'duration': duration,
          'days': days,
          'themes': themes,
          if (userLat != null) 'userLat': userLat,
          if (userLng != null) 'userLng': userLng,
        }),
      );

      if (response.statusCode == 200) {
        return jsonDecode(utf8.decode(response.bodyBytes));
      } else {
        print('서버 에러 발생: 상태 코드 ${response.statusCode}');
        return null;
      }
    } catch (e) {
      print('네트워크 에러 발생: $e');
      return null;
    }
  }
}