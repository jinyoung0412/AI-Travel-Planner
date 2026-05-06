import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;

class AuthService extends ChangeNotifier {
  static const String baseUrl = 'http://10.0.2.2:8080';

  String? _token;
  String? _nickname;
  String? _profileImg;

  String? get token => _token;
  String? get nickname => _nickname;
  String? get profileImg => _profileImg;
  bool get isLoggedIn => _token != null;

  Future<void> loadFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('jwt_token');
    _nickname = prefs.getString('nickname');
    _profileImg = prefs.getString('profile_img');
    notifyListeners();
  }

  Future<bool> loginWithKakao() async {
    try {
      OAuthToken kakaoToken;
      if (await isKakaoTalkInstalled()) {
        kakaoToken = await UserApi.instance.loginWithKakaoTalk();
      } else {
        kakaoToken = await UserApi.instance.loginWithKakaoAccount();
      }

      final response = await http.post(
        Uri.parse('$baseUrl/auth/kakao'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'access_token': kakaoToken.accessToken}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        _token = data['token'];
        _nickname = data['nickname'];
        _profileImg = data['profile_img'];

        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('jwt_token', _token!);
        if (_nickname != null) await prefs.setString('nickname', _nickname!);
        if (_profileImg != null) await prefs.setString('profile_img', _profileImg!);

        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('[auth] 카카오 로그인 오류: $e');
      return false;
    }
  }

  Future<void> logout() async {
    try {
      await UserApi.instance.logout();
    } catch (_) {}
    _token = null;
    _nickname = null;
    _profileImg = null;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('jwt_token');
    await prefs.remove('nickname');
    await prefs.remove('profile_img');
    notifyListeners();
  }
}
