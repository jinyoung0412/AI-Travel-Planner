import 'dart:async';
import 'package:ai_travel_app/location_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

void main() {
  DeviceLocationSource source({
    bool enabled = true,
    LocationPermission permission = LocationPermission.whileInUse,
    LocationPermission requested = LocationPermission.denied,
    Future<Position> Function()? position,
    Duration timeout = const Duration(seconds: 1),
  }) => DeviceLocationSource(
    serviceEnabled: () async => enabled,
    checkPermission: () async => permission,
    requestPermission: () async => requested,
    position:
        position ??
        () async => Position(
          latitude: 36.8151,
          longitude: 127.1139,
          timestamp: DateTime(2026),
          accuracy: 1,
          altitude: 0,
          altitudeAccuracy: 1,
          heading: 0,
          headingAccuracy: 1,
          speed: 0,
          speedAccuracy: 1,
        ),
    timeout: timeout,
  );
  Matcher failure(LocationFailure value) =>
      isA<LocationException>().having((e) => e.failure, 'failure', value);

  test(
    'location service disabled does not request permission or position',
    () async {
      var called = false;
      final device = DeviceLocationSource(
        serviceEnabled: () async => false,
        checkPermission: () async {
          called = true;
          return LocationPermission.always;
        },
        position: () {
          called = true;
          throw StateError('unexpected');
        },
      );
      await expectLater(
        device.locate(),
        throwsA(failure(LocationFailure.serviceDisabled)),
      );
      expect(called, false);
    },
  );
  test('denial and permanent denial have distinct recovery guidance', () async {
    await expectLater(
      source(permission: LocationPermission.denied).locate(),
      throwsA(failure(LocationFailure.denied)),
    );
    await expectLater(
      source(permission: LocationPermission.deniedForever).locate(),
      throwsA(failure(LocationFailure.deniedForever)),
    );
  });
  test('permission request can grant access', () async {
    final fix = await source(
      permission: LocationPermission.denied,
      requested: LocationPermission.whileInUse,
    ).locate();
    expect(fix.lat, 36.8151);
    expect(fix.lng, 127.1139);
  });
  test(
    'hanging GPS is bounded and exceptions become recoverable errors',
    () async {
      final pending = Completer<Position>();
      await expectLater(
        source(
          position: () => pending.future,
          timeout: const Duration(milliseconds: 5),
        ).locate(),
        throwsA(failure(LocationFailure.timeout)),
      );
      await expectLater(
        source(
          position: () async => throw StateError('plugin failed'),
        ).locate(),
        throwsA(failure(LocationFailure.unavailable)),
      );
    },
  );
}
