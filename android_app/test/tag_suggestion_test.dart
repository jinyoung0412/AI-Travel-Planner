import 'dart:async';
import 'dart:convert';

import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/network/tag_suggestion_exception.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  http.Response response(Object body, [int status = 200]) => http.Response(
    jsonEncode(body),
    status,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );

  Matcher failure(String reason) => isA<TagSuggestionException>()
      .having((error) => error.reason, 'reason', reason)
      .having(
        (error) => error.message,
        'safe message',
        isNot(contains('private')),
      );

  test(
    'strict and legacy tag success preserve list contract including empty',
    () async {
      for (final wrapped in [true, false]) {
        for (final tags in [
          <String>[],
          ['친구와', '친구와', '조용한'],
        ]) {
          final client = ApiClient(
            client: MockClient(
              (_) async => response(
                wrapped
                    ? {
                        'success': true,
                        'data': {'tags': tags},
                      }
                    : {'tags': tags},
              ),
            ),
          );
          addTearDown(client.close);
          expect(
            await client.suggestTags(userText: '추천', throwOnError: true),
            tags.toSet().toList(),
          );
          expect(
            await client.suggestTags(userText: '추천'),
            tags.toSet().toList(),
          );
        }
      }
    },
  );

  test(
    'provider gateway timeout and invalid request retain safe reasons',
    () async {
      for (final entry in {
        'tags_unavailable': 503,
        'upstream_unavailable': 502,
        'upstream_timeout': 504,
        'invalid_upstream_response': 502,
        'invalid_request': 400,
      }.entries) {
        for (final wrapped in [true, false]) {
          final error = {'error': 'private provider body', 'reason': entry.key};
          final client = ApiClient(
            client: MockClient(
              (_) async => response(
                wrapped ? {'success': false, 'error': error} : error,
                entry.value,
              ),
            ),
          );
          addTearDown(client.close);
          await expectLater(
            client.suggestTags(userText: '추천', throwOnError: true),
            throwsA(failure(entry.key)),
          );
          expect(await client.suggestTags(userText: '추천'), isEmpty);
        }
      }
    },
  );

  test(
    'malformed tags and JSON fail instead of becoming valid zero tags',
    () async {
      for (final body in [
        '{',
        jsonEncode({
          'tags': [3],
        }),
        jsonEncode({'tags': 'bad'}),
        jsonEncode({'data': []}),
        jsonEncode({'success': true}),
      ]) {
        final client = ApiClient(
          client: MockClient((_) async => http.Response(body, 200)),
        );
        addTearDown(client.close);
        await expectLater(
          client.suggestTags(userText: '추천', throwOnError: true),
          throwsA(failure('invalid_response')),
        );
      }
    },
  );

  test(
    'network failures and deadline differ from empty success; blank stays local',
    () async {
      final offline = ApiClient(
        client: MockClient((_) async => throw http.ClientException('private')),
      );
      final hanging = ApiClient(
        timeout: const Duration(milliseconds: 5),
        client: MockClient((_) => Completer<http.Response>().future),
      );
      addTearDown(offline.close);
      addTearDown(hanging.close);
      await expectLater(
        offline.suggestTags(userText: '추천', throwOnError: true),
        throwsA(failure('network_unavailable')),
      );
      await expectLater(
        hanging.suggestTags(userText: '추천', throwOnError: true),
        throwsA(failure('network_timeout')),
      );
      expect(
        await offline.suggestTags(userText: '  ', throwOnError: true),
        isEmpty,
      );
    },
  );
}
