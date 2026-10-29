import 'package:flutter/material.dart';
import 'travel_data.dart';

class CourseSummaryCard extends StatelessWidget {
  final bool quiet;
  final bool showDescription;
  final Map<String, dynamic>? metric;
  final Map<String, dynamic> metadata;
  final List<Map<String, dynamic>> places;

  const CourseSummaryCard({
    super.key,
    this.quiet = false,
    this.showDescription = true,
    required this.metric,
    required this.metadata,
    required this.places,
  });

  @override
  Widget build(BuildContext context) {
    final distanceAllowed = places.every(
      (place) => PlaceData.fromJson(place).coordinateDistanceAllowed,
    );
    final distance = finiteNumber(metric?['estimated_distance_km']);
    final showDistance =
        places.isNotEmpty &&
        distanceAllowed &&
        distance != null &&
        distance >= 0;
    if (!showDistance) return const SizedBox.shrink();
    if (quiet) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Align(
          alignment: Alignment.centerLeft,
          widthFactor: showDescription ? null : 1,
          child: Wrap(
            spacing: 10,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  const Icon(
                    Icons.route_outlined,
                    size: 18,
                    color: Color(0xFF087E8B),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    '약 ${distance.toStringAsFixed(1)} km',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF087E8B),
                    ),
                  ),
                ],
              ),
              if (showDescription)
                const Text(
                  '출발점 포함 · 직선거리 추정',
                  style: TextStyle(fontSize: 12, color: Color(0xFF70645D)),
                ),
            ],
          ),
        ),
      );
    }
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFE8F9FB),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            '출발점 포함 · 직선거리 추정',
            style: TextStyle(fontSize: 13, color: Color(0xFF32636A)),
          ),
          const SizedBox(height: 4),
          Text(
            '약 ${distance.toStringAsFixed(1)} km',
            style: const TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.bold,
              color: Color(0xFF087E8B),
            ),
          ),
        ],
      ),
    );
  }
}
