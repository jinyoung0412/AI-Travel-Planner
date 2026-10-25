// A Kakao search result is an external identity, not an authoritative match by
// name alone. Require local coordinates plus address evidence when available.
const KAKAO_TIMEOUT_MS = 10000;

function normalize(value) {
    return String(value || '').trim().replace(/\s+/g, ' ').replace(/^충청남도(?= |$)/, '충남');
}

// Source/provider labels checked on 2026-10-25. These are spelling aliases for
// individual branches, never permission to match every store of a brand.
const BRANCH_NAMES = [
    ['뚜쥬루과자점 거북이점', '뚜쥬루 거북이점'],
    ['뚜쥬루갤러리아백화점센터시티점', '뚜쥬루 갤러리아점'],
    ['뚜쥬루과자점 성정점', '뚜쥬루 성정점'],
    ['뚜쥬루 빵돌가마마을', '뚜쥬루 빵돌가마점'],
];
const BRANCH_ALIAS = new Map(BRANCH_NAMES.flatMap(names => names.map(name => [name, names[1]])));

function samePlaceName(actual, expected, doc, address) {
    if (actual === expected) return true;
    // Providers may insert spaces in a label (랜드마크195 / 랜드마크 195).
    // Keep every letter/branch token, and require the same complete address.
    // Candidate filtering below still enforces proximity and uniqueness.
    if (address && actual.replace(/\s+/g, '') === expected.replace(/\s+/g, '')) return true;
    const branch = BRANCH_ALIAS.get(expected);
    // Alias matches still require a complete matching address, proximity and
    // bakery category; an annex/charger at the same site is a different place.
    return Boolean(branch && branch === BRANCH_ALIAS.get(actual) && address &&
        typeof doc.category_name === 'string' && /제과|베이커리/.test(doc.category_name));
}

function addressAnchor(value) {
    // Same token/whitespace contract as blog_evidence.py; shared JSON fixtures
    // exercise both implementations. Address fields contain one place address.
    const text = normalize(value).toLowerCase();
    const cities = [...text.matchAll(/(?<![가-힣a-z0-9_])([가-힣]+시)(?![가-힣a-z0-9_])/g)];
    for (let i = 0; i < cities.length; i++) {
        const city = cities[i];
        const start = city.index + city[0].length;
        const end = Math.min(start + 250, cities[i + 1]?.index ?? text.length);
        const road = text.slice(start).match(
            /(?<![가-힣a-z0-9_·])([가-힣a-z0-9·]+(?:로|길))\s*(\d+(?:\s*-\s*\d+)?)(?![가-힣a-z0-9_-]|\s*[-－–—−/／]|\.\d)/
        );
        if (road && start + road.index + road[0].length <= end) return `${city[1]}|${road[1]}|${road[2].replace(/\s+/g, '')}`;
    }
    return null;
}

function distanceM(lat, lng, doc) {
    const y = Number(doc.y), x = Number(doc.x);
    const coordinate = value => (typeof value === 'number' ||
        (typeof value === 'string' && value.trim().length > 0));
    if (!coordinate(doc.y) || !coordinate(doc.x) || !Number.isFinite(y) || !Number.isFinite(x) ||
        Math.abs(y) > 90 || Math.abs(x) > 180) return Infinity;
    const radians = degrees => degrees * Math.PI / 180;
    const h = Math.sin(radians(y - lat) / 2) ** 2
        + Math.cos(radians(lat)) * Math.cos(radians(y)) * Math.sin(radians(x - lng) / 2) ** 2;
    return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

function selectIdentityMatch(documents, { name, address, lat, lng }) {
    const expected = addressAnchor(address);
    // An incomplete provided address cannot prove a different provider's ID.
    if (address && !expected) return null;
    const query = normalize(name);
    if (!Array.isArray(documents)) throw new Error('Invalid map response');
    const matches = documents.filter(doc => {
        if (!doc || typeof doc !== 'object' || !/^https?:\/\/place\.map\.kakao\.com\/\d+$/.test(doc.place_url) || distanceM(lat, lng, doc) > 250) return false;
        const actualName = normalize(doc.place_name);
        // A shared building/coordinate does not make a parking lot, annex or
        // another branch the requested place. Keep branch names intact.
        if (!samePlaceName(actualName, query, doc, expected)) return false;
        return !expected || [doc.road_address_name, doc.address_name].some(a => addressAnchor(a) === expected);
    });
    // Multiple matches are ambiguous: the Flutter client can open its own pin.
    return matches.length === 1 ? matches[0] : null;
}

async function findPlace(httpClient, input, headers, { signal } = {}) {
    const response = await httpClient.get('https://dapi.kakao.com/v2/local/search/keyword.json', {
        params: { query: BRANCH_ALIAS.get(normalize(input.name)) || input.name,
            x: input.lng, y: input.lat, radius: 1000, size: 15 }, headers,
        timeout: KAKAO_TIMEOUT_MS, signal,
    });
    const match = selectIdentityMatch(response.data?.documents, input);
    return match ? { ...match, place_url: match.place_url.replace(/^http:/, 'https:') } : null;
}

module.exports = { selectIdentityMatch, findPlace, KAKAO_TIMEOUT_MS };
