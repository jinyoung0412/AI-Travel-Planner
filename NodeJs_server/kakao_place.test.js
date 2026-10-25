const test = require('node:test');
const assert = require('node:assert/strict');
const { findPlace, selectIdentityMatch } = require('./kakao_place');
const input = { name: '아지트', address: '충남 천안시 테스트로 1', lat: 36.8151, lng: 127.1139 };
const doc = { id: '1', place_name: '아지트', place_url: 'https://place.map.kakao.com/1',
    x: '127.1139', y: '36.8151', road_address_name: input.address };

test('matching branch requires address and proximity, not same name', () => {
    const other = { ...doc, id: '2', road_address_name: '충남 천안시 테스트로 2' };
    assert.equal(selectIdentityMatch([other, doc], input).id, '1');
    assert.equal(selectIdentityMatch([other], input), null);
    assert.equal(selectIdentityMatch([{ ...doc, x: '127.2' }], input), null);
});
test('ambiguous results and incomplete address fall back to a pin', () => {
    assert.equal(selectIdentityMatch([doc, { ...doc, id: '2' }], input), null);
    assert.equal(selectIdentityMatch([doc], { ...input, address: '천안시' }), null);
});
test('map API is mocked, bounded and passes original coordinates', async () => {
    let calls = 0;
    const mock = { get: async (url, options) => {
        calls += 1;
        assert.equal(options.params.x, input.lng);
        assert.equal(options.params.y, input.lat);
        assert.equal(options.timeout, 10000);
        return { data: { documents: [doc] } };
    } };
    assert.equal((await findPlace(mock, input, { Authorization: 'mock' })).id, '1');
    assert.equal(calls, 1);
});
test('map failure propagates to the gateway error handler', async () => {
    await assert.rejects(findPlace({ get: async () => { throw new Error('mock timeout'); } }, input, {}), /mock timeout/);
});

const addressCases = require('../tests/fixtures/address_cases.json');
for (const fixture of addressCases) {
    test(`complete address tokens: ${fixture.label}`, () => {
        const expected = { ...input, address: '충남 천안시 중앙로 10' };
        const actual = { ...doc, road_address_name: fixture.address, address_name: '' };
        assert.equal(selectIdentityMatch([actual], expected)?.id ?? null, fixture.matches ? '1' : null);
    });
}


test('numeric coordinates and provider HTTP links remain compatible; links upgrade to HTTPS', async () => {
    const actual = { ...doc, x: 127.1139, y: 36.8151, place_url: 'http://place.map.kakao.com/1' };
    assert.equal(selectIdentityMatch([actual], input).id, '1');
    const matched = await findPlace({ get: async () => ({ data: { documents: [actual] } }) }, input, {});
    assert.equal(matched.place_url, 'https://place.map.kakao.com/1');
});

test('malformed map documents and unrelated URLs cannot prove an identity', () => {
    assert.throws(() => selectIdentityMatch({}, input), /Invalid map response/);
    for (const invalid of [null, { ...doc, x: null }, { ...doc, y: '' },
        { ...doc, x: 181 }, { ...doc, place_url: 'https://other.invalid/1' },
        { ...doc, place_url: 'javascript:alert(1)' }]) {
        assert.equal(selectIdentityMatch([invalid], input), null);
    }
});

test('API-01: arbitrary facility and branch suffixes cannot establish identity', () => {
    for (const [name, suffix] of [['검토공원', '공영주차장'], ['검토박물관', '부설카페'],
        ['검토카페', '본점'], ['검토카페 본점', '별관']]) {
        const expected = { ...input, name };
        const exact = { ...doc, place_name: name };
        const other = { ...doc, id: '2', place_name: `${name} ${suffix}` };
        assert.equal(selectIdentityMatch([other], expected), null);
        assert.equal(selectIdentityMatch([other, exact], expected).id, '1');
    }
    assert.equal(selectIdentityMatch([{ ...doc, place_name: '아지트  천안점' }],
        { ...input, name: ' 아지트\n천안점 ' }).id, '1');
    assert.equal(selectIdentityMatch([{ ...doc, place_name: '아지트 아산점' }],
        { ...input, name: '아지트 천안점' }), null);
});

for (const [source, provider] of [
    ['뚜쥬루과자점 거북이점', '뚜쥬루 거북이점'],
    ['뚜쥬루갤러리아백화점센터시티점', '뚜쥬루 갤러리아점'],
    ['뚜쥬루과자점 성정점', '뚜쥬루 성정점'],
    ['뚜쥬루 빵돌가마마을', '뚜쥬루 빵돌가마점'],
]) {
    test(`branch spelling alias retains address/distance identity: ${source}`, async () => {
        const expected = { ...input, name: source };
        const actual = { ...doc, place_name: provider, category_name: '음식점 > 간식 > 제과,베이커리' };
        assert.equal(selectIdentityMatch([actual], expected).id, '1');
        assert.equal(selectIdentityMatch([{ ...actual, road_address_name: '충남 천안시 테스트로 2' }], expected), null);
        assert.equal(selectIdentityMatch([{ ...actual, x: '127.2' }], expected), null);
        assert.equal(selectIdentityMatch([actual], { ...expected, address: '' }), null);
        assert.equal(selectIdentityMatch([{ ...actual, category_name: '교통,수송 > 전기차 충전소' }], expected), null);
        assert.equal(selectIdentityMatch([{ ...actual, place_name: provider + ' 전기차충전소' }], expected), null);
        assert.equal(selectIdentityMatch([actual, { ...actual, id: '2' }], expected), null);
        let calls = 0;
        const matched = await findPlace({ get: async (_url, options) => {
            calls++;
            assert.equal(options.params.query, provider);
            return { data: { documents: [actual] } };
        } }, expected, {});
        assert.equal(matched.id, '1');
        assert.equal(calls, 1);
    });
}

test('brand aliases never equate different branches at the same address', () => {
    const expected = { ...input, name: '뚜쥬루과자점 성정점' };
    for (const name of ['뚜쥬루 거북이점', '뚜쥬루 어린이베이커리', '뚜쥬루 성정점 별관']) {
        assert.equal(selectIdentityMatch([{ ...doc, place_name: name,
            category_name: '음식점 > 제과,베이커리' }], expected), null);
    }
});

test('provider name spacing is allowed only with complete matching identity evidence', () => {
    const expected = { ...input, name: '랜드마크195', address: '충남 천안시 동남구 유량로 195 랜드마크195' };
    const actual = { ...doc, place_name: '랜드마크 195', road_address_name: '충남 천안시 동남구 유량로 195' };
    assert.equal(selectIdentityMatch([actual], expected).id, '1');
    assert.equal(selectIdentityMatch([actual], { ...expected, address: '' }), null);
    assert.equal(selectIdentityMatch([actual], { ...expected, address: '천안시 동남구' }), null);
    assert.equal(selectIdentityMatch([{ ...actual, road_address_name: '충남 천안시 동남구 유량로 196' }], expected), null);
    assert.equal(selectIdentityMatch([{ ...actual, x: '127.2' }], expected), null);
    assert.equal(selectIdentityMatch([{ ...actual, place_name: '랜드마크 195 별관' }], expected), null);
    assert.equal(selectIdentityMatch([{ ...actual, place_name: '랜드마크 195 전기차충전소' }], expected), null);
    assert.equal(selectIdentityMatch([actual, { ...actual, id: '2' }], expected), null);
    assert.equal(selectIdentityMatch([{ ...actual, place_name: '랜드마크 195 아산점' }], expected), null);
});
