import 'dart:async';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'travel_data.dart';
import 'preferences_transaction.dart';

class LocalStorageService {
  static const _spotsKey = 'saved_spots';
  static const _coursesKey = 'saved_courses';

  static Future<void>? _pending;
  static int _unresolvedSequence = 0;
  static final _transaction = PreferencesTransaction();

  // SharedPreferences has no atomic read-modify-write operation. Queue reads too,
  // since first reads migrate legacy data. The queue is scoped to this isolate.
  static Future<T> _serial<T>(Future<T> Function() operation) {
    final previous = _pending;
    final released = Completer<void>();
    _pending = released.future;
    return () async {
      try {
        if (previous != null) await previous;
        final prefs = await SharedPreferences.getInstance();
        // Do not run even a migrating read against uncertain native/cache data.
        await _transaction.recover(prefs);
        try {
          final result = await operation();
          await _transaction.commit(prefs);
          return result;
        } catch (_) {
          // If recovery also fails, its undo record remains and the next
          // operation must recover successfully before it can proceed.
          await _transaction.recover(prefs);
          rethrow;
        }
      } finally {
        if (identical(_pending, released.future)) _pending = null;
        released.complete();
      }
    }();
  }

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
    if (spot['place_id'] == null || '${spot['place_id']}'.trim().isEmpty) {
      result['place_id'] =
          alias ??
          unresolvedId ??
          'legacy:unresolved:${DateTime.now().microsecondsSinceEpoch}:${_unresolvedSequence++}';
      result['identity_origin'] = address.isNotEmpty
          ? 'legacy_address'
          : alias != null
          ? 'legacy_coordinates'
          : 'legacy_unresolved';
    }
    return result;
  }

  static final _localId = RegExp(r'^local:v1:[0-9a-f]{64}$');

  static Object? _optionalJson(Object? value) {
    if (value is! String) return value;
    try {
      return jsonDecode(value);
    } on FormatException {
      return null;
    }
  }

  static Set<String> _aliases(Map<String, dynamic> spot) {
    final stored = _optionalJson(spot['identity_aliases']);
    return [
      if (stored is List) ...stored,
      spot['place_id'],
      spot['identity_key'],
    ].whereType<String>().where(_localId.hasMatch).toSet();
  }

  static Map<String, Set<String>> _conflicts(Map<String, dynamic> spot) {
    final stored = _optionalJson(spot['identity_alias_conflicts']);
    if (stored is! Map) return {};
    final result = <String, Set<String>>{};
    for (final entry in stored.entries) {
      if (entry.key is! String ||
          !_localId.hasMatch(entry.key) ||
          entry.value is! List) {
        continue;
      }
      final owners = (entry.value as List)
          .whereType<String>()
          .where((id) => id.contains(':') && !id.startsWith('local:v1:'))
          .toSet();
      if (owners.length > 1) result[entry.key as String] = owners;
    }
    return result;
  }

  static bool samePlace(Map<String, dynamic> a, Map<String, dynamic> b) {
    a = identify(a);
    b = identify(b);
    if (a['place_id'] == b['place_id']) return true;
    // Two provider identities remain distinct even if a legacy origin marker
    // or an old alias survived a previous client migration.
    if (_authoritative(a) && _authoritative(b)) return false;
    final blocked = {..._conflicts(a).keys, ..._conflicts(b).keys};
    final aLocal = '${a['place_id']}'.startsWith('local:v1:');
    final bLocal = '${b['place_id']}'.startsWith('local:v1:');
    if (aLocal || bLocal) {
      final shared = _aliases(a).intersection(_aliases(b))..removeAll(blocked);
      if (shared.isNotEmpty) return true;
    }
    // Addressless old courses use exact six-decimal coordinates, unless that
    // same alias is known to have belonged to multiple provider identities.
    if (a['identity_origin'] == 'legacy_coordinates' ||
        b['identity_origin'] == 'legacy_coordinates') {
      final key = _coordinateKey(a);
      return key != null && !blocked.contains(key) && key == _coordinateKey(b);
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
    final data = jsonObjects(jsonDecode(raw));
    final migrated = data.asMap().entries.map((entry) {
      if (!courses) {
        return identify(
          entry.value,
          unresolvedId: 'legacy:unresolved:$key:${entry.key}',
        );
      }
      final spots = jsonObjects(entry.value['spots'] ?? []);
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
        await _transaction.write(prefs, '${key}_legacy_backup', raw);
      }
      await _transaction.write(prefs, key, jsonEncode(migrated));
      await _transaction.write(prefs, '${key}_schema', 2);
    }
    return migrated;
  }

  static Future<List<Map<String, dynamic>>> getSavedSpots() =>
      _serial(() => _read(_spotsKey, courses: false));
  static Future<void> _write(
    String key,
    List<Map<String, dynamic>> items,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await _transaction.write(prefs, key, jsonEncode(items));
  }

  static Future<void> saveSpot(Map<String, dynamic> spot) {
    final snapshot = Map<String, dynamic>.from(spot);
    return _serial(() => _saveSpot(snapshot));
  }

  static bool _authoritative(Map<String, dynamic> spot) {
    final id = '${spot['place_id'] ?? ''}';
    return id.isNotEmpty &&
        !id.startsWith('local:v1:') &&
        !id.startsWith('legacy:');
  }

  static Map<String, dynamic> _mergeSpot(
    Map<String, dynamic> existing,
    Map<String, dynamic> incoming,
  ) {
    final updated = identify(incoming);
    // A stale legacy screen must not downgrade an already upgraded provider ID.
    final result = _authoritative(existing) && !_authoritative(updated)
        ? <String, dynamic>{...updated, ...existing}
        : <String, dynamic>{
            ...existing,
            ...updated,
            'identity_origin': updated['identity_origin'] ?? 'server',
          };
    final conflicts = _conflicts(existing);
    for (final entry in _conflicts(updated).entries) {
      conflicts.putIfAbsent(entry.key, () => <String>{}).addAll(entry.value);
    }
    return {
      ...result,
      'identity_aliases': ({
        ..._aliases(existing),
        ..._aliases(updated),
      }.toList()..sort()),
      'identity_alias_conflicts': {
        for (final entry in conflicts.entries)
          entry.key: (entry.value.toList()..sort()),
      },
    };
  }

  static Future<void> _saveSpot(Map<String, dynamic> spot) async {
    final spots = await _read(_spotsKey, courses: false);
    final index = spots.indexWhere((s) => samePlace(s, spot));
    if (index >= 0) {
      spots[index] = _mergeSpot(spots[index], spot);
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
  static Future<void> deleteSpot(Map<String, dynamic> spot) =>
      _serial(() async {
        final spots = await _read(_spotsKey, courses: false);
        spots.removeWhere((s) => samePlace(s, spot));
        await _write(_spotsKey, spots);
      });

  static Future<List<Map<String, dynamic>>> getSavedCourses() =>
      _serial(() => _read(_coursesKey, courses: true));
  static List<Map<String, dynamic>> _spots(Map<String, dynamic> course) =>
      jsonObjects(course['spots'] ?? []);
  static bool _sameCourse(
    List<Map<String, dynamic>> a,
    List<Map<String, dynamic>> b,
  ) =>
      a.length == b.length &&
      List.generate(a.length, (i) => samePlace(a[i], b[i])).every((v) => v);
  static Future<void> saveCourse(
    String region,
    List<Map<String, dynamic>> spots, {
    Map<String, dynamic>? metric,
    Map<String, dynamic>? metadata,
  }) {
    final snapshot = spots.map((s) => Map<String, dynamic>.from(s)).toList();
    final savedMetric = metric == null
        ? null
        : Map<String, dynamic>.from(metric);
    final savedMetadata = metadata == null
        ? null
        : Map<String, dynamic>.from(metadata);
    return _serial(() async {
      final spots = snapshot;
      final courses = await _read(_coursesKey, courses: true);
      final index = courses.indexWhere((c) => _sameCourse(_spots(c), spots));
      final existing = index >= 0 ? courses[index] : <String, dynamic>{};
      final existingSpots = index >= 0
          ? _spots(existing)
          : <Map<String, dynamic>>[];
      final mergedSpots = List.generate(
        spots.length,
        (i) => index >= 0
            ? _mergeSpot(existingSpots[i], spots[i])
            : identify(spots[i]),
      );
      courses.removeWhere((c) => _sameCourse(_spots(c), spots));
      courses.insert(0, {
        ...existing,
        'region': region,
        if (savedMetric != null) 'metric': savedMetric,
        if (savedMetadata != null) 'metadata': savedMetadata,
        'spots': mergedSpots,
        'created_at': DateTime.now().toIso8601String(),
      });
      if (courses.length > 100) courses.removeRange(100, courses.length);
      await _write(_coursesKey, courses);
    });
  }

  static Future<bool> isCourseSaved(List<Map<String, dynamic>> spots) async =>
      (await getSavedCourses()).any((c) => _sameCourse(_spots(c), spots));
  static Future<void> removeCourseBySpots(List<Map<String, dynamic>> spots) {
    final snapshot = spots.map((s) => Map<String, dynamic>.from(s)).toList();
    return _serial(() async {
      final courses = await _read(_coursesKey, courses: true);
      courses.removeWhere((c) => _sameCourse(_spots(c), snapshot));
      await _write(_coursesKey, courses);
    });
  }

  static Future<void> deleteCourse(int index) => _serial(() async {
    final courses = await _read(_coursesKey, courses: true);
    if (index < 0 || index >= courses.length) return;
    courses.removeAt(index);
    await _write(_coursesKey, courses);
  });
}
