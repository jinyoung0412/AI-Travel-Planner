import 'dart:convert';
import 'dart:io';
import 'package:ai_travel_app/transit_hubs.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'all selectable hubs match named public-map references and are regional',
    () {
      final fixture =
          jsonDecode(File('test/fixtures/transit_hubs.json').readAsStringSync())
              as Map;
      final references = (fixture['hubs'] as List).cast<Map>();
      expect(references.length, 12);
      expect(
        transitHubs.values.fold<int>(0, (sum, hubs) => sum + hubs.length),
        references.length,
      );
      for (final row in references) {
        final hub = transitHubs[row['region']]!.singleWhere(
          (h) => h.name == row['name'],
        );
        expect(hub.lat, row['lat']);
        expect(hub.lng, row['lng']);
        expect(hub.address, row['address']);
        expect(hub.sourceUrl, row['source_url']);
        expect(hub.lat, inInclusiveRange(36.7, 36.9));
        expect(hub.lng, inInclusiveRange(126.9, 127.2));
        expect(
          row['coordinate_meaning'],
          'station_or_terminal_representative_point',
        );
      }
      final a = transitHubs['천안']!.singleWhere((h) => h.name.contains('KTX'));
      final b = transitHubs['아산']!.singleWhere((h) => h.name.contains('KTX'));
      expect([a.lat, a.lng], [b.lat, b.lng]);
    },
  );
  test(
    'Apple runner inputs contain minimum location and sandbox capabilities',
    () {
      final ios = File('ios/Runner/Info.plist').readAsStringSync();
      final mac = File('macos/Runner/Info.plist').readAsStringSync();
      expect(ios, contains('NSLocationWhenInUseUsageDescription'));
      expect(ios, isNot(contains('NSLocationAlways')));
      expect(ios, isNot(contains('UIBackgroundModes')));
      expect(mac, contains('NSLocationUsageDescription'));
      for (final name in ['DebugProfile', 'Release']) {
        final ent = File('macos/Runner/$name.entitlements').readAsStringSync();
        for (final key in [
          'app-sandbox',
          'network.client',
          'personal-information.location',
        ]) {
          expect(
            ent,
            contains('<key>com.apple.security.$key</key>\n\t<true/>'),
          );
        }
      }
    },
  );
}
