import 'package:flutter/material.dart';
import 'place_map_button.dart';
import 'travel_data.dart';

class CourseTimeline extends StatelessWidget {
  final List<Map<String, dynamic>> places;
  final bool compact;
  final bool quiet;
  final int? selectedIndex;
  final ValueChanged<int>? onSelect;
  final List<GlobalKey>? stopKeys;
  const CourseTimeline({
    super.key,
    required this.places,
    this.compact = false,
    this.quiet = false,
    this.selectedIndex,
    this.onSelect,
    this.stopKeys,
  });
  @override
  Widget build(BuildContext context) => Column(
    children: List.generate(
      places.length,
      (index) => _TimelineStop(
        key: stopKeys?[index],
        place: places[index],
        step: index + 1,
        isLast: index == places.length - 1,
        compact: compact,
        quiet: quiet,
        selected: selectedIndex == index,
        onSelect: onSelect == null ? null : () => onSelect!(index),
      ),
    ),
  );
}

class _TimelineStop extends StatelessWidget {
  final Map<String, dynamic> place;
  final int step;
  final bool isLast;
  final bool compact;
  final bool quiet;
  final bool selected;
  final VoidCallback? onSelect;

  const _TimelineStop({
    super.key,
    required this.place,
    required this.step,
    required this.isLast,
    required this.compact,
    required this.quiet,
    required this.selected,
    this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final data = PlaceData.fromJson(place);
    final name = data.name;
    final address = data.address;
    final category = data.category;

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: quiet ? Colors.transparent : const Color(0xFF26C6DA),
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    quiet ? step.toString().padLeft(2, '0') : '$step',
                    style: TextStyle(
                      color: quiet ? const Color(0xFF087E8B) : Colors.white,
                      fontWeight: quiet ? FontWeight.w600 : FontWeight.bold,
                    ),
                  ),
                ),
              ),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: quiet ? 1 : 2,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    color: quiet
                        ? const Color(0xFFEADFD6)
                        : const Color(0xFF26C6DA),
                  ),
                ),
            ],
          ),
          SizedBox(width: quiet ? 4 : 14),

          Expanded(
            child: Semantics(
              selected: selected,
              child: InkWell(
                onTap: onSelect,
                borderRadius: BorderRadius.circular(quiet ? 17 : 14),
                child: Container(
                  margin: EdgeInsets.only(bottom: isLast ? 0 : 16),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: selected
                        ? const Color(0xFFFFF3E9)
                        : quiet
                        ? const Color(0xFFFFFDFB)
                        : Colors.white,
                    border: quiet
                        ? Border.all(
                            color: selected
                                ? const Color(0xFFCAA28C)
                                : const Color(0xFFEADFD6),
                          )
                        : null,
                    borderRadius: BorderRadius.circular(quiet ? 17 : 14),
                    boxShadow: quiet
                        ? []
                        : [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.05),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                          ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (quiet && category.isNotEmpty) ...[
                        Text(
                          category,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF087E8B),
                          ),
                        ),
                        const SizedBox(height: 5),
                      ],
                      Text(
                        name,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: quiet ? FontWeight.w600 : FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 4),
                      if (!quiet && category.isNotEmpty)
                        Container(
                          margin: const EdgeInsets.only(bottom: 4),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE8F9FB),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            category,
                            style: const TextStyle(
                              fontSize: 12,
                              color: Color(0xFF087E8B),
                            ),
                          ),
                        ),
                      if (address.isNotEmpty) ...[
                        Text(
                          address,
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.5,
                            color: Color(0xFF5F6368),
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      PlaceMapButton(
                        place: place,
                        lookupDetail: true,
                        quiet: quiet,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
