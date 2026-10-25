/// Safe, structured failure without exposing provider response text to the UI.
/// The `List<String>` success contract stays compatible with existing sources.
class TagSuggestionException implements Exception {
  final String reason;
  const TagSuggestionException(this.reason);

  String get message => switch (reason) {
    'network_unavailable' => '서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해주세요.',
    'network_timeout' ||
    'upstream_timeout' => '태그 응답 시간이 초과됐어요. 잠시 후 다시 시도해주세요.',
    'tags_unavailable' ||
    'upstream_unavailable' => 'AI 태그 서비스를 이용할 수 없어요. 잠시 후 다시 시도하거나 직접 선택해주세요.',
    'invalid_response' ||
    'invalid_upstream_response' => '태그 응답을 확인하지 못했어요. 다시 시도하거나 직접 선택해주세요.',
    'invalid_request' => '입력 내용을 확인하고 다시 시도해주세요.',
    _ => '태그를 가져오지 못했어요. 잠시 후 다시 시도하거나 직접 선택해주세요.',
  };
}
