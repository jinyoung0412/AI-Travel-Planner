import 'package:flutter/material.dart';

/// Choosing a tile is local; only the explicit recommendation action submits it.
class ActivityChoiceDialog extends StatefulWidget {
  const ActivityChoiceDialog({super.key, required this.options});

  final List<Map<String, dynamic>> options;

  @override
  State<ActivityChoiceDialog> createState() => _ActivityChoiceDialogState();
}

class _ActivityChoiceDialogState extends State<ActivityChoiceDialog> {
  String? _selected;
  static const _brown = Color(0xFF914B33);
  static const _ink = Color(0xFF28231F);
  static const _labels = {
    '음식': '식사',
    '카페': '카페·디저트',
    '자연·산책': '산책·자연',
    '문화·역사': '전시·문화',
    '체험': '체험·만들기',
    '실내 오락': '실내 놀거리',
  };
  static const _icons = {
    '음식': Icons.restaurant_outlined,
    '카페': Icons.coffee_outlined,
    '자연·산책': Icons.park_outlined,
    '문화·역사': Icons.image_outlined,
    '체험': Icons.palette_outlined,
    '실내 오락': Icons.sports_esports_outlined,
  };

  String _label(Map<String, dynamic> option) =>
      _labels[option['value']] ?? '${option['label']}';

  @override
  Widget build(BuildContext context) {
    final selectedLabel = _selected == null
        ? null
        : _label(widget.options.firstWhere((o) => o['value'] == _selected));
    return Dialog(
      backgroundColor: const Color(0xFFFFF8F3),
      surfaceTintColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 390),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(22),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Semantics(
                      namesRoute: true,
                      header: true,
                      child: const Text(
                        '어떤 활동을 원하세요?',
                        style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.w600,
                          color: _ink,
                          letterSpacing: -0.7,
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: '선택창 닫기',
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close, size: 20),
                    color: const Color(0xFF7B6B60),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns =
                      constraints.maxWidth >= 250 &&
                          MediaQuery.textScalerOf(context).scale(14) <= 19
                      ? 2
                      : 1;
                  final width =
                      (constraints.maxWidth - (columns - 1) * 10) / columns;
                  return Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      for (final option in widget.options)
                        SizedBox(
                          width: width,
                          child: Semantics(
                            selected: _selected == option['value'],
                            child: OutlinedButton(
                              onPressed: () => setState(
                                () => _selected = option['value'] as String,
                              ),
                              style: OutlinedButton.styleFrom(
                                minimumSize: const Size(0, 90),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 14,
                                ),
                                foregroundColor: _ink,
                                backgroundColor: _selected == option['value']
                                    ? const Color(0xFFF8E9E2)
                                    : const Color(0xFFFFFDFB),
                                side: BorderSide(
                                  color: _selected == option['value']
                                      ? _brown
                                      : const Color(0xFFE8D7CC),
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(15),
                                ),
                              ),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    _icons[option['value']] ??
                                        Icons.explore_outlined,
                                    color: _brown,
                                    size: 22,
                                  ),
                                  const SizedBox(height: 10),
                                  Text(
                                    _label(option),
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _selected == null
                    ? null
                    : () => Navigator.pop(context, _selected),
                style: FilledButton.styleFrom(
                  backgroundColor: _brown,
                  foregroundColor: const Color(0xFFFFFAF7),
                  disabledBackgroundColor: const Color(0xFFEADED5),
                  disabledForegroundColor: const Color(0xFF89776A),
                  minimumSize: const Size(0, 48),
                  padding: const EdgeInsets.all(12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(13),
                  ),
                ),
                child: Text(
                  selectedLabel == null ? '활동을 선택해 주세요' : '$selectedLabel 추천받기',
                ),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => Navigator.pop(context),
                style: TextButton.styleFrom(
                  foregroundColor: const Color(0xFF78685C),
                  minimumSize: const Size(0, 48),
                ),
                child: const Text('입력한 문장 수정', style: TextStyle(fontSize: 13)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
