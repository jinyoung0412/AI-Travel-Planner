import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // 🚨 [에뮬레이터 전용 특수 IP]
  // localhost(127.0.0.1) 대신 10.0.2.2를 써야 컴퓨터의 서버와 연결됩니다.
  static const String baseUrl = "http://10.0.2.2:8080";

  // AI 여행 코스 추천 요청 함수
  static Future<Map<String, dynamic>> getRecommendation(List<String> tags, int days) async {
    final url = Uri.parse('$baseUrl/api/recommend');

    try {
      print("🚀 [에뮬레이터] 서버로 데이터 전송: $tags, $days일");

      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "tags": tags,
          "days": days,
        }),
      );

      if (response.statusCode == 200) {
        // 한글 깨짐 방지를 위한 utf8 디코딩 처리
        var decodedData = utf8.decode(response.bodyBytes);
        print("✅ 서버 응답 성공: $decodedData");
        return jsonDecode(decodedData);
      } else {
        print("🔥 서버 에러: ${response.statusCode}");
        throw Exception("서버 통신 실패: ${response.statusCode}");
      }
    } catch (e) {
      print("❌ 연결 오류: $e");
      throw Exception("서버 연결 실패. (Node.js 켜져 있는지 확인!)");
    }
  }
}