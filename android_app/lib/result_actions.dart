import 'package:flutter/material.dart';

enum ResultAction { edit, recommendAgain }

/// Returns to the existing input screen; it owns the request and consent flow.
class ResultActions extends StatelessWidget {
  final bool quiet;
  const ResultActions({super.key, this.quiet = false});

  @override
  Widget build(BuildContext context) => SafeArea(
    top: false,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: quiet
          ? Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextButton.icon(
                  onPressed: () => Navigator.pop(context, ResultAction.edit),
                  icon: const Icon(Icons.tune, size: 18),
                  label: const Text('조건 수정'),
                  style: TextButton.styleFrom(
                    foregroundColor: const Color(0xFF914B33),
                    backgroundColor: const Color(0xFFF5E8DD),
                    minimumSize: const Size(0, 48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(13),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                FilledButton.icon(
                  onPressed: () =>
                      Navigator.pop(context, ResultAction.recommendAgain),
                  icon: const Icon(Icons.refresh, size: 18),
                  label: const Text('같은 조건으로 새 추천'),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF914B33),
                    minimumSize: const Size(0, 48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(13),
                    ),
                  ),
                ),
              ],
            )
          : Wrap(
              spacing: 12,
              alignment: WrapAlignment.center,
              children: [
                OutlinedButton.icon(
                  onPressed: () => Navigator.pop(context, ResultAction.edit),
                  icon: const Icon(Icons.tune, size: 18),
                  label: const Text('조건 수정'),
                ),
                FilledButton.icon(
                  onPressed: () =>
                      Navigator.pop(context, ResultAction.recommendAgain),
                  icon: const Icon(Icons.refresh, size: 18),
                  label: const Text('같은 조건으로 새 추천'),
                ),
              ],
            ),
    ),
  );
}
