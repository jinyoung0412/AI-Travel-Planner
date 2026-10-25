import 'dart:convert';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> place(int id) => {
  'place_id': 'naver:$id',
  'name': '동명 지점',
  'address': '충남 천안시 $id',
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('simultaneous spot saves preserve all branches', () async {
    await Future.wait(
      List.generate(20, (i) => LocalStorageService.saveSpot(place(i))),
    );
    expect((await LocalStorageService.getSavedSpots()).length, 20);
  });

  test(
    'simultaneous course saves preserve slot order and all courses',
    () async {
      await Future.wait(
        List.generate(
          10,
          (i) => LocalStorageService.saveCourse('천안', [place(i), place(i + 1)]),
        ),
      );
      final courses = await LocalStorageService.getSavedCourses();
      expect(courses.length, 10);
      expect(courses.last['spots'], [
        LocalStorageService.identify(place(0)),
        LocalStorageService.identify(place(1)),
      ]);
    },
  );

  test('save followed by delete is applied in invocation order', () async {
    await LocalStorageService.saveSpot(place(0));
    await Future.wait([
      LocalStorageService.saveSpot(place(1)),
      LocalStorageService.deleteSpot(place(0)),
    ]);
    expect(
      (await LocalStorageService.getSavedSpots()).map((s) => s['place_id']),
      ['naver:1'],
    );
  });

  test(
    'invalid stored data is preserved and later operations can recover',
    () async {
      const raw = '[{"name":"기존 장소"},null]';
      SharedPreferences.setMockInitialValues({'saved_spots': raw});
      await expectLater(
        LocalStorageService.saveSpot(place(1)),
        throwsFormatException,
      );
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('saved_spots'), raw);
      expect(prefs.containsKey('saved_spots_schema'), false);
      await prefs.setString('saved_spots', jsonEncode([place(0)]));
      await LocalStorageService.saveSpot(place(1));
      expect((await LocalStorageService.getSavedSpots()).length, 2);
    },
  );
  test(
    'concurrent first reads and mutation keep exactly the original legacy backup',
    () async {
      const raw = '[{"name":"기존 장소","address":"충남 천안시 0","saved_at":"old"}]';
      SharedPreferences.setMockInitialValues({'saved_spots': raw});
      await Future.wait([
        LocalStorageService.getSavedSpots(),
        LocalStorageService.saveSpot(place(1)),
        LocalStorageService.getSavedSpots(),
      ]);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('saved_spots_legacy_backup'), raw);
      expect(prefs.getInt('saved_spots_schema'), 2);
      expect((await LocalStorageService.getSavedSpots()).length, 2);
      expect(
        (await LocalStorageService.getSavedSpots()).last['saved_at'],
        'old',
      );
      await LocalStorageService.getSavedSpots();
      expect(prefs.getString('saved_spots_legacy_backup'), raw);
    },
  );

  test(
    'queued write snapshots its input before callers change the map',
    () async {
      final item = place(1);
      final pending = LocalStorageService.saveSpot(item);
      item['name'] = 'changed';
      await pending;
      expect(
        (await LocalStorageService.getSavedSpots()).single['name'],
        '동명 지점',
      );
    },
  );
  test(
    'stale legacy saves do not downgrade authoritative spot or course IDs',
    () async {
      final modern = place(1);
      final legacy = Map<String, dynamic>.from(modern)..remove('place_id');
      await LocalStorageService.saveSpot(modern);
      await LocalStorageService.saveSpot(legacy);
      expect(
        (await LocalStorageService.getSavedSpots()).single['place_id'],
        'naver:1',
      );
      await LocalStorageService.saveSpot({...modern, 'place_id': 'naver:2'});
      expect((await LocalStorageService.getSavedSpots()).length, 2);

      await LocalStorageService.saveCourse(
        '천안',
        [modern],
        metric: {'estimated_distance_km': 1.2},
      );
      await LocalStorageService.saveCourse('천안', [legacy]);
      final course = (await LocalStorageService.getSavedCourses()).single;
      expect(course['spots'][0]['place_id'], 'naver:1');
      expect(course['metric'], {'estimated_distance_km': 1.2});
      await LocalStorageService.saveCourse('천안', [
        {...modern, 'place_id': 'naver:2'},
      ]);
      expect((await LocalStorageService.getSavedCourses()).length, 2);
    },
  );
}
