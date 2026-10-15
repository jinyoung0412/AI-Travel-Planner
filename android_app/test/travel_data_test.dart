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
    expect(
      distanceNotice({'estimated_distance_km': '1.25'}),
      contains('1.3km (직선거리 추정)'),
    );
    for (final value in [null, 'bad', double.nan, -1]) {
      expect(
        distanceNotice({'estimated_distance_km': value}),
        isNot(contains('km')),
      );
    }
  });
}
