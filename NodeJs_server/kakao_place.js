// A Kakao search result is an external identity, not an authoritative match by
// name alone. Require local coordinates plus address evidence when available.
function normalize(value) {
    return String(value || '').trim().replace(/\s+/g, ' ').replace(/^충청남도(?= |$)/, '충남');
}

function addressAnchor(value) {
    const text = normalize(value);
    const city = text.match(/([가-힣]+시)(?: |$)/)?.[1];
    const road = text.match(/([가-힣0-9·]+(?:로|길))\s+(\d+(?:-\d+)?)(?![\d-])/);
    return city && road ? `${city}|${road[1]}|${road[2]}` : null;
}

function distanceM(lat, lng, doc) {
    const y = Number(doc.y), x = Number(doc.x);
    if (!Number.isFinite(y) || !Number.isFinite(x)) return Infinity;
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
    const matches = documents.filter(doc => {
        if (!doc.place_url || distanceM(lat, lng, doc) > 250) return false;
        const actualName = normalize(doc.place_name);
        if (actualName !== query && !(expected && actualName.startsWith(query + ' '))) return false;
        return !expected || [doc.road_address_name, doc.address_name].some(a => addressAnchor(a) === expected);
    });
    // Multiple matches are ambiguous: the Flutter client can open its own pin.
    return matches.length === 1 ? matches[0] : null;
}

async function findPlace(httpClient, input, headers) {
    const response = await httpClient.get('https://dapi.kakao.com/v2/local/search/keyword.json', {
        params: { query: input.name, x: input.lng, y: input.lat, radius: 1000, size: 15 }, headers,
        timeout: 10000,
    });
    return selectIdentityMatch(response.data.documents || [], input);
}

module.exports = { selectIdentityMatch, findPlace };
