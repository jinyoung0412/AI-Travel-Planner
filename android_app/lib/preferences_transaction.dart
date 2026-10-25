import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// A write-ahead undo record for the app's six legacy preference keys.
/// A failed plugin write can change both Dart and native memory, so reload alone
/// is not a rollback. Recovery must acknowledge every restore before new writes.
class PreferencesTransaction {
  static const journalKey = 'saved_travel_undo_v1';
  static const keys = [
    'saved_spots',
    'saved_courses',
    'saved_spots_schema',
    'saved_courses_schema',
    'saved_spots_legacy_backup',
    'saved_courses_legacy_backup',
  ];
  Map<String, Object?>? _before;

  static Future<void> _ack(Future<bool> write) async {
    if (!await write) throw StateError('저장소에 기록하지 못했습니다.');
  }

  Map<String, Object?> _decode(String raw) {
    final value = jsonDecode(raw);
    if (value is! Map || value['version'] != 1 || value['before'] is! Map) {
      throw const FormatException('저장소 복구 기록을 확인하지 못했습니다.');
    }
    final before = Map<String, Object?>.from(value['before'] as Map);
    if (before.length != keys.length || !keys.every(before.containsKey)) {
      throw const FormatException('저장소 복구 항목을 확인하지 못했습니다.');
    }
    for (final value in before.values) {
      if (value != null &&
          value is! String &&
          value is! int &&
          value is! bool &&
          value is! double &&
          !(value is List && value.every((e) => e is String))) {
        throw const FormatException('저장소 복구 값이 올바르지 않습니다.');
      }
    }
    return before;
  }

  String get _record => jsonEncode({'version': 1, 'before': _before});

  Future<void> recover(SharedPreferences prefs) async {
    final raw = prefs.getString(journalKey);
    if (_before == null && raw == null) return;
    _before ??= _decode(raw!);
    // Re-establish the undo record even if a failed remove poisoned its cache.
    await _ack(prefs.setString(journalKey, _record));
    for (final entry in _before!.entries) {
      await _set(prefs, entry.key, entry.value);
    }
    await _ack(prefs.remove(journalKey));
    _before = null;
  }

  Future<void> write(SharedPreferences prefs, String key, Object value) async {
    if (!keys.contains(key)) throw ArgumentError.value(key);
    if (_before == null) {
      _before = {for (final key in keys) key: prefs.get(key)};
      // No application key is mutated until the undo record is acknowledged.
      await _ack(prefs.setString(journalKey, _record));
    }
    await _set(prefs, key, value);
  }

  Future<void> commit(SharedPreferences prefs) async {
    if (_before == null) return;
    await _ack(prefs.remove(journalKey));
    _before = null;
  }

  Future<void> _set(SharedPreferences prefs, String key, Object? value) =>
      _ack(switch (value) {
        null => prefs.remove(key),
        String v => prefs.setString(key, v),
        int v => prefs.setInt(key, v),
        bool v => prefs.setBool(key, v),
        double v => prefs.setDouble(key, v),
        List v => prefs.setStringList(key, v.cast<String>()),
        _ => throw const FormatException('지원하지 않는 저장 값입니다.'),
      });
}
