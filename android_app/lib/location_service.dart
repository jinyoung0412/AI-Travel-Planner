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
  };
}

abstract class LocationSource {
  Future<LocationFix> locate();
}

class DeviceLocationSource implements LocationSource {
  final Duration timeout;
  final Future<bool> Function() _serviceEnabled;
  final Future<LocationPermission> Function() _checkPermission;
  final Future<LocationPermission> Function() _requestPermission;
  final Future<Position> Function() _position;

  DeviceLocationSource({
    this.timeout = const Duration(seconds: 15),
    Future<bool> Function()? serviceEnabled,
    Future<LocationPermission> Function()? checkPermission,
    Future<LocationPermission> Function()? requestPermission,
    Future<Position> Function()? position,
  }) : _serviceEnabled = serviceEnabled ?? Geolocator.isLocationServiceEnabled,
       _checkPermission = checkPermission ?? Geolocator.checkPermission,
       _requestPermission = requestPermission ?? Geolocator.requestPermission,
       _position =
           position ??
           (() => Geolocator.getCurrentPosition(
             locationSettings: const LocationSettings(
               accuracy: LocationAccuracy.high,
             ),
           ));

  @override
  Future<LocationFix> locate() async {
    try {
      return await _locate().timeout(timeout);
    } on LocationException {
      rethrow;
    } on TimeoutException {
      throw const LocationException(LocationFailure.timeout);
    } catch (_) {
      throw const LocationException(LocationFailure.unavailable);
    }
  }

  Future<LocationFix> _locate() async {
    if (!await _serviceEnabled()) {
      throw const LocationException(LocationFailure.serviceDisabled);
    }
    var permission = await _checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await _requestPermission();
    }
    if (permission == LocationPermission.deniedForever) {
      throw const LocationException(LocationFailure.deniedForever);
    }
    if (permission != LocationPermission.always &&
        permission != LocationPermission.whileInUse) {
      throw const LocationException(LocationFailure.denied);
    }
    final position = await _position();
    if (!position.latitude.isFinite ||
        !position.longitude.isFinite ||
        position.latitude.abs() > 90 ||
        position.longitude.abs() > 180) {
      throw const LocationException(LocationFailure.unavailable);
    }
    return LocationFix(position.latitude, position.longitude);
  }
}
