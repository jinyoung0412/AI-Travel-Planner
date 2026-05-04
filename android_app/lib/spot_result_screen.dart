import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class SpotResultScreen extends StatelessWidget {
  final List<Map<String, dynamic>> places;

  const SpotResultScreen({super.key, required this.places});

  Future<void> _openKakaoMap(BuildContext context, Map<String, dynamic> place) async {
    final lat = place['lat'];
    final lng = place['lng'];
    final name = Uri.encodeComponent(place['name'] ?? '');
    final appUri = Uri.parse('kakaomap://look?p=$lat,$lng');
    final webUri = Uri.parse('https://map.kakao.com/link/to/$name,$lat,$lng');

    if (await canLaunchUrl(appUri)) {
      await launchUrl(appUri);
    } else if (await canLaunchUrl(webUri)) {
      await launchUrl(webUri, mode: LaunchMode.externalApplication);
    } else {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('지도를 열 수 없습니다.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: const Text('추천 장소', style: TextStyle(fontWeight: FontWeight.bold)),
      ),
      body: ListView.builder(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        itemCount: places.length,
        itemBuilder: (context, index) => _PlaceCard(
          place: places[index],
          rank: index + 1,
          onMapTap: () => _openKakaoMap(context, places[index]),
        ),
      ),
    );
  }
}

class _PlaceCard extends StatelessWidget {
  final Map<String, dynamic> place;
  final int rank;
  final VoidCallback onMapTap;

  const _PlaceCard({required this.place, required this.rank, required this.onMapTap});

  @override
  Widget build(BuildContext context) {
    final name     = place['name']     ?? '';
    final address  = place['address']  ?? '';
    final category = place['category'] ?? '';

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
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                if (category.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(bottom: 4),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF0EB),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(category, style: const TextStyle(fontSize: 12, color: Color(0xFFFF7043))),
                  ),
                Text(address, style: TextStyle(fontSize: 13, color: Colors.grey.shade500)),
                const SizedBox(height: 10),
                GestureDetector(
                  onTap: onMapTap,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.map_outlined, size: 15, color: Colors.grey.shade600),
                      const SizedBox(width: 4),
                      Text('지도에서 보기', style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
