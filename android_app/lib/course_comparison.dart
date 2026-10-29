import 'package:flutter/material.dart';
import 'travel_data.dart';

/// Compare visit order and existing estimates, then confirm one course.
class CourseComparison extends StatefulWidget {
  final List<List<Map<String, dynamic>>> courses;
  final List<Map<String, dynamic>?> metrics;
  final int selected;

  const CourseComparison({
    super.key,
    required this.courses,
    required this.metrics,
    required this.selected,
  });

  @override
  State<CourseComparison> createState() => _CourseComparisonState();
}

class _CourseComparisonState extends State<CourseComparison> {
  static const _brown = Color(0xFF914B33);
  static const _ink = Color(0xFF302722);
  static const _muted = Color(0xFF796C62);
  int _pending = 0;

  @override
  void initState() {
    super.initState();
    _pending = _validSelection(widget.selected);
  }

  int _validSelection(int index) =>
      index >= 0 && index < widget.courses.length ? index : 0;

  @override
  void didUpdateWidget(CourseComparison oldWidget) {
    super.didUpdateWidget(oldWidget);
    _pending = _validSelection(
      oldWidget.selected != widget.selected ? widget.selected : _pending,
    );
  }

  double? _distance(int index) {
    final places = widget.courses[index];
    final value = index < widget.metrics.length
        ? finiteNumber(widget.metrics[index]?['estimated_distance_km'])
        : null;
    if (places.isEmpty ||
        value == null ||
        value < 0 ||
        places.any((p) => !PlaceData.fromJson(p).coordinateDistanceAllowed)) {
      return null;
    }
    return value;
  }

  String _displayName(Map<String, dynamic> place) {
    final name = PlaceData.fromJson(place).name;
    const suffix = '근린공원';
    return name.endsWith('$suffix$suffix')
        ? name.substring(0, name.length - suffix.length)
        : name;
  }

  Widget _card(int index) {
    final chosen = index == _pending;
    final distance = _distance(index);
    final places = widget.courses[index];
    return Semantics(
      selected: chosen,
      child: Material(
        color: chosen ? const Color(0xFFFBF0E7) : const Color(0xFFFFFDFB),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: chosen ? _brown : const Color(0xFFEADFD6)),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          key: ValueKey('comparison-course-$index'),
          onTap: () => setState(() => _pending = index),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 12,
                  runSpacing: 4,
                  children: [
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '코스 ${index + 1}',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: _ink,
                          ),
                        ),
                        if (chosen) ...[
                          const SizedBox(width: 7),
                          const Icon(Icons.check, size: 16, color: _brown),
                        ],
                      ],
                    ),
                    if (distance != null)
                      Text.rich(
                        TextSpan(
                          text: distance.toStringAsFixed(1),
                          style: const TextStyle(
                            color: _brown,
                            fontSize: 22,
                            fontWeight: FontWeight.w500,
                          ),
                          children: const [
                            TextSpan(
                              text: ' km',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
                if (places.isNotEmpty) const SizedBox(height: 8),
                for (final entry in places.asMap().entries)
                  Padding(
                    padding: EdgeInsets.only(
                      bottom: entry.key == places.length - 1 ? 0 : 4,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 24,
                          child: Text(
                            (entry.key + 1).toString().padLeft(2, '0'),
                            style: const TextStyle(
                              fontSize: 11,
                              height: 1.8,
                              color: _muted,
                            ),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            _displayName(entry.value),
                            style: const TextStyle(
                              fontSize: 13,
                              height: 1.5,
                              color: _ink,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasDistance = List.generate(
      widget.courses.length,
      _distance,
    ).any((value) => value != null);
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * .8,
      child: SafeArea(
        top: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 8, 8),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      '전체 코스 비교',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                        color: _ink,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: '비교 닫기',
                    onPressed: () => Navigator.pop(context),
                    color: _muted,
                    icon: const Icon(Icons.close, size: 21),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                itemCount: widget.courses.length,
                separatorBuilder: (_, _) => const SizedBox(height: 8),
                itemBuilder: (_, index) => _card(index),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (hasDistance) ...[
                    const Text(
                      '출발점 포함 · 직선거리 추정',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: _muted),
                    ),
                    const SizedBox(height: 10),
                  ],
                  FilledButton(
                    onPressed: widget.courses.isEmpty
                        ? null
                        : () => Navigator.pop(context, _pending),
                    style: FilledButton.styleFrom(
                      backgroundColor: _brown,
                      foregroundColor: const Color(0xFFFFFDFB),
                      minimumSize: const Size(0, 48),
                      padding: const EdgeInsets.all(12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(13),
                      ),
                    ),
                    child: Text('코스 ${_pending + 1} 보기'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
