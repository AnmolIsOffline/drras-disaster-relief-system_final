const PUNJAB_DISTRICTS = [
  'Amritsar', 'Barnala', 'Bathinda', 'Faridkot', 'Fatehgarh Sahib', 'Fazilka',
  'Ferozepur', 'Gurdaspur', 'Hoshiarpur', 'Jalandhar', 'Kapurthala', 'Ludhiana',
  'Malerkotla', 'Mansa', 'Moga', 'Sri Muktsar Sahib', 'Pathankot', 'Patiala',
  'Rupnagar', 'Sahibzada Ajit Singh Nagar', 'Sangrur',
  'Shaheed Bhagat Singh Nagar', 'Tarn Taran',
];

// Keep this aligned with operations.geography.is_punjab_coordinate.
export function isPunjabCoordinate(latitude, longitude) {
  const lat = Number(latitude), lon = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= 29.5 && lat <= 32.6 && lon >= 73.8 && lon <= 76.9;
}

function districtName(address = {}) {
  const raw = String(address.state_district || address.county || address.district || '').trim();
  const cleaned = raw.replace(/\s+district$/i, '').replace(/\s+/g, ' ').toLowerCase();
  const aliases = {
    'sas nagar': 'Sahibzada Ajit Singh Nagar',
    's.a.s. nagar': 'Sahibzada Ajit Singh Nagar',
    'mohali': 'Sahibzada Ajit Singh Nagar',
    'nawanshahr': 'Shaheed Bhagat Singh Nagar',
    'muktsar': 'Sri Muktsar Sahib',
  };
  if (aliases[cleaned]) return aliases[cleaned];
  return PUNJAB_DISTRICTS.find(name => name.toLowerCase() === cleaned) || '';
}

export function parsePunjabAddress(result) {
  const address = result?.address || {};
  const state = String(address.state || '').trim();
  const country = String(address.country_code || '').toLowerCase();
  if ((state && !/\bpunjab\b/i.test(state)) || (country && country !== 'in')) {
    return { outsidePunjab: true, address: '', district: '' };
  }
  if (!/\bpunjab\b/i.test(state) || country === 'pk') {
    return { outsidePunjab: false, address: '', district: '' };
  }
  const locality = address.neighbourhood || address.suburb || address.village
    || address.town || address.city || address.hamlet || '';
  const street = [address.house_number, address.road].filter(Boolean).join(' ').trim();
  const localityText = [street, locality].filter(Boolean).join(', ');
  return {
    outsidePunjab: false,
    address: localityText.slice(0, 180),
    district: districtName(address),
  };
}

export function applyLocationSelection(fields, latitude, longitude, result = null) {
  const lat = Number(latitude), lon = Number(longitude);
  if (!isPunjabCoordinate(lat, lon)) return { ok: false, reason: 'outside-bounds' };
  const parsed = result ? parsePunjabAddress(result) : { outsidePunjab: false, address: '', district: '' };
  if (parsed.outsidePunjab) return { ok: false, reason: 'outside-punjab' };
  fields.latitude.value = lat.toFixed(6);
  fields.longitude.value = lon.toFixed(6);
  if (parsed.address) fields.address.value = parsed.address;
  if (parsed.district) fields.district.value = parsed.district;
  return { ok: true, addressUpdated: Boolean(parsed.address), districtUpdated: Boolean(parsed.district) };
}

export function geolocationFailureMessage(error) {
  if (error?.code === 1) return 'Location permission was denied. Allow location access in your browser or choose a point on the map.';
  if (error?.code === 2) return 'Your current location is unavailable. Check device location or choose a point on the map.';
  return 'Location lookup timed out. Try again or choose a point on the map.';
}

let lastLookupAt = 0;
const reverseCache = new Map();
let lookupQueue = Promise.resolve();
export function reverseGeocode(latitude, longitude, fetcher = fetch) {
  const lat = Number(latitude), lon = Number(longitude);
  if (!isPunjabCoordinate(lat, lon)) throw new Error('Selected point is outside the supported Punjab area.');
  const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  if (reverseCache.has(key)) return Promise.resolve(reverseCache.get(key));
  const task = lookupQueue.then(async () => {
    if (reverseCache.has(key)) return reverseCache.get(key);
    const delay = Math.max(0, 1100 - (Date.now() - lastLookupAt));
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    lastLookupAt = Date.now();
    const url = new URL('https://nominatim.openstreetmap.org/reverse');
    url.search = new URLSearchParams({ format: 'jsonv2', addressdetails: '1', 'accept-language': 'en', lat: String(lat), lon: String(lon) });
    const response = await fetcher(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Location lookup returned ${response.status}.`);
    const result = await response.json();
    if (!result || typeof result !== 'object') throw new Error('Location lookup returned no usable result.');
    reverseCache.set(key, result);
    return result;
  });
  lookupQueue = task.catch(() => {});
  return task;
}
