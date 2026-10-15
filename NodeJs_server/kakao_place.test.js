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
