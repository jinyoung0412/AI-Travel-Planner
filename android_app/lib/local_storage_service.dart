import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocalStorageService {
  static const _spotsKey = 'saved_spots';
  static const _coursesKey = 'saved_courses';

  // Mirrors place_identity.py v1; no fuzzy name matching.
  static String _normalize(dynamic value) => (value ?? '')
      .toString()
      .trim()
      .replaceAll(RegExp(r'\s+'), ' ')
      .toLowerCase()
      .replaceFirst(RegExp(r'^충청남도(?= |$)'), '충남');
  static String _hash(String name, String address) =>
      'local:v1:${sha256.convert(utf8.encode('$name\u001f$address'))}';
  static String _fixedCoordinate(num value) {
    final units = (value.abs() * 1000000 + 0.5).floor();
    final sign = value < 0 && units != 0 ? '-' : '';
    return '$sign${units ~/ 1000000}.${(units % 1000000).toString().padLeft(6, '0')}';
  }

  static String? _coordinateKey(Map<String, dynamic> spot) {
    final lat = num.tryParse('${spot['lat']}');
    final lng = num.tryParse('${spot['lng']}');
    if (lat == null || lng == null || !lat.isFinite || !lng.isFinite) {
      return null;
    }
    return _hash(
      _normalize(spot['name']),
      '@${_fixedCoordinate(lat)},${_fixedCoordinate(lng)}',
    );
  }

  static Map<String, dynamic> identify(
    Map<String, dynamic> spot, {
    String? unresolvedId,
  }) {
    final result = Map<String, dynamic>.from(spot);
    final address = _normalize(spot['address']);
    final alias = address.isNotEmpty
        ? _hash(_normalize(spot['name']), address)
        : _coordinateKey(spot);
    result['identity_key'] = spot['identity_key'] ?? alias;
    if (spot['place_id'] == null || '${spot['place_id']}'.isEmpty) {
      result['place_id'] =
          alias ??
          unresolvedId ??
          'legacy:unresolved:${DateTime.now().microsecondsSinceEpoch}';
      result['identity_origin'] = address.isNotEmpty
          ? 'legacy_address'
          : alias != null
          ? 'legacy_coordinates'
          : 'legacy_unresolved';
    }
    return result;
  }

  static bool samePlace(Map<String, dynamic> a, Map<String, dynamic> b) {
    a = identify(a);
    b = identify(b);
    if (a['place_id'] == b['place_id']) return true;
    final aLocal = '${a['place_id']}'.startsWith('local:v1:');
    final bLocal = '${b['place_id']}'.startsWith('local:v1:');
    if ((aLocal || bLocal) &&
        a['identity_key'] != null &&
        a['identity_key'] == b['identity_key']) {
      return true;
    }
    // Old courses omitted addresses; name + exact six-decimal coordinates is
    // permitted only when at least one side came from that legacy format.
    if (a['identity_origin'] == 'legacy_coordinates' ||
        b['identity_origin'] == 'legacy_coordinates') {
      final key = _coordinateKey(a);
      return key != null && key == _coordinateKey(b);
    }
    return false;
  }

  static Future<List<Map<String, dynamic>>> _read(
    String key, {
    required bool courses,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(key);
    if (raw == null) return [];
    final data = List<Map<String, dynamic>>.from(jsonDecode(raw));
    final migrated = data.asMap().entries.map((entry) {
      if (!courses) {
        return identify(
          entry.value,
          unresolvedId: 'legacy:unresolved:$key:${entry.key}',
        );
      }
      final spots = List<Map<String, dynamic>>.from(entry.value['spots'] ?? []);
      return <String, dynamic>{
        ...entry.value,
        'spots': spots
            .asMap()
            .entries
            .map(
              (s) => identify(
                s.value,
                unresolvedId: 'legacy:unresolved:$key:${entry.key}:${s.key}',
              ),
            )
            .toList(),
      };
    }).toList();
    if (prefs.getInt('${key}_schema') != 2) {
      if (!prefs.containsKey('${key}_legacy_backup')) {
        await prefs.setString('${key}_legacy_backup', raw);
      }
      await prefs.setString(key, jsonEncode(migrated));
      await prefs.setInt('${key}_schema', 2);
    }
    return migrated;
  }

  static Future<List<Map<String, dynamic>>> getSavedSpots() =>
      _read(_spotsKey, courses: false);
  static Future<void> _write(
    String key,
    List<Map<String, dynamic>> items,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, jsonEncode(items));
  }

  static Future<void> saveSpot(Map<String, dynamic> spot) async {
    final spots = await getSavedSpots();
    final index = spots.indexWhere((s) => samePlace(s, spot));
    if (index >= 0) {
      // Upgrade a matched legacy coordinate record to the authoritative ID.
      final updated = identify(spot);
      spots[index] = {
        ...spots[index],
        ...updated,
        'identity_origin': updated['identity_origin'] ?? 'server',
      };
      await _write(_spotsKey, spots);
      return;
    }
    spots.insert(0, {
      ...identify(spot),
      'saved_at': DateTime.now().toIso8601String(),
    });
    await _write(_spotsKey, spots);
  }

  static Future<bool> isSpotSaved(Map<String, dynamic> spot) async =>
      (await getSavedSpots()).any((s) => samePlace(s, spot));
  static Future<void> deleteSpot(Map<String, dynamic> spot) async {
    final spots = await getSavedSpots();
    spots.removeWhere((s) => samePlace(s, spot));
    await _write(_spotsKey, spots);
  }

  static Future<List<Map<String, dynamic>>> getSavedCourses() =>
      _read(_coursesKey, courses: true);
  static List<Map<String, dynamic>> _spots(Map<String, dynamic> course) =>
      List<Map<String, dynamic>>.from(course['spots'] ?? []);
  static bool _sameCourse(
    List<Map<String, dynamic>> a,
    List<Map<String, dynamic>> b,
  ) =>
      a.length == b.length &&
      List.generate(a.length, (i) => samePlace(a[i], b[i])).every((v) => v);
  static Future<void> saveCourse(
    String region,
    List<Map<String, dynamic>> spots,
  ) async {
    final courses = await getSavedCourses();
    courses.removeWhere((c) => _sameCourse(_spots(c), spots));
    courses.insert(0, {
      'region': region,
      'spots': spots.map(identify).toList(),
      'created_at': DateTime.now().toIso8601String(),
    });
    if (courses.length > 100) courses.removeRange(100, courses.length);
    await _write(_coursesKey, courses);
  }

  static Future<bool> isCourseSaved(List<Map<String, dynamic>> spots) async =>
      (await getSavedCourses()).any((c) => _sameCourse(_spots(c), spots));
  static Future<void> removeCourseBySpots(
    List<Map<String, dynamic>> spots,
  ) async {
    final courses = await getSavedCourses();
    courses.removeWhere((c) => _sameCourse(_spots(c), spots));
    await _write(_coursesKey, courses);
  }

  static Future<void> deleteCourse(int index) async {
    final courses = await getSavedCourses();
    if (index < 0 || index >= courses.length) return;
    courses.removeAt(index);
    await _write(_coursesKey, courses);
  }
}
