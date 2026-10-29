"""Shared Punjab geography rules for DRRAS forms and map records."""

PUNJAB_DISTRICTS = (
    'Amritsar', 'Barnala', 'Bathinda', 'Faridkot', 'Fatehgarh Sahib',
    'Fazilka', 'Ferozepur', 'Gurdaspur', 'Hoshiarpur', 'Jalandhar',
    'Kapurthala', 'Ludhiana', 'Malerkotla', 'Mansa', 'Moga',
    'Sri Muktsar Sahib', 'Pathankot', 'Patiala', 'Rupnagar',
    'Sahibzada Ajit Singh Nagar', 'Sangrur', 'Shaheed Bhagat Singh Nagar',
    'Tarn Taran',
)

# Broad state bounds used as a second check alongside the district selection.
PUNJAB_BOUNDS = {'south': 29.5, 'north': 32.6, 'west': 73.8, 'east': 76.9}


def is_punjab_coordinate(latitude, longitude):
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    return (
        PUNJAB_BOUNDS['south'] <= latitude <= PUNJAB_BOUNDS['north']
        and PUNJAB_BOUNDS['west'] <= longitude <= PUNJAB_BOUNDS['east']
    )


def format_punjab_address(address, district):
    address = str(address or '').strip().strip(',')
    district = str(district or '').strip()
    if district not in PUNJAB_DISTRICTS or not address:
        raise ValueError('Choose a Punjab district and enter a locality or address.')
    return f'{address}, {district}, Punjab'
