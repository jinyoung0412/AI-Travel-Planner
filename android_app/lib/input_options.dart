part of 'input_screen.dart';

const Map<String, LocationFix> _kRegionCenters = {
  '천안': LocationFix(36.8151, 127.1139),
  '아산': LocationFix(36.7898, 127.0043),
};

const _kTransitHubs = transitHubs;

// Only the mood group permits more than one selected tag.
const Set<String> _kSingleSelectGroups = {'누구와', '특별한 날', '실내 · 야외', '어떤 활동'};

class _SlotStyle {
  final IconData icon;
  final Color color;
  const _SlotStyle(this.icon, this.color);
}

const _kSlotStyles = {
  '음식': _SlotStyle(Icons.restaurant, Color(0xFFFF7043)),
  '카페': _SlotStyle(Icons.local_cafe, Color(0xFF795548)),
  '자연·산책': _SlotStyle(Icons.nature_people, Color(0xFF43A047)),
  '등산': _SlotStyle(Icons.terrain, Color(0xFF2E7D32)),
  '문화·역사': _SlotStyle(Icons.account_balance, Color(0xFF7B1FA2)),
  '쇼핑': _SlotStyle(Icons.shopping_cart, Color(0xFFE91E63)),
  '관광지': _SlotStyle(Icons.place, Color(0xFF1976D2)),
  '실내 오락': _SlotStyle(Icons.videogame_asset, Color(0xFF5E35B1)),
};

const _kDefaultCourse = ['음식', '자연·산책', '카페', '문화·역사', '음식'];

const Map<String, List<String>> _kTagGroups = {
  '누구와': [
    '혼자',
    '친구와',
    '연인과',
    '부부끼리',
    '가족 나들이',
    '부모님 모시고',
    '아이와 함께',
    '유아/영아 동반',
    '단체/모임',
    '동아리/클럽',
    '회식',
    '소개팅/첫만남',
  ],
  '어떤 분위기': [
    '힐링/여유',
    '활동적인',
    '감성적인',
    '로맨틱한',
    '조용한',
    '트렌디한',
    '고급스러운',
    '아늑한',
    '이색적인',
    '자연 친화적',
    '소소한 일상',
    '설레는',
    '멋진 야경',
  ],
  '특별한 날': ['기념일', '생일', '졸업·입학 기념', '프로포즈', '첫 데이트', '오랜만에 만남', '일상 탈출'],
  '실내 · 야외': ['실내 위주', '야외 위주'],
  '어떤 활동': [
    '맛집 탐방',
    '카페 투어',
    '문화·역사 탐방',
    '박물관/전시',
    '쇼핑',
    '자연/산책',
    '등산/트레킹',
    '사진 명소',
    '스포츠/레저',
    '체험 공방',
    '전통/한옥',
    '노래방/실내 오락',
  ],
};
