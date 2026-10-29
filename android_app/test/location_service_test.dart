import 'dart:async';
import 'package:ai_travel_app/location_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:geolocator_android/geolocator_android.dart'
    show GeolocatorAndroid;
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
  test(
    'timeout cancels each stream and retry has no overlapping subscription',
    () async {
      var active = 0, maximum = 0, cancels = 0;
      final settings = <LocationSettings>[];
      final source = DeviceLocationSource(
        timeout: const Duration(milliseconds: 20),
        serviceEnabled: () async => true,
        checkPermission: () async => LocationPermission.whileInUse,
        positionStream: (s) {
          settings.add(s);
          return StreamController<Position>(
            onListen: () {
              active++;
              if (active > maximum) maximum = active;
            },
            onCancel: () {
              active--;
              cancels++;
            },
          ).stream;
        },
      );
      for (var i = 0; i < 2; i++) {
        await expectLater(
          source.locate(),
          throwsA(failure(LocationFailure.timeout)),
        );
        expect(active, 0);
      }
      expect(maximum, 1);
      expect(cancels, 2);
      expect(
        settings.every(
          (s) =>
              s.timeLimit != null &&
              s.timeLimit! > Duration.zero &&
              s.timeLimit! <= const Duration(milliseconds: 20),
        ),
        true,
      );
    },
  );
  test(
    'late permission after timeout cannot start a native position stream',
    () async {
      final permission = Completer<LocationPermission>();
      var starts = 0;
      final source = DeviceLocationSource(
        timeout: const Duration(milliseconds: 10),
        serviceEnabled: () async => true,
        checkPermission: () async => LocationPermission.denied,
        requestPermission: () => permission.future,
        positionStream: (_) {
          starts++;
          return const Stream.empty();
        },
      );
      await expectLater(
        source.locate(),
        throwsA(failure(LocationFailure.timeout)),
      );
      permission.complete(LocationPermission.whileInUse);
      await Future<void>.delayed(Duration.zero);
      expect(starts, 0);
    },
  );
  test(
    'cancel during permission prevents late GPS and an active retry shares prompt',
    () async {
      final permission = Completer<LocationPermission>();
      var prompts = 0, starts = 0;
      final stream = StreamController<Position>();
      final source = DeviceLocationSource(
        serviceEnabled: () async => true,
        checkPermission: () async => LocationPermission.denied,
        requestPermission: () {
          prompts++;
          return permission.future;
        },
        positionStream: (_) {
          starts++;
          return stream.stream;
        },
      );
      final first = expectLater(
        source.locate(),
        throwsA(failure(LocationFailure.cancelled)),
      );
      await Future<void>.delayed(Duration.zero);
      await source.cancel();
      await first;
      final second = expectLater(
        source.locate(),
        throwsA(failure(LocationFailure.cancelled)),
      );
      await Future<void>.delayed(Duration.zero);
      expect(prompts, 1);
      permission.complete(LocationPermission.whileInUse);
      await Future<void>.delayed(Duration.zero);
      expect(starts, 1);
      await source.cancel();
      await second;
      await stream.close();
    },
  );
  test('native cancel failure prevents another subscription', () async {
    var starts = 0;
    final source = DeviceLocationSource(
      timeout: const Duration(milliseconds: 10),
      serviceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      positionStream: (_) {
        starts++;
        return StreamController<Position>(
          onCancel: () async {
            throw StateError('cancel failed');
          },
        ).stream;
      },
    );
    await expectLater(
      source.locate(),
      throwsA(failure(LocationFailure.unavailable)),
    );
    await expectLater(
      source.locate(),
      throwsA(failure(LocationFailure.unavailable)),
    );
    expect(starts, 1);
  });
  test(
    'locked Android plugin receives listen then cancel on timeout and explicit leave',
    () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      const methods = MethodChannel('flutter.baseflow.com/geolocator_android');
      const events = MethodChannel(
        'flutter.baseflow.com/geolocator_updates_android',
      );
      final calls = <String>[];
      final secondListen = Completer<void>();
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(methods, (call) async {
        if (call.method == 'isLocationServiceEnabled') return true;
        if (call.method == 'checkPermission') return 2;
        throw StateError('unexpected method');
      });
      messenger.setMockMethodCallHandler(events, (call) async {
        calls.add(call.method);
        if (call.method == 'listen' &&
            calls.where((name) => name == 'listen').length == 2) {
          secondListen.complete();
        }
        return null;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(methods, null));
      addTearDown(() => messenger.setMockMethodCallHandler(events, null));
      GeolocatorAndroid.registerWith();
      final source = DeviceLocationSource(
        timeout: const Duration(milliseconds: 200),
      );
      await expectLater(
        source.locate(),
        throwsA(failure(LocationFailure.timeout)),
      );
      await Future<void>.delayed(Duration.zero);
      expect(calls, ['listen', 'cancel']);
      // Explicit cancellation is a separate case from the short timeout.
      // Wait for the native listen handshake instead of racing a 20 ms timer
      // against an event-loop yield on a busy test host.
      final leavingSource = DeviceLocationSource(
        timeout: const Duration(seconds: 5),
      );
      final pending = expectLater(
        leavingSource.locate(),
        throwsA(failure(LocationFailure.cancelled)),
      );
      await secondListen.future;
      await leavingSource.cancel();
      await pending;
      await Future<void>.delayed(Duration.zero);
      expect(calls, ['listen', 'cancel', 'listen', 'cancel']);
    },
  );
}
