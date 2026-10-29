import 'package:flutter/material.dart';
import 'local_storage_service.dart';

bool samePlaceComposition(
  List<Map<String, dynamic>> first,
  List<Map<String, dynamic>> second, {
  bool ordered = false,
}) {
  if (first.isEmpty || first.length != second.length) return false;
  if (ordered) {
    return List.generate(
      first.length,
      (i) => i,
    ).every((i) => LocalStorageService.samePlace(first[i], second[i]));
  }
  final remaining = List<Map<String, dynamic>>.from(second);
  for (final place in first) {
    final index = remaining.indexWhere(
      (other) => LocalStorageService.samePlace(place, other),
    );
    if (index < 0) return false;
    remaining.removeAt(index);
  }
  return true;
}

bool sameCourseComposition(
  List<List<Map<String, dynamic>>> first,
  List<List<Map<String, dynamic>>> second,
) {
  if (first.isEmpty || first.length != second.length) return false;
  final remaining = List<List<Map<String, dynamic>>>.from(second);
  for (final course in first) {
    final index = remaining.indexWhere(
      (other) => samePlaceComposition(course, other, ordered: true),
    );
    if (index < 0) return false;
    remaining.removeAt(index);
  }
  return true;
}

class RepeatedResultNotice extends StatelessWidget {
  const RepeatedResultNotice({super.key});
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF3E0),
      borderRadius: BorderRadius.circular(10),
    ),
    child: const Text(
      '이전 추천과 같은 구성이에요.',
      style: TextStyle(fontSize: 13, color: Color(0xFF795548)),
    ),
  );
}
