import 'api_service.dart';

class RecommendationRequest {
  final String mode;
  final String userText;
  final String transport;
  final String region;
  final double lat;
  final double lng;
  final List<String> tags;
  final int count;
  final List<String> slotTypes;

  RecommendationRequest({
    required this.mode,
    required this.userText,
    required this.transport,
    required this.region,
    required this.lat,
    required this.lng,
    required List<String> tags,
    required this.count,
    required List<String> slotTypes,
  }) : tags = List.unmodifiable(tags),
       slotTypes = List.unmodifiable(slotTypes);
}

abstract class RecommendationSource {
  Future<List<String>> suggestTags(String text);
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request);
}

/// Keeps ApiService's public named arguments and response envelope unchanged.
class ApiRecommendationSource implements RecommendationSource {
  const ApiRecommendationSource();
  @override
  Future<List<String>> suggestTags(String text) =>
      ApiService.suggestTags(userText: text);

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) =>
      request.mode == 'spot'
      ? ApiService.getSpotRecommendation(
          userText: request.userText,
          transport: request.transport,
          region: request.region,
          userLat: request.lat,
          userLng: request.lng,
          personaTags: request.tags,
          count: request.count,
        )
      : ApiService.getCourseRecommendation(
          transport: request.transport,
          region: request.region,
          userLat: request.lat,
          userLng: request.lng,
          personaTags: request.tags,
          count: request.count,
          spotCount: request.slotTypes.length,
          slotTypes: request.slotTypes,
        );
}
