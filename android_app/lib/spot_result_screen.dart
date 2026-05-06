import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_service.dart';

class SpotResultScreen extends StatelessWidget {
  final List<Map<String, dynamic>> places;
  final int requestedCount;

  const SpotResultScreen({super.key, required this.places, required this.requestedCount});

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
        itemCount: places.length + (places.length < requestedCount ? 1 : 0),
        itemBuilder: (context, index) {
          if (index == 0 && places.length < requestedCount) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF3E0),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFFFCC80)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, size: 16, color: Color(0xFFFF8F00)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '선택하신 조건에 맞는 장소가 부족해 ${places.length}곳만 추천되었어요.',
                        style: const TextStyle(fontSize: 13, color: Color(0xFF795548)),
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

class _PlaceCard extends StatefulWidget {
  final Map<String, dynamic> place;
  final int rank;

  const _PlaceCard({required this.place, required this.rank});

  @override
  State<_PlaceCard> createState() => _PlaceCardState();
}

class _PlaceCardState extends State<_PlaceCard> {
  bool _isLoading = false;

  Future<void> _openKakaoDetail() async {
    setState(() => _isLoading = true);
    try {
      final name = widget.place['name'] as String? ?? '';
      final lat  = (widget.place['lat']  as num).toDouble();
      final lng  = (widget.place['lng']  as num).toDouble();

      final placeUrl = await ApiService.getKakaoPlaceUrl(
        name: name, lat: lat, lng: lng,
      );

      if (!mounted) return;

      if (placeUrl == null) {
        // 미등록 장소 → 좌표 핀으로 폴백
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('카카오맵 미등록 장소예요. 위치만 표시할게요.')),
          );
        }
        final appUri = Uri.parse('kakaomap://look?p=$lat,$lng');
        final webUri = Uri.parse(
            'https://map.kakao.com/link/map/${Uri.encodeComponent(name)},$lat,$lng');
        if (await canLaunchUrl(appUri)) {
          await launchUrl(appUri);
        } else {
          await launchUrl(webUri, mode: LaunchMode.externalApplication);
        }
        return;
      }

      final uri = Uri.parse(placeUrl);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('카카오맵을 열 수 없습니다.')),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final name     = widget.place['name']     as String? ?? '';
    final address  = widget.place['address']  as String? ?? '';
    final category = widget.place['category'] as String? ?? '';

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
                '${widget.rank}',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                if (category.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(bottom: 4),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF0EB),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(category,
                        style: const TextStyle(
                            fontSize: 12, color: Color(0xFFFF7043))),
                  ),
                Text(address,
                    style: TextStyle(
                        fontSize: 13, color: Colors.grey.shade500)),
                const SizedBox(height: 10),
                GestureDetector(
                  onTap: _isLoading ? null : _openKakaoDetail,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_isLoading)
                        SizedBox(
                          width: 13, height: 13,
                          child: CircularProgressIndicator(
                              strokeWidth: 1.5,
                              color: Colors.grey.shade500),
                        )
                      else
                        Icon(Icons.open_in_new,
                            size: 14, color: Colors.grey.shade500),
                      const SizedBox(width: 5),
                      Text(
                        _isLoading ? '불러오는 중...' : '카카오맵에서 보기',
                        style: TextStyle(
                            fontSize: 13, color: Colors.grey.shade500),
                      ),
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
