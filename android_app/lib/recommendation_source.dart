import 'dart:math';
import 'api_service.dart';
import 'network/request_cancellation.dart';

class RecommendationRequest {
  static final Random _random = Random.secure();
  static int? _lastSeed;
  static int _newSeed() {
    var value = _random.nextInt(2147483648);
    if (value == _lastSeed) value = (value + 1) % 2147483648;
    _lastSeed = value;
    return value;
  }

  final String mode;
  final String userText;
  final String transport;
  final String region;
  final double lat;
  final double lng;
  final List<String> tags;
  final int count;
  final List<String> slotTypes;
  final bool naturalPlan;
  final String? intentToken;
  final String? activityChoice;
  final String? clarificationToken;
  final bool acceptUnverified;
  final RequestCancellation? cancellation;
  final int seed;
  final List<String> recentPlaceIds;

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
    this.naturalPlan = false,
    this.intentToken,
    this.activityChoice,
    this.clarificationToken,
    this.acceptUnverified = false,
    this.cancellation,
    int? seed,
    List<String> recentPlaceIds = const [],
  }) : recentPlaceIds = List.unmodifiable(
         recentPlaceIds
             .map((id) => id.trim())
             .where((id) => id.isNotEmpty && id.length <= 200)
             .toSet()
             .take(100),
       ),
       tags = List.unmodifiable(tags),
       seed = seed ?? _newSeed(),
       slotTypes = List.unmodifiable(slotTypes);

  Map<String, dynamic> get selectionFields => {
    'seed': seed,
    'randomize': true,
    if (recentPlaceIds.isNotEmpty) 'recent_place_ids': recentPlaceIds,
  };

  Map<String, dynamic> get intentFields => {
    ...selectionFields,
    'intent_version': 1,
    'plan_mode': naturalPlan ? 'natural' : 'manual',
    if (intentToken != null) 'intent_token': intentToken,
    if (activityChoice != null) 'activity_choice': activityChoice,
    'accept_unverified': acceptUnverified,
  };

  Map<String, dynamic> get interpretationBody => {
    'mode': mode,
    'user_text': userText,
    'region': region,
    'transport': transport,
    'user_lat': lat,
    'user_lng': lng,
    'persona_tags': tags,
    'count': count,
    if (mode == 'course')
      'spot_count': slotTypes.isEmpty ? 3 : slotTypes.length,
    if (mode == 'course') 'slot_types': slotTypes,
    ...intentFields,
    if (clarificationToken != null) 'clarification_token': clarificationToken,
  };

  RecommendationRequest clarified({
    required String activity,
    required String token,
  }) => RecommendationRequest(
    mode: mode,
    userText: userText,
    transport: transport,
    region: region,
    lat: lat,
    lng: lng,
    tags: tags,
    count: count,
    slotTypes: slotTypes,
    naturalPlan: naturalPlan,
    cancellation: cancellation,
    seed: seed,
    recentPlaceIds: recentPlaceIds,
    activityChoice: activity,
    clarificationToken: token,
  );

  RecommendationRequest reviewed({
    required String token,
    String? targetMode,
    int? targetCount,
    bool unverified = false,
  }) {
    // A sentence with several visits can be approved as one natural course.
    // This conversion has no course-screen slot selection and must match the
    // controls signed by /travel/interpret, rather than the manual UI default.
    final switchingToCourse = mode == 'spot' && targetMode == 'course';
    return RecommendationRequest(
      mode: targetMode ?? mode,
      userText: userText,
      transport: transport,
      region: region,
      lat: lat,
      lng: lng,
      tags: tags,
      count: targetCount ?? (switchingToCourse ? 1 : count),
      slotTypes: switchingToCourse ? const [] : slotTypes,
      naturalPlan: switchingToCourse || naturalPlan,
      intentToken: token,
      activityChoice: activityChoice,
      acceptUnverified: unverified,
      cancellation: cancellation,
      seed: seed,
      recentPlaceIds: recentPlaceIds,
    );
  }
}

abstract class RecommendationSource {
  Future<List<String>> suggestTags(String text);
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request);
}

abstract class IntentRecommendationSource implements RecommendationSource {
  Future<Map<String, dynamic>?> interpret(RecommendationRequest request);
}

/// Keeps ApiService's public named arguments and response envelope unchanged.
class ApiRecommendationSource implements IntentRecommendationSource {
  const ApiRecommendationSource();
  @override
  Future<List<String>> suggestTags(String text) =>
      ApiService.suggestTags(userText: text);

  @override
  Future<Map<String, dynamic>> interpret(RecommendationRequest request) =>
      ApiService.interpretTravel(
        request.interpretationBody,
        cancellation: request.cancellation,
      );

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
          intentFields: request.userText.isEmpty
              ? request.selectionFields
              : request.intentFields,
          cancellation: request.cancellation,
        )
      : ApiService.getCourseRecommendation(
          transport: request.transport,
          region: request.region,
          userLat: request.lat,
          userLng: request.lng,
          personaTags: request.tags,
          count: request.count,
          spotCount: request.slotTypes.isEmpty ? 3 : request.slotTypes.length,
          slotTypes: request.slotTypes,
          userText: request.userText,
          intentFields: request.userText.isEmpty
              ? request.selectionFields
              : request.intentFields,
          cancellation: request.cancellation,
        );
}
