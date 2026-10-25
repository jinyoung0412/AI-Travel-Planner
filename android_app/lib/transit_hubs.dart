import 'location_service.dart';

/// Public-map representative points, not surveyed entrances or boarding stops.
/// Source/date/previous values: test/fixtures/transit_hubs.json.
/// Map attribution: © OpenStreetMap contributors (ODbL), via Mapcarta.
class TransitHub extends LocationFix {
  final String name;
  final String address;
  final String sourceUrl;
  static const checkedDate = '2026-10-20';
  const TransitHub(
    this.name,
    super.lat,
    super.lng,
    this.address,
    this.sourceUrl,
  );
}

const Map<String, List<TransitHub>> transitHubs = {
  '천안': [
    TransitHub(
      '천안역',
      36.81028,
      127.14684,
      '충남 천안시 동남구 대흥로 239',
      'https://mapcarta.com/N368636171',
    ),
    TransitHub(
      '봉명역',
      36.8013,
      127.13587,
      '충남 천안시 동남구 차돌로 51',
      'https://mapcarta.com/N1973709782',
    ),
    TransitHub(
      '쌍용역',
      36.79372,
      127.12129,
      '충남 천안시 서북구 쌍용19로 20',
      'https://mapcarta.com/N980061738',
    ),
    TransitHub(
      '두정역',
      36.83365,
      127.14894,
      '충남 천안시 서북구 두정로 289',
      'https://mapcarta.com/29774926',
    ),
    TransitHub(
      '천안아산역 (KTX)',
      36.79438,
      127.1045,
      '충남 아산시 배방읍 희망로 일대',
      'https://mapcarta.com/N4725167962',
    ),
    TransitHub(
      '천안종합터미널',
      36.81949,
      127.15599,
      '충남 천안시 동남구 만남로 43',
      'https://mapcarta.com/N368736352',
    ),
  ],
  '아산': [
    TransitHub(
      '온양온천역',
      36.78055,
      127.00316,
      '충남 아산시 온천대로 1496',
      'https://mapcarta.com/N5894627167',
    ),
    TransitHub(
      '신창역',
      36.76979,
      126.95182,
      '충남 아산시 신창면 행목로 50',
      'https://mapcarta.com/32847756',
    ),
    TransitHub(
      '탕정역',
      36.78821,
      127.08456,
      '충남 아산시 한들물빛6로 11',
      'https://mapcarta.com/N6022603091',
    ),
    TransitHub(
      '천안아산역 (KTX)',
      36.79438,
      127.1045,
      '충남 아산시 배방읍 희망로 일대',
      'https://mapcarta.com/N4725167962',
    ),
    TransitHub(
      '아산터미널',
      36.78476,
      127.01597,
      '충남 아산시 번영로 225',
      'https://mapcarta.com/W869986467',
    ),
    TransitHub(
      '배방역',
      36.7777,
      127.05299,
      '충남 아산시 배방읍 온천대로 1967',
      'https://mapcarta.com/29533372',
    ),
  ],
};
