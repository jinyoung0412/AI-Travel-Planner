import 'network/api_client.dart';
import 'network/request_cancellation.dart';

/// Static compatibility facade used by the app's existing screens.
class ApiService {
  static const String baseUrl = defaultApiBaseUrl;
  static final ApiClient _client = ApiClient();

  static Future<Map<String, dynamic>> interpretTravel(
    Map<String, dynamic> body, {
    RequestCancellation? cancellation,
  }) => _client.post('/travel/interpret', body, cancellation: cancellation);

  static Future<List<String>> suggestTags({required String userText}) =>
      _client.suggestTags(userText: userText, throwOnError: true);

  static Future<Map<String, dynamic>?> getSpotRecommendation({
    required String userText,
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
    Map<String, dynamic> intentFields = const {},
    RequestCancellation? cancellation,
  }) => _client.getSpotRecommendation(
    userText: userText,
    transport: transport,
    region: region,
    userLat: userLat,
    userLng: userLng,
    personaTags: personaTags,
    count: count,
    intentFields: intentFields,
    cancellation: cancellation,
  );

  static Future<Map<String, dynamic>?> getCourseRecommendation({
    required String transport,
    required String region,
    required double userLat,
    required double userLng,
    required List<String> personaTags,
    required int count,
    int spotCount = 5,
    List<String> slotTypes = const [],
    String userText = '',
    Map<String, dynamic> intentFields = const {},
    RequestCancellation? cancellation,
  }) => _client.getCourseRecommendation(
    transport: transport,
    region: region,
    userLat: userLat,
    userLng: userLng,
    personaTags: personaTags,
    count: count,
    spotCount: spotCount,
    slotTypes: slotTypes,
    userText: userText,
    intentFields: intentFields,
    cancellation: cancellation,
  );

  static Future<String?> getKakaoPlaceUrl({
    required String name,
    required double lat,
    required double lng,
    String address = '',
  }) => _client.getKakaoPlaceUrl(
    name: name,
    lat: lat,
    lng: lng,
    address: address,
  );
}
