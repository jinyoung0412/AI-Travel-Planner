import 'package:flutter/material.dart';

class ChoiceConditionOption {
  final String id;
  final String scope;
  final String label;
  final bool common;
  const ChoiceConditionOption(
    this.id,
    this.scope,
    this.label, {
    this.common = false,
  });
  String get description {
    final text = label.startsWith('$scope:') ? label : '$scope: $label';
    final description = text.contains('미확인') ? text : '$text 미확인';
    return common && !scope.contains('공통')
        ? '방문 공통 · $description'
        : description;
  }
}

class ChoiceConsentOffer {
  final String planId;
  final List<ChoiceConditionOption> conditions;
  const ChoiceConsentOffer(this.planId, this.conditions);
}

/// Only an explicit selection grants permission; closing the dialog grants none.
Future<List<String>?> chooseUnverifiedConditions(
  BuildContext context,
  ChoiceConsentOffer offer,
) => showDialog<List<String>>(
  context: context,
  builder: (context) {
    final selected = <String>{};
    return StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        title: const Text('미확인 상태로 이 대안도 볼까요?'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('선택한 조건은 확인되지 않은 상태로 포함해요.'),
              for (final condition in offer.conditions)
                CheckboxListTile(
                  key: ValueKey(condition.id),
                  contentPadding: EdgeInsets.zero,
                  title: Text(condition.description),
                  value: selected.contains(condition.id),
                  onChanged: (value) => setState(() {
                    if (value == true) {
                      selected.add(condition.id);
                    } else {
                      selected.remove(condition.id);
                    }
                  }),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: selected.isEmpty
                ? null
                : () => Navigator.pop(context, selected.toList()..sort()),
            child: const Text('선택한 미확인 대안도 보기'),
          ),
        ],
      ),
    );
  },
);

/// Runs once per tap sequence and leaves existing results visible on failure.
class ChoiceOfferNotice extends StatefulWidget {
  final ChoiceConsentOffer? offer;
  final Future<void> Function(BuildContext)? onInclude;
  const ChoiceOfferNotice({super.key, this.offer, this.onInclude});
  @override
  State<ChoiceOfferNotice> createState() => _ChoiceOfferNoticeState();
}

class _ChoiceOfferNoticeState extends State<ChoiceOfferNotice> {
  bool _busy = false;
  @override
  Widget build(BuildContext context) {
    final offer = widget.offer;
    if (offer == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '다른 대안에는 미확인 조건이 있어요. ${offer.conditions.map((c) => c.description).join(', ')}',
          ),
          TextButton(
            onPressed: _busy || widget.onInclude == null
                ? null
                : () async {
                    setState(() => _busy = true);
                    try {
                      await widget.onInclude!(context);
                    } finally {
                      if (mounted) setState(() => _busy = false);
                    }
                  },
            child: Text(_busy ? '확인 중…' : '미확인 대안도 보기'),
          ),
        ],
      ),
    );
  }
}

/// Unknown or malformed contracts never create a consent action.
ChoiceConsentOffer? readChoiceConsentOffer(
  Map<String, dynamic> metadata, {
  Map<String, dynamic>? travelRequest,
}) {
  bool text(Object? value, int max) =>
      value is String && value.trim().isNotEmpty && value.length <= max;
  if (metadata['choice_contract_version'] != 1) return null;
  final offer = metadata['consent_offer'];
  if (offer is! Map || !text(offer['plan_id'], 64)) return null;
  final alternatives = offer['alternatives'];
  if (alternatives is! List ||
      alternatives.isEmpty ||
      alternatives.length > 15) {
    return null;
  }
  final canonicalStages = travelRequest?['stages'];
  if (travelRequest != null) {
    if (travelRequest['plan_id'] != offer['plan_id'] ||
        canonicalStages is! List ||
        canonicalStages.isEmpty ||
        canonicalStages.length > 5) {
      return null;
    }
    for (var i = 0; i < canonicalStages.length; i++) {
      if (canonicalStages[i] is! Map || canonicalStages[i]['id'] != 's${i + 1}') {
        return null;
      }
    }
  }
  final multipleStages = canonicalStages is List
      ? canonicalStages.length > 1
      : alternatives.whereType<Map>().map((a) => a['stage_id']).toSet().length >
            1;
  final ids = <String, ChoiceConditionOption>{};
  final signatures = <String, String>{};
  final scopes = <String, Set<String>>{};
  for (final alternative in alternatives) {
    if (alternative is! Map ||
        !text(alternative['stage_id'], 64) ||
        !text(alternative['alternative_id'], 64) ||
        !text(alternative['label'], 200) ||
        alternative['reason'] != 'required_condition_unknown' ||
        alternative['candidate_count'] is! int ||
        alternative['candidate_count'] <= 0) {
      return null;
    }
    final stageId = alternative['stage_id'] as String;
    final alternativeId = alternative['alternative_id'] as String;
    final stageMatch = RegExp(r'^s([1-5])$').firstMatch(stageId);
    if (stageMatch == null ||
        !RegExp(
          '^${RegExp.escape(stageId)}\\.a[1-3]\$',
        ).hasMatch(alternativeId)) {
      return null;
    }
    final ordinal = int.parse(stageMatch.group(1)!);
    Map? canonicalStage;
    Map? canonicalAlternative;
    if (canonicalStages is List) {
      if (ordinal > canonicalStages.length) return null;
      canonicalStage = canonicalStages[ordinal - 1] as Map;
      final choices = canonicalStage['alternatives'];
      if (choices is List && choices.isNotEmpty) {
        final matching = choices
            .whereType<Map>()
            .where((a) => a['id'] == alternativeId)
            .toList();
        if (matching.length != 1) return null;
        canonicalAlternative = matching.single;
      } else if (alternativeId != '$stageId.a1') {
        return null;
      }
    }
    final categories =
        (canonicalAlternative ?? canonicalStage)?['category_filters'];
    if (canonicalStage != null &&
        (categories is! List ||
            categories.isEmpty ||
            !categories.every((v) => v is String && v.isNotEmpty))) {
      return null;
    }
    final label =
        categories is List &&
            categories.isNotEmpty &&
            categories.every((v) => v is String && v.isNotEmpty)
        ? categories.join(' / ')
        : alternative['label'] as String;
    final conditions = alternative['conditions'];
    if (conditions is! List || conditions.isEmpty || conditions.length > 25) {
      return null;
    }
    for (final c in conditions) {
      if (c is! Map ||
          !text(c['id'], 64) ||
          !text(c['field'], 64) ||
          !text(c['label'], 300) ||
          !text(c['quote'], 300) ||
          c['status'] != 'unknown' ||
          c['required'] != true ||
          c['value'] is! bool) {
        return null;
      }
      final span = c['source_span'];
      if (span != null &&
          (span is! List ||
              span.length != 2 ||
              span.any((v) => v is! int) ||
              span[0] < 0 ||
              span[1] <= span[0])) {
        return null;
      }
      final id = c['id'] as String;
      final common = RegExp(
        '^${RegExp.escape(stageId)}\\.c(?:[1-9]|1[0-9]|2[0-5])\$',
      ).hasMatch(id);
      final branch = RegExp(
        '^${RegExp.escape(alternativeId)}\\.c(?:[1-9]|1[0-9]|2[0-5])\$',
      ).hasMatch(id);
      if (!common && !branch) return null;
      Map? declared;
      if (canonicalStage != null) {
        final declarations = (common
            ? canonicalStage
            : canonicalAlternative)?['conditions'];
        if (declarations is! List) return null;
        final matching = declarations
            .whereType<Map>()
            .where((atom) => atom['id'] == id)
            .toList();
        if (matching.length != 1) return null;
        declared = matching.single;
        for (final field in ['field', 'value', 'required', 'quote']) {
          if (c[field] != declared[field]) return null;
        }
        final declaredSpan = declared['source_span'];
        if (declaredSpan != null &&
            (declaredSpan is! List ||
                declaredSpan.length != 2 ||
                declaredSpan.any((v) => v is! int) ||
                span is! List ||
                span.length != 2 ||
                span[0] != declaredSpan[0] ||
                span[1] != declaredSpan[1])) {
          return null;
        }
      }

      final signature =
          '${alternative['stage_id']}|${c['field']}|${c['value']}|${c['quote']}|${c['source_span']}';
      if (signatures.containsKey(id) && signatures[id] != signature) {
        return null;
      }
      signatures[id] = signature;
      final commonCategories = canonicalStage?['category_filters'];
      final scope =
          common && commonCategories is List && commonCategories.isNotEmpty
          ? '$ordinal번째 방문 공통 · ${commonCategories.join(' / ')} (모든 대안)'
          : '${multipleStages || ordinal > 1 ? '$ordinal번째 방문 · ' : ''}$label';
      scopes.putIfAbsent(id, () => <String>{}).add(scope);
      const fields = {
        'indoor': '실내',
        'outdoor': '야외',
        'outdoor_seating': '야외 좌석',
        'open_now': '현재 영업',
        'accessible': '이동 약자 접근성',
        'quiet': '조용함',
        'lively': '활기찬 분위기',
        'romantic': '로맨틱함',
        'cool': '시원함',
        'relaxed': '여유로움',
      };
      final conditionLabel = declared == null
          ? c['label'] as String
          : '${fields[declared['field']] ?? declared['quote']}${declared['value'] == false ? ' 아님' : ''} 여부 미확인';
      ids[id] = ChoiceConditionOption(id, '', conditionLabel);
    }
  }
  if (ids.isEmpty || ids.length > 25) return null;
  return ChoiceConsentOffer(
    offer['plan_id'] as String,
    List.unmodifiable([
      for (final entry in ids.entries)
        ChoiceConditionOption(
          entry.key,
          scopes[entry.key]!.join(' / '),
          entry.value.label,
          common: RegExp(r'^s[1-5]\.c[0-9]+$').hasMatch(entry.key),
        ),
    ]),
  );
}

/// Public historical attribution only; this widget never grants consent.
class ChoiceConditionNotice extends StatelessWidget {
  final Map<String, dynamic> place;
  const ChoiceConditionNotice({super.key, required this.place});
  @override
  Widget build(BuildContext context) {
    final explanation = place['travel_explanation'];
    if (explanation is! Map ||
        explanation['alternative_id'] is! String ||
        explanation['alternative_label'] is! String) {
      return const SizedBox.shrink();
    }
    final unknown = explanation['unverified_conditions'];
    final labels = unknown is List
        ? unknown.whereType<String>().where((s) => s.isNotEmpty).toList()
        : <String>[];
    final reason = explanation['reason'];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('선택 대안: ${explanation['alternative_label']}'),
          if (reason is String && reason.isNotEmpty) Text(reason),
          if (labels.isNotEmpty) Text('확인 필요: ${labels.join(', ')}'),
          if (labels.isNotEmpty && explanation['consent_used'] == true)
            const Text('미확인 조건에 동의하고 포함한 결과예요.'),
        ],
      ),
    );
  }
}
