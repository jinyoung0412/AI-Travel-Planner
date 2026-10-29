import 'package:flutter/material.dart';

class ServiceRegionDialog extends StatelessWidget {
  const ServiceRegionDialog({super.key});

  static const _brown = Color(0xFF914B33);
  static const _muted = Color(0xFF786A61);

  @override
  Widget build(BuildContext context) => Dialog(
    backgroundColor: const Color(0xFFFFFDFB),
    surfaceTintColor: Colors.transparent,
    insetPadding: const EdgeInsets.all(24),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 390),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Semantics(
              namesRoute: true,
              header: true,
              child: const Text(
                '추천 기준을 바꿀까요?',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.6,
                  color: Color(0xFF302722),
                  height: 1.4,
                ),
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              '현재 위치는 천안·아산 밖이에요.',
              style: TextStyle(fontSize: 14, height: 1.75, color: _muted),
            ),
            const SizedBox(height: 18),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
              decoration: BoxDecoration(
                color: const Color(0xFFF5E8DD),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Row(
                children: [
                  Icon(Icons.location_on_outlined, size: 22, color: _brown),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '추천 기준 위치',
                          style: TextStyle(fontSize: 11, color: _muted),
                        ),
                        SizedBox(height: 2),
                        Text(
                          '천안 중심부',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                            color: _brown,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 25),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              style: FilledButton.styleFrom(
                backgroundColor: _brown,
                foregroundColor: const Color(0xFFFFFDFB),
                minimumSize: const Size(0, 48),
                padding: const EdgeInsets.all(12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(13),
                ),
              ),
              child: const Text('천안으로 추천'),
            ),
            const SizedBox(height: 3),
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              style: TextButton.styleFrom(
                foregroundColor: _muted,
                minimumSize: const Size(0, 48),
              ),
              child: const Text('돌아가기'),
            ),
          ],
        ),
      ),
    ),
  );
}
