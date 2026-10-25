import 'dart:async';
import 'package:geolocator/geolocator.dart';

class LocationFix {
  final double lat;
  final double lng;
  const LocationFix(this.lat, this.lng);
}

enum LocationFailure {
  serviceDisabled,
  denied,
  deniedForever,
  timeout,
  unavailable,
  cancelled,
}

class LocationException implements Exception {
  final LocationFailure failure;
  const LocationException(this.failure);
  String get message => switch (failure) {
    LocationFailure.serviceDisabled => '위치 서비스가 꺼져 있어요. 켜거나 지역을 직접 선택해주세요.',
    LocationFailure.denied => '위치 권한이 거부되었어요. 다시 시도하거나 지역을 직접 선택해주세요.',
    LocationFailure.deniedForever => '위치 권한을 설정에서 허용하거나 지역을 직접 선택해주세요.',
    LocationFailure.timeout => '위치 확인 시간이 초과됐어요. 다시 시도하거나 지역을 직접 선택해주세요.',
    LocationFailure.unavailable => '위치를 확인할 수 없어요. 다시 시도하거나 지역을 직접 선택해주세요.',
    LocationFailure.cancelled => '위치 확인을 취소했어요.',
  };
}

abstract class LocationSource {
  Future<LocationFix> locate();
}

/// Optional capability; existing injected LocationSource fakes remain compatible.
abstract class CancellableLocationSource implements LocationSource {
  Future<void> cancel();
}

class DeviceLocationSource implements CancellableLocationSource {
  final Duration timeout;
  final Future<bool> Function() _serviceEnabled;
  final Future<LocationPermission> Function() _checkPermission;
  final Future<LocationPermission> Function() _requestPermission;
  final Stream<Position> Function(LocationSettings) _positions;
  Future<LocationPermission>? _permissionPending;
  _LocationSession? _active;
  int _revision = 0;
  bool _cancelFailed = false;

  DeviceLocationSource({
    this.timeout = const Duration(seconds: 15),
    Future<bool> Function()? serviceEnabled,
    Future<LocationPermission> Function()? checkPermission,
    Future<LocationPermission> Function()? requestPermission,
    Future<Position> Function()? position,
    Stream<Position> Function(LocationSettings)? positionStream,
  }) : assert(position == null || positionStream == null),
       _serviceEnabled = serviceEnabled ?? Geolocator.isLocationServiceEnabled,
       _checkPermission = checkPermission ?? Geolocator.checkPermission,
       _requestPermission = requestPermission ?? Geolocator.requestPermission,
       _positions =
           positionStream ??
           (position != null
               ? ((_) => Stream.fromFuture(position()))
               : ((settings) =>
                     Geolocator.getPositionStream(locationSettings: settings)));

  @override
  Future<void> cancel() async {
    ++_revision;
    await _stopActive();
  }

  Future<void> _stopActive() async {
    final active = _active;
    if (active == null) return;
    await active.finish(failure: LocationFailure.cancelled);
    _cancelFailed = _cancelFailed || active.cancelFailed;
    if (identical(_active, active)) _active = null;
  }

  @override
  Future<LocationFix> locate() async {
    final revision = ++_revision;
    await _stopActive();
    if (revision != _revision) {
      throw const LocationException(LocationFailure.cancelled);
    }
    // A failed native cancel must not be followed by a second subscription.
    if (_cancelFailed || timeout <= Duration.zero) {
      throw const LocationException(LocationFailure.unavailable);
    }
    final active = _LocationSession(timeout);
    _active = active;
    unawaited(_locate(active));
    try {
      return await active.result.future;
    } finally {
      _cancelFailed = _cancelFailed || active.cancelFailed;
      if (revision == _revision && identical(_active, active)) _active = null;
    }
  }

  void _checkActive(_LocationSession active) {
    if (active.closed || !identical(_active, active)) {
      throw const LocationException(LocationFailure.cancelled);
    }
    if (active.remaining <= Duration.zero) {
      throw const LocationException(LocationFailure.timeout);
    }
  }

  Future<LocationPermission> _permission() async {
    // OS permission prompts cannot be dismissed by the plugin. Reuse a pending
    // prompt on retry; the expired session still cannot start a GPS stream.
    final pending = _permissionPending ??= _requestPermission();
    try {
      return await pending;
    } finally {
      if (identical(_permissionPending, pending)) _permissionPending = null;
    }
  }

  Future<void> _locate(_LocationSession active) async {
    try {
      _checkActive(active);
      final enabled = await _serviceEnabled();
      _checkActive(active);
      if (!enabled) {
        throw const LocationException(LocationFailure.serviceDisabled);
      }
      var permission = await _checkPermission();
      _checkActive(active);
      if (permission == LocationPermission.denied) {
        permission = await _permission();
        _checkActive(active);
      }
      if (permission == LocationPermission.deniedForever) {
        throw const LocationException(LocationFailure.deniedForever);
      }
      if (permission != LocationPermission.always &&
          permission != LocationPermission.whileInUse) {
        throw const LocationException(LocationFailure.denied);
      }
      _checkActive(active);
      active.subscription =
          _positions(
            LocationSettings(
              accuracy: LocationAccuracy.high,
              timeLimit: active.remaining,
            ),
          ).listen(
            (position) {
              if (!position.latitude.isFinite ||
                  !position.longitude.isFinite ||
                  position.latitude.abs() > 90 ||
                  position.longitude.abs() > 180) {
                unawaited(active.finish(failure: LocationFailure.unavailable));
              } else {
                unawaited(
                  active.finish(
                    fix: LocationFix(position.latitude, position.longitude),
                  ),
                );
              }
            },
            onError: (Object error) => unawaited(
              active.finish(
                failure: error is TimeoutException
                    ? LocationFailure.timeout
                    : LocationFailure.unavailable,
              ),
            ),
            onDone: () =>
                unawaited(active.finish(failure: LocationFailure.unavailable)),
          );
    } on LocationException catch (error) {
      await active.finish(failure: error.failure);
    } catch (_) {
      await active.finish(failure: LocationFailure.unavailable);
    }
  }
}

class _LocationSession {
  final result = Completer<LocationFix>();
  final Stopwatch _elapsed = Stopwatch()..start();
  final Duration timeout;
  late final Timer _timer;
  StreamSubscription<Position>? subscription;
  Future<void>? _finishing;
  bool closed = false;
  bool cancelFailed = false;
  _LocationSession(this.timeout) {
    _timer = Timer(
      timeout,
      () => unawaited(finish(failure: LocationFailure.timeout)),
    );
  }
  Duration get remaining => timeout - _elapsed.elapsed;

  Future<void> finish({LocationFix? fix, LocationFailure? failure}) {
    if (_finishing != null) return _finishing!;
    closed = true;
    _timer.cancel();
    return _finishing = () async {
      try {
        // Await subscription cleanup before exposing completion/retry. The locked
        // native plugin dispatches event-channel cancel from this cleanup; its
        // OS-level stop completion is not exposed by the public plugin API.
        await subscription?.cancel().timeout(const Duration(seconds: 5));
      } catch (_) {
        cancelFailed = true;
      }
      if (fix != null && !cancelFailed) {
        result.complete(fix);
      } else {
        result.completeError(
          LocationException(
            cancelFailed
                ? LocationFailure.unavailable
                : failure ?? LocationFailure.unavailable,
          ),
        );
      }
    }();
  }
}
