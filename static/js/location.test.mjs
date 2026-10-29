import test from 'node:test';
import assert from 'node:assert/strict';
import { applyLocationSelection, geolocationFailureMessage, isPunjabCoordinate, parsePunjabAddress, reverseGeocode } from './location.js';

test('Punjab coordinate validation rejects non-finite and out-of-area points', () => {
  assert.equal(isPunjabCoordinate(30.901, 75.857), true);
  assert.equal(isPunjabCoordinate(28, 77), false);
  assert.equal(isPunjabCoordinate('NaN', 75.8), false);
});

test('reverse geocoding synchronizes coordinates, locality, and a known district', () => {
  const fields = { latitude: { value: '' }, longitude: { value: '' }, address: { value: '' }, district: { value: '' } };
  const result = applyLocationSelection(fields, 30.901, 75.857, {
    address: { state: 'Punjab', country_code: 'in', state_district: 'Ludhiana District', road: 'Model Town Road', suburb: 'Model Town' },
  });
  assert.equal(result.ok, true);
  assert.deepEqual(fields, {
    latitude: { value: '30.901000' }, longitude: { value: '75.857000' },
    address: { value: 'Model Town Road, Model Town' }, district: { value: 'Ludhiana' },
  });
});

test('unavailable or incomplete address data retains coordinates and manual address fields', () => {
  const fields = { latitude: { value: '' }, longitude: { value: '' }, address: { value: 'Ward 9' }, district: { value: 'Ludhiana' } };
  const result = applyLocationSelection(fields, 30.9, 75.8, null);
  assert.equal(result.ok, true);
  assert.equal(fields.latitude.value, '30.900000');
  assert.equal(fields.address.value, 'Ward 9');
  assert.equal(fields.district.value, 'Ludhiana');
  assert.deepEqual(parsePunjabAddress({ address: { state: 'Punjab', country_code: 'in' } }), { outsidePunjab: false, address: '', district: '' });
});

test('outside-Punjab geocoder results and invalid map points are rejected', () => {
  const fields = { latitude: { value: '' }, longitude: { value: '' }, address: { value: '' }, district: { value: '' } };
  assert.deepEqual(applyLocationSelection(fields, 30.9, 75.8, { address: { state: 'Haryana', country_code: 'in' } }), { ok: false, reason: 'outside-punjab' });
  assert.deepEqual(applyLocationSelection(fields, 28, 77), { ok: false, reason: 'outside-bounds' });
  assert.equal(fields.latitude.value, '');
});

test('browser geolocation failures explain denied permission and unavailable position', () => {
  assert.match(geolocationFailureMessage({ code: 1 }), /permission was denied/i);
  assert.match(geolocationFailureMessage({ code: 2 }), /location is unavailable/i);
  assert.match(geolocationFailureMessage({ code: 3 }), /timed out/i);
});

test('reverse geocoder reports unavailable service responses for manual fallback', async () => {
  await assert.rejects(reverseGeocode(30.9, 75.8, async () => { throw new TypeError('network unavailable'); }), /network unavailable/);
});
