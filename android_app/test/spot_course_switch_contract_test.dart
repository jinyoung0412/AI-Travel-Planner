import 'dart:convert';
import 'dart:io';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _fingerprintKeys = [
  'user_text',
  'region',
  'transport',
  'user_lat',
  'user_lng',
  'count',
  'persona_tags',
  'plan_mode',
  'spot_count',
  'slot_types',
  'seed',
  'randomize',
  'intent_version',
  'activity_choice',
];
dynamic _sorted(dynamic value) {
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort();
    return {for (final key in keys) key: _sorted(value[key])};
  }
  if (value is List) return value.map(_sorted).toList();
  return value;
}

String _fingerprint(Map<String, dynamic> body) => sha256
    .convert(
      utf8.encode(
        jsonEncode(
          _sorted({
            'mode': 'course',
            for (final key in _fingerprintKeys) key: body[key],
          }),
        ),
      ),
    )
    .toString();

void main() {
  test(
    'real API adapter serializes signed natural-course controls after spot conversion',
    () async {
      final requests = <Map<String, dynamic>>[];
      final evidence = <Map<String, dynamic>>[];
      final client = MockClient((request) async {
        expect(request.url.path, '/recommend/course');
        requests.add(jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response(jsonEncode({'courses': [], 'metadata': {}}), 200);
      });
      await http.runWithClient(() async {
        for (final count in [3, 5, 7, 10]) {
          final initial = RecommendationRequest(
            mode: 'spot',
            userText: '친구와 카페 갔다가 공원 산책',
            transport: '대중교통',
            region: '천안',
            lat: 36.8013,
            lng: 127.13587,
            tags: const ['친구와'],
            count: count,
            slotTypes: const [],
            seed: 24680 + count,
            recentPlaceIds: const ['fixture:old'],
          );
          // app.interpret_travel signs exactly these controls for an approved
          // multi-stage spot request, independent of the initial spot count.
          final signedControls = <String, dynamic>{
            ...initial.interpretationBody,
            'mode': 'course',
            'count': 1,
            'spot_count': 3,
            'slot_types': <String>[],
            'plan_mode': 'natural',
          };
          final reviewed = initial.reviewed(
            token: 'fixture-not-a-real-token',
            targetMode: 'course',
            targetCount: 1,
          );
          await const ApiRecommendationSource().recommend(reviewed);
          final wire = requests.last;
          expect(wire['count'], 1);
          expect(wire['spot_count'], 3);
          expect(wire['slot_types'], isEmpty);
          expect(wire['plan_mode'], 'natural');
          expect(_fingerprint(wire), _fingerprint(signedControls));
          expect(wire['seed'], initial.seed);
          expect(wire['recent_place_ids'], ['fixture:old']);
          final relaxed = reviewed.reviewed(
            token: 'fixture-not-a-real-token',
            unverified: true,
          );
          await const ApiRecommendationSource().recommend(relaxed);
          expect(requests.last['accept_unverified'], true);
          expect(_fingerprint(requests.last), _fingerprint(signedControls));
          evidence.add({
            'initial_count': count,
            'interpretation_body': initial.interpretationBody,
            'course_wire_without_token': {...wire}..remove('intent_token'),
            'signed_controls_fingerprint': _fingerprint(signedControls),
            'wire_fingerprint': _fingerprint(wire),
          });
        }
      }, () => client);
      expect(requests.length, 8);
      final output = Platform.environment['F2_WIRE_EVIDENCE'];
      if (output != null) {
        File(output).writeAsStringSync(
          const JsonEncoder.withIndent('  ').convert(evidence),
        );
      }
      client.close();
    },
  );

  test('course-screen manual order survives review without conversion', () {
    final request = RecommendationRequest(
      mode: 'course',
      userText: '100일 데이트',
      transport: '차',
      region: '천안',
      lat: 36.8,
      lng: 127.1,
      tags: const ['연인과'],
      count: 3,
      slotTypes: const ['음식', '체험', '카페'],
    );
    final reviewed = request.reviewed(
      token: 'manual',
      targetMode: 'course',
      targetCount: 3,
    );
    expect(reviewed.naturalPlan, false);
    expect(reviewed.slotTypes, request.slotTypes);
    expect(reviewed.count, 3);
    expect(reviewed.interpretationBody['spot_count'], 3);
  });
}
