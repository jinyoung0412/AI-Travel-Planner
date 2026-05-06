import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

class LocalStorageService {
  static const _spotsKey = 'saved_spots';
  static const _coursesKey = 'saved_courses';

  static Future<List<Map<String, dynamic>>> getSavedSpots() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_spotsKey);
    if (raw == null) return [];
    return List<Map<String, dynamic>>.from(jsonDecode(raw));
  }

  static Future<void> saveSpot(Map<String, dynamic> spot) async {
    final spots = await getSavedSpots();
    final exists = spots.any((s) => s['name'] == spot['name']);
    if (exists) return;
    spots.insert(0, {...spot, 'saved_at': DateTime.now().toIso8601String()});
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_spotsKey, jsonEncode(spots));
  }

  static Future<bool> isSpotSaved(String name) async {
    final spots = await getSavedSpots();
    return spots.any((s) => s['name'] == name);
  }

  static Future<void> deleteSpot(String name) async {
    final spots = await getSavedSpots();
    spots.removeWhere((s) => s['name'] == name);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_spotsKey, jsonEncode(spots));
  }

  static Future<List<Map<String, dynamic>>> getSavedCourses() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_coursesKey);
    if (raw == null) return [];
    return List<Map<String, dynamic>>.from(jsonDecode(raw));
  }

  static Future<void> saveCourse(String region, List<Map<String, dynamic>> spots) async {
    final courses = await getSavedCourses();
    courses.insert(0, {
      'region': region,
      'spots': spots,
      'created_at': DateTime.now().toIso8601String(),
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_coursesKey, jsonEncode(courses));
  }

  static Future<void> deleteCourse(int index) async {
    final courses = await getSavedCourses();
    if (index < 0 || index >= courses.length) return;
    courses.removeAt(index);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_coursesKey, jsonEncode(courses));
  }
}
