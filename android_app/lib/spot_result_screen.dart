import 'package:flutter/material.dart';
import 'bookmark_button.dart';
import 'place_map_button.dart';
import 'travel_data.dart';
import 'preference_notice.dart';
import 'local_storage_service.dart';

class SpotResultScreen extends StatelessWidget {
  final List<Map<String, dynamic>> places;
  final int requestedCount;
  final Map<String, dynamic> metadata;

  const SpotResultScreen({
    super.key,
    required this.places,
    required this.requestedCount,
    this.metadata = const {},
  });

  @override
  Widget build(BuildContext context) {
    final evidenceBanner = metadata['preference_evidence'] == 'unavailable'
        ? 1
        : 0;
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: const Text(
          '추천 장소',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
      ),
      body: ListView.builder(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        itemCount:
            places.length +
            (places.length < requestedCount ? 1 : 0) +
            evidenceBanner,
        itemBuilder: (context, index) {
          if (evidenceBanner == 1 && index == 0) {
            return PreferenceNotice(metadata: metadata);
          }
          index -= evidenceBanner;
          if (index == 0 && places.length < requestedCount) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF3E0),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFFFCC80)),
                ),
                child: Row(
                  children: [
                    const Icon(
                      Icons.info_outline,
                      size: 16,
                      color: Color(0xFFFF8F00),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '선택하신 조건에 맞는 장소가 부족해 ${places.length}곳만 추천되었어요.',
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xFF795548),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          }
          final i = places.length < requestedCount ? index - 1 : index;
          return _PlaceCard(place: places[i], rank: i + 1);
        },
      ),
    );
  }
}

class _PlaceCard extends StatelessWidget {
  final Map<String, dynamic> place;
  final int rank;

  const _PlaceCard({required this.place, required this.rank});

  @override
  Widget build(BuildContext context) {
    final data = PlaceData.fromJson(place);
    final name = data.name;
    final address = data.address;
    final category = data.category;

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: const BoxDecoration(
              color: Color(0xFFFF7043),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                '$rank',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        name,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    BookmarkButton(
                      read: () => LocalStorageService.isSpotSaved(place),
                      save: () => LocalStorageService.saveSpot(place),
                      remove: () => LocalStorageService.deleteSpot(place),
                      label: '스팟을',
                      color: const Color(0xFFFF7043),
                    ),
                  ],
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
                      color: const Color(0xFFFFF0EB),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      category,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFFFF7043),
                      ),
                    ),
                  ),
                Text(
                  address,
                  style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
                ),
                const SizedBox(height: 10),
                PlaceMapButton(place: place, lookupDetail: true),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
