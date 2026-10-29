import 'package:ai_travel_app/travel_data.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'place boundary accepts numeric coordinates and preserves identity and tags',
    () {
      final place = PlaceData.fromJson({
        'place_id': 'naver:1',
        'identity_key': 'alias',
        'name': '카페',
        'lat': '36.8',
        'lng': 127,
        'tags': ['친구와'],
        'category': null,
      });
      expect(place.lat, 36.8);
      expect(place.lng, 127.0);
      expect(place.category, '');
      expect(place.toJson()['tags'], ['친구와']);
      expect(place.toJson()['identity_key'], 'alias');
      expect(PlaceData.fromJson({'lat': 'NaN', 'lng': 999}).lat, isNull);
      expect(PlaceData.fromJson({'lat': 'NaN', 'lng': 999}).lng, isNull);
    },
  );
  test(
    'wrapped and legacy response lists retain course order without silently dropping stops',
    () {
      final data = RecommendationData.fromJson({
        'data': {
          'courses': [
            [
              {'name': '첫째'},
              {'name': '둘째'},
            ],
          ],
        },
      });
      expect(data.courses.single.map((s) => s['name']), ['첫째', '둘째']);
      expect(RecommendationData.fromJson({'places': []}).places, isEmpty);
      expect(
        () => RecommendationData.fromJson({
          'courses': [
            [{}, null],
          ],
        }).courses,
        throwsFormatException,
      );
      expect(
        () => RecommendationData.fromJson({'places': {}}).places,
        throwsFormatException,
      );
      expect(() => jsonObject({1: 'wrong key'}), throwsFormatException);
    },
  );
  test('distance notice only shows finite nonnegative estimates', () {
    expect(distanceNotice({'estimated_distance_km': '1.25'}), '직선거리 약 1.3 km');
    for (final value in [null, 'bad', double.nan, -1]) {
      expect(
        distanceNotice({'estimated_distance_km': value}),
        isNot(contains('km')),
      );
    }
  });
  test(
    'coordinate-quality restrictions survive DTO round trip without inventing verification',
    () {
      for (final quality in [
        null,
        'bad',
        {'status': 'unverified', 'map_coordinate_eligible': true},
      ]) {
        final place = PlaceData.fromJson({
          'coordinate_quality': quality,
          'address': '충남 천안시 충절로 410',
        });
        expect(place.coordinateMapAllowed, true);
        expect(place.coordinateDistanceAllowed, true);
        expect(place.toJson()['coordinate_quality'], quality);
        expect(
          distanceNotice(
            {'estimated_distance_km': 1.2},
            places: [place.toJson()],
          ),
          '직선거리 약 1.2 km',
        );
      }
      for (final quality in [
        {'status': 'blocked'},
        {'map_coordinate_eligible': false, 'distance_eligible': false},
      ]) {
        final place = PlaceData.fromJson({'coordinate_quality': quality});
        expect(place.coordinateMapAllowed, false);
        expect(place.coordinateDistanceAllowed, false);
        expect(place.toJson()['coordinate_quality'], quality);
        expect(
          distanceNotice(
            {'estimated_distance_km': 1.2},
            places: [place.toJson()],
          ),
          isNot(contains('km')),
        );
      }
    },
  );
  test(
    'wrapped and legacy metadata retain optional spatial limit alongside taste evidence',
    () {
      const limitation = '주변 장소와의 거리는 적용하지 않았습니다.';
      for (final wrapped in [false, true]) {
        final payload = {
          'places': <Object>[],
          'metadata': {
            'spatial_relation_limitation': limitation,
            'preference_evidence': 'unavailable',
            'preference_limitation': '취향 근거 없음',
          },
        };
        final data = RecommendationData.fromJson(
          wrapped ? {'data': payload} : payload,
        );
        expect(data.metadata['spatial_relation_limitation'], limitation);
        expect(data.metadata['preference_evidence'], 'unavailable');
        expect(data.places, isEmpty);
      }
      expect(RecommendationData.fromJson({'places': []}).metadata, isEmpty);
    },
  );
}
