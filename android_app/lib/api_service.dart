import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // 에뮬레이터에서 로컬 Node.js 서버에 접근하기 위한 IP (10.0.2.2)
  static const String baseUrl = 'http://10.0.2.2:8080';

  // 모든 여행 정보를 받아서 서버로 전송하는 함수
  static Future<Map<String, dynamic>?> getRecommendation({
    required String transport,
    required int personCount,
    required String region,
    required String duration,
    required int days,
    required List<String> themes,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/ai-predict'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'transport': transport,       // 이동 수단 (예: 대중교통/도보)
          'personCount': personCount,   // 인원수 (예: 2)
          'region': region,             // 지역 (예: 충남 전체)
          'duration': duration,         // 텍스트 기간 (예: 1박 2일)
          'days': days,                 // 숫자 일수 (예: 2)
          'themes': themes,             // 테마 리스트 (예: ["바다", "힐링"])
        }),
      );

      if (response.statusCode == 200) {
        // 한글 깨짐 방지를 위해 utf8 디코딩 후 json 파싱
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