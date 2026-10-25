import 'dart:convert';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/preferences_transaction.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

// Runs the real locked SharedPreferences cache against a separate native memory
// and durable store. Failed writes poison native memory too, so reload is unsafe.
class FaultStore extends InMemorySharedPreferencesStore {
  final Map<String, Object> durable;
  final Map<String, Object> native;
  bool Function(String, Object?)? fail;
  bool throwsInstead = false;
  final writes = <String>[];
  FaultStore(Map<String, Object> initial)
    : durable = Map.from(initial),
      native = Map.from(initial),
      super.empty();
  @override
  Future<Map<String, Object>> getAll() async => Map.from(native);
  @override
  Future<bool> setValue(String type, String key, Object value) async {
    writes.add(key);
    native[key] = value;
    if (fail?.call(key, value) ?? false) {
      if (throwsInstead) throw StateError('synthetic failure');
      return false;
    }
    durable[key] = value;
    return true;
  }

  @override
  Future<bool> remove(String key) async {
    writes.add(key);
    native.remove(key);
    if (fail?.call(key, null) ?? false) {
      if (throwsInstead) throw StateError('synthetic failure');
      return false;
    }
    durable.remove(key);
    return true;
  }

  void restart() {
    native
      ..clear()
      ..addAll(durable);
    SharedPreferences.resetStatic();
  }
}

Map<String, dynamic> place(int id) => {
  'place_id': 'naver:$id',
  'name': '원문 $id',
  'address': '충남 천안시 시험로 $id',
  'identity_aliases': ['local:v1:${'a' * 64}'],
  'custom': {'source': '보존'},
};
Map<String, Object> initial({bool legacy = false}) => {
  'flutter.saved_spots': jsonEncode([place(1)]),
  'flutter.saved_courses': jsonEncode([
    {
      'region': '천안',
      'spots': [place(1), place(2)],
      'metric': {'estimated_distance_km': 1.2},
      'metadata': {'source': 'keep'},
    },
  ]),
  if (!legacy) 'flutter.saved_spots_schema': 2,
  if (!legacy) 'flutter.saved_courses_schema': 2,
};
void main() {
  late FaultStore store;
  void install({bool legacy = false}) {
    store = FaultStore(initial(legacy: legacy));
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
  }

  tearDown(() async {
    // Let a failed-recovery test leave the static storage queue consistent.
    store.fail = null;
    await LocalStorageService.getSavedSpots();
    await LocalStorageService.getSavedCourses();
  });
  for (final throwsInstead in [false, true]) {
    for (final course in [false, true]) {
      test(
        'failed ${course ? 'course' : 'spot'} delete ($throwsInstead) then save preserves original',
        () async {
          install();
          store.throwsInstead = throwsInstead;
          var failed = false;
          final key = course ? 'flutter.saved_courses' : 'flutter.saved_spots';
          final original = store.durable[key];
          store.fail = (k, v) {
            if (k == key && !failed) {
              failed = true;
              return true;
            }
            return false;
          };
          await expectLater(
            course
                ? LocalStorageService.removeCourseBySpots([place(1), place(2)])
                : LocalStorageService.deleteSpot(place(1)),
            throwsStateError,
          );
          expect(store.durable[key], original);
          final prefs = await SharedPreferences.getInstance();
          expect(prefs.getString(key.substring(8)), original);
          if (course) {
            await LocalStorageService.saveCourse('아산', [place(3)]);
            expect((await LocalStorageService.getSavedCourses()).length, 2);
          } else {
            await LocalStorageService.saveSpot(place(3));
            expect((await LocalStorageService.getSavedSpots()).length, 2);
          }
          store.restart();
          expect(
            course
                ? (await LocalStorageService.getSavedCourses()).length
                : (await LocalStorageService.getSavedSpots()).length,
            2,
          );
          expect(
            store.durable.containsKey(
              'flutter.${PreferencesTransaction.journalKey}',
            ),
            false,
          );
        },
      );
    }
  }
  for (final exception in [false, true]) {
    for (final course in [false, true]) {
      final base = course ? 'saved_courses' : 'saved_spots';
      for (final failingKey in [
        PreferencesTransaction.journalKey,
        '${base}_legacy_backup',
        base,
        '${base}_schema',
      ]) {
        test(
          'migration $base failure at $failingKey ($exception) retains raw keys and backup',
          () async {
            install(legacy: true);
            store.throwsInstead = exception;
            final original = Map<String, Object>.from(store.durable);
            var failed = false;
            store.fail = (k, v) {
              if (k == 'flutter.$failingKey' && !failed) {
                failed = true;
                return true;
              }
              return false;
            };
            await expectLater(
              course
                  ? LocalStorageService.getSavedCourses()
                  : LocalStorageService.getSavedSpots(),
              throwsStateError,
            );
            expect(store.durable, original);
            store.restart();
            if (course) {
              await LocalStorageService.getSavedCourses();
            } else {
              await LocalStorageService.getSavedSpots();
            }
            expect(
              store.durable['flutter.${base}_legacy_backup'],
              original['flutter.$base'],
            );
            expect(store.durable['flutter.${base}_schema'], 2);
          },
        );
      }
    }
  }
  test(
    'failed rollback blocks a subsequent save; fresh session recovers durable undo',
    () async {
      install();
      final original = Map<String, Object>.from(store.durable);
      // All writes to the spot key fail, including rollback, and poison native cache.
      store.fail = (k, v) => k == 'flutter.saved_spots';
      await expectLater(
        LocalStorageService.deleteSpot(place(1)),
        throwsStateError,
      );
      final beforeNext = store.writes.length;
      await expectLater(
        LocalStorageService.saveSpot(place(3)),
        throwsStateError,
      );
      expect(
        store.writes
            .skip(beforeNext)
            .where((k) => k == 'flutter.saved_spots')
            .length,
        1,
        reason: 'only recovery attempted, no new save',
      );
      expect(
        store.durable['flutter.saved_spots'],
        original['flutter.saved_spots'],
      );
      expect(
        store.durable.containsKey(
          'flutter.${PreferencesTransaction.journalKey}',
        ),
        true,
      );
      store.fail = null;
      store.restart();
      // A fresh transaction object models process restart; only durable undo exists.
      await PreferencesTransaction().recover(
        await SharedPreferences.getInstance(),
      );
      expect(store.durable, original);
      await LocalStorageService.saveSpot(place(3));
      expect((await LocalStorageService.getSavedSpots()).length, 2);
    },
  );
  test(
    'failed commit-record removal rolls back instead of committing error',
    () async {
      install();
      final original = Map<String, Object>.from(store.durable);
      var once = false;
      store.fail = (k, v) {
        if (k == 'flutter.${PreferencesTransaction.journalKey}' &&
            v == null &&
            !once) {
          once = true;
          return true;
        }
        return false;
      };
      await expectLater(
        LocalStorageService.saveSpot(place(3)),
        throwsStateError,
      );
      expect(store.durable, original);
      await LocalStorageService.saveSpot(place(3));
      expect((await LocalStorageService.getSavedSpots()).length, 2);
    },
  );
  for (final exception in [false, true]) {
    for (final course in [false, true]) {
      test(
        'failed new ${course ? 'course' : 'spot'} save ($exception) does not survive next write or restart',
        () async {
          install();
          store.throwsInstead = exception;
          final key = course ? 'flutter.saved_courses' : 'flutter.saved_spots';
          final original = store.durable[key];
          var once = false;
          store.fail = (k, v) {
            if (k == key && !once) {
              once = true;
              return true;
            }
            return false;
          };
          await expectLater(
            course
                ? LocalStorageService.saveCourse('new', [place(3)])
                : LocalStorageService.saveSpot(place(3)),
            throwsStateError,
          );
          expect(store.durable[key], original);
          await (course
              ? LocalStorageService.saveCourse('next', [place(4)])
              : LocalStorageService.saveSpot(place(4)));
          store.restart();
          final records = course
              ? await LocalStorageService.getSavedCourses()
              : await LocalStorageService.getSavedSpots();
          expect(records.length, 2);
          expect(jsonEncode(records), isNot(contains('naver:3')));
          expect(jsonEncode(records), contains('보존'));
        },
      );
    }
  }
  test(
    'malformed recovery record blocks writes and remains untouched',
    () async {
      install();
      const raw = '{"version":99,"before":{}}';
      store.durable['flutter.${PreferencesTransaction.journalKey}'] = raw;
      store.native['flutter.${PreferencesTransaction.journalKey}'] = raw;
      final original = Map<String, Object>.from(store.durable);
      await expectLater(
        LocalStorageService.saveSpot(place(3)),
        throwsFormatException,
      );
      expect(store.durable, original);
      expect(store.writes, isEmpty);
      // Repair only this synthetic record so shared static state is clean.
      store.durable.remove('flutter.${PreferencesTransaction.journalKey}');
      store.native.remove('flutter.${PreferencesTransaction.journalKey}');
      SharedPreferences.resetStatic();
    },
  );
}
