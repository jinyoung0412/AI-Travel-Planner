import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ai_travel_app/local_storage_service.dart';

Map<String, dynamic> spot(String id, String address, double lng) => {
  'place_id': id,
  'name': '아지트',
  'address': address,
  'lat': 36.8151,
  'lng': lng,
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  test('Python and Dart identities agree and normalize province-whitespace', () {
    final a = LocalStorageService.identify({
      'name': '장소0',
      'address': '충남 천안시 테스트로 1',
    });
    final b = LocalStorageService.identify({
      'name': '장소0',
      'address': '충청남도   천안시 테스트로 1',
    });
    expect(
      a['place_id'],
      'local:v1:2f4e6866656d892d2d14e6fa1c033c29be51683bc677fd4e6ae9e5030cc02edc',
    );
    expect(a['place_id'], b['place_id']);
  });
  test(
    'same names in different branches save and delete independently',
    () async {
      final a = spot('naver:1', '충남 천안시 테스트로 1', 127.11);
      final b = spot('naver:2', '충남 아산시 테스트로 2', 127.12);
      await LocalStorageService.saveSpot(a);
      await LocalStorageService.saveSpot(b);
      await LocalStorageService.saveSpot(a);
      expect((await LocalStorageService.getSavedSpots()).length, 2);
      await LocalStorageService.deleteSpot(a);
      expect(await LocalStorageService.isSpotSaved(a), false);
      expect(await LocalStorageService.isSpotSaved(b), true);
    },
  );
  test(
    'legacy spot migrates while retaining timestamp, backup and bookmark',
    () async {
      const raw =
          '[{"name":"아지트","address":"충남 천안시 테스트로 1","lat":36.8151,"lng":127.11,"saved_at":"old"}]';
      SharedPreferences.setMockInitialValues({'saved_spots': raw});
      final saved = await LocalStorageService.getSavedSpots();
      expect(saved.single['place_id'], startsWith('local:v1:'));
      expect(saved.single['saved_at'], 'old');
      expect(
        await LocalStorageService.isSpotSaved(
          spot('naver:1', '충남 천안시 테스트로 1', 127.11),
        ),
        true,
      );
      expect(
        (await SharedPreferences.getInstance()).getString(
          'saved_spots_legacy_backup',
        ),
        raw,
      );
      expect(await LocalStorageService.getSavedSpots(), saved);
    },
  );
  test(
    'old course without address matches name-coordinates in slot order',
    () async {
      final old = [
        {'name': '아지트', 'lat': 36.8151, 'lng': 127.11},
        {'name': '아지트', 'lat': 36.8151, 'lng': 127.12},
      ];
      SharedPreferences.setMockInitialValues({
        'saved_courses': jsonEncode([
          {'region': '천안', 'spots': old, 'created_at': 'old'},
        ]),
      });
      final modern = [
        spot('naver:1', '충남 천안시 테스트로 1', 127.11),
        spot('naver:2', '충남 아산시 테스트로 2', 127.12),
      ];
      expect(await LocalStorageService.isCourseSaved(modern), true);
      expect(
        await LocalStorageService.isCourseSaved(modern.reversed.toList()),
        false,
      );
      await LocalStorageService.removeCourseBySpots(modern);
      expect(await LocalStorageService.getSavedCourses(), isEmpty);
      expect(
        (await SharedPreferences.getInstance()).getString(
          'saved_courses_legacy_backup',
        ),
        isNotNull,
      );
    },
  );
  test('courses with same names and different IDs remain distinct', () async {
    final a = [spot('naver:1', '충남 천안시 테스트로 1', 127.11)];
    final b = [spot('naver:2', '충남 아산시 테스트로 2', 127.12)];
    await LocalStorageService.saveCourse('천안', a);
    await LocalStorageService.saveCourse('아산', b);
    expect((await LocalStorageService.getSavedCourses()).length, 2);
    await LocalStorageService.removeCourseBySpots(a);
    expect(await LocalStorageService.isCourseSaved(b), true);
  });
  test('distinct provider IDs do not merge through name-address alias', () {
    expect(
      LocalStorageService.samePlace(
        spot('naver:1', '충남 천안시 테스트로 1', 127.11),
        spot('naver:2', '충남 천안시 테스트로 1', 127.11),
      ),
      false,
    );
  });
  test(
    'name-only unresolved records preserved and never match a branch',
    () async {
      SharedPreferences.setMockInitialValues({
        'saved_spots': '[{"name":"아지트"}]',
      });
      final old = (await LocalStorageService.getSavedSpots()).single;
      expect(old['identity_origin'], 'legacy_unresolved');
      expect(
        await LocalStorageService.isSpotSaved(
          spot('naver:1', '충남 천안시 테스트로 1', 127.11),
        ),
        false,
      );
      await LocalStorageService.deleteSpot(old);
      expect(await LocalStorageService.getSavedSpots(), isEmpty);
    },
  );
  test('coordinate alias rounding agrees and legacy save upgrades ID', () async {
    final edge = LocalStorageService.identify({
      'name': '좌표장소',
      'lat': 36.8151005,
      'lng': 127.1139005,
    });
    expect(
      edge['place_id'],
      'local:v1:18bbb278a8e17464d0ca5146e70a87422ca98bb9507f82567d68a0298aa72c65',
    );
    SharedPreferences.setMockInitialValues({
      'saved_spots':
          '[{"name":"아지트","lat":36.8151,"lng":127.11,"saved_at":"old"}]',
    });
    final modern = spot('naver:1', '충남 천안시 테스트로 1', 127.11);
    await LocalStorageService.saveSpot(modern);
    final saved = (await LocalStorageService.getSavedSpots()).single;
    expect(saved['place_id'], 'naver:1');
    expect(saved['identity_origin'], 'server');
    expect(saved['saved_at'], 'old');
    expect(
      LocalStorageService.samePlace(
        saved,
        spot('naver:2', '충남 천안시 테스트로 1', 127.11),
      ),
      false,
    );
  });
}
