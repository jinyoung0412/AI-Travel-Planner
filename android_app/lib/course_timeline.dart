import 'package:flutter/material.dart';
import 'place_map_button.dart';
import 'travel_data.dart';

class CourseTimeline extends StatelessWidget {
  final List<Map<String, dynamic>> places;
  const CourseTimeline({super.key, required this.places});
  @override
  Widget build(BuildContext context) => Column(
    children: List.generate(
      places.length,
      (index) => _TimelineStop(
        place: places[index],
        step: index + 1,
        isLast: index == places.length - 1,
      ),
    ),
  );
}

class _TimelineStop extends StatelessWidget {
  final Map<String, dynamic> place;
  final int step;
  final bool isLast;

  const _TimelineStop({
    required this.place,
    required this.step,
    required this.isLast,
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
                decoration: const BoxDecoration(
                  color: Color(0xFF26C6DA),
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    '$step',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    color: const Color(0xFF26C6DA),
                  ),
                ),
            ],
          ),
          const SizedBox(width: 14),

          Expanded(
            child: Container(
              margin: EdgeInsets.only(bottom: isLast ? 0 : 16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                boxShadow: [
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
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  if (category.isNotEmpty)
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
                          color: Color(0xFF26C6DA),
                        ),
                      ),
                    ),
                  Text(
                    address,
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
                  ),
                  const SizedBox(height: 10),
                  PlaceMapButton(place: place),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
