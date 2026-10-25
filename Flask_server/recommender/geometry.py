"""Great-circle kilometres; these estimates do not model roads or travel time."""
import numpy as np


def distances_from(start, coordinates):
    coordinates = np.asarray(coordinates, dtype=float).reshape(-1, 2)
    a = np.radians(np.asarray(start, dtype=float))
    b = np.radians(coordinates)
    d = b - a
    h = np.sin(d[:, 0] / 2)**2 + np.cos(a[0]) * np.cos(b[:, 0]) * np.sin(d[:, 1] / 2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def route_metrics(course, start):
    current, legs = start, []
    for place in course:
        point = (place['latitude'], place['longitude'])
        legs.append(float(distances_from(current, [point])[0]))
        current = point
    return {'distance_method': 'coordinate_great_circle',
            'estimated_distance_km': round(sum(legs), 3),
            'leg_distances_km': [round(x, 3) for x in legs],
            'travel_time_minutes': None}


def greedy_tsp(records, start):
    """Nearest-neighbour ordering for spot recommendations, not slot courses."""
    remaining, route = list(records), []
    while remaining:
        idx = int(np.argmin(distances_from(start, [(p['latitude'], p['longitude']) for p in remaining])))
        place = remaining.pop(idx)
        route.append(place)
        start = (place['latitude'], place['longitude'])
    return route
