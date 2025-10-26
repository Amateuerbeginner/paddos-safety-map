"""
PADDOS SAFETY ENGINE
====================
Advanced safety calculation with service availability detection
"""

import requests
import math
from datetime import datetime
from typing import Dict, List, Tuple

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
TIMEOUT = 15

COUNTRY_BASELINES = {
    'NO': 1.18, 'SE': 1.16, 'DK': 1.16, 'FI': 1.17, 'CH': 1.15,
    'CA': 1.11, 'DE': 1.10, 'AU': 1.09, 'GB': 1.08, 'US': 1.04,
    'IN': 0.88, 'BR': 0.89, 'CN': 0.94, 'MX': 0.84, 'DEFAULT': 1.00
}

WEIGHTS = {
    'temporal_risk': 0.28,
    'emergency_proximity': 0.27,
    'population_density': 0.25,
    'infrastructure': 0.20
}


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance"""
    try:
        R = 6371
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        Δφ, Δλ = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(Δφ/2)**2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except:
        return float('inf')


def fetch_osm_data(query: str) -> Tuple[List[Dict], bool]:
    """Fetch OSM data with success indicator"""
    try:
        response = requests.post(OVERPASS_URL, data={'data': query}, timeout=TIMEOUT)
        if response.status_code == 200:
            elements = response.json().get('elements', [])
            return elements, True
        return [], False
    except:
        return [], False


def get_nearby_places(lat: float, lon: float, place_type: str, radius: int) -> Tuple[List[Dict], bool]:
    """Get nearby places with success status"""
    queries = {
        'hospital': f'node["amenity"="hospital"](around:{radius},{lat},{lon}); way["amenity"="hospital"](around:{radius},{lat},{lon});',
        'police': f'node["amenity"="police"](around:{radius},{lat},{lon}); way["amenity"="police"](around:{radius},{lat},{lon});',
        'bus_stop': f'node["highway"="bus_stop"](around:{radius},{lat},{lon});',
        'train': f'node["railway"="station"](around:{radius},{lat},{lon});',
        'activity': f'node["shop"](around:{radius},{lat},{lon}); node["amenity"="restaurant"](around:{radius},{lat},{lon});',
        'infrastructure': f'node["highway"="street_lamp"](around:{radius},{lat},{lon}); way["lit"="yes"](around:{radius},{lat},{lon});'
    }
    
    if place_type not in queries:
        return [], False
    
    query = f"[out:json][timeout:{TIMEOUT}]; ({queries[place_type]}); out center;"
    elements, success = fetch_osm_data(query)
    
    if not success:
        return [], False
    
    places = []
    for elem in elements:
        try:
            e_lat = elem.get('lat') or elem.get('center', {}).get('lat')
            e_lon = elem.get('lon') or elem.get('center', {}).get('lon')
            
            if not (e_lat and e_lon):
                continue
            
            dist = calculate_distance(lat, lon, e_lat, e_lon)
            if dist == float('inf'):
                continue
            
            name = elem.get('tags', {}).get('name', f'{place_type.title()}')
            
            places.append({
                'name': name,
                'type': place_type,
                'distance': round(dist, 2),
                'latitude': e_lat,
                'longitude': e_lon
            })
        except:
            continue
    
    return sorted(places, key=lambda x: x['distance']), True


def calculate_safety_score(lat: float, lon: float, country_code: str = 'XX') -> Dict:
    """
    Calculate safety score with service availability detection
    """
    
    print(f"\n{'='*70}")
    print(f"PADDOS: Calculating for ({lat:.4f}, {lon:.4f})")
    print(f"{'='*70}")
    
    try:
        # Time-based risk (always available)
        hour = datetime.now().hour
        if 9 <= hour <= 18:
            time_score, period = 88, f"{hour}:00 - Low Risk"
        elif 7 <= hour < 9 or 18 < hour <= 20:
            time_score, period = 62, f"{hour}:00 - Moderate Risk"
        else:
            time_score, period = 25, f"{hour}:00 - High Risk"
        
        print(f"✓ Time: {time_score}")
        
        # Get data with success tracking
        hospitals, hosp_success = get_nearby_places(lat, lon, 'hospital', 5000)
        police, police_success = get_nearby_places(lat, lon, 'police', 5000)
        bus_stops, bus_success = get_nearby_places(lat, lon, 'bus_stop', 1000)
        trains, train_success = get_nearby_places(lat, lon, 'train', 2000)
        activity, activity_success = get_nearby_places(lat, lon, 'activity', 600)
        infra, infra_success = get_nearby_places(lat, lon, 'infrastructure', 500)
        
        # Check if minimum required data is available
        services_available = (hosp_success or police_success) and activity_success
        
        if not services_available:
            print("✗ Minimum required data NOT available")
            return {
                'score': 0,
                'rating': "SERVICE UNAVAILABLE",
                'color': "#999999",
                'confidence': 0,
                'timestamp': datetime.now().isoformat(),
                'breakdown': {
                    'temporal_risk': 0,
                    'emergency_proximity': 0,
                    'population_density': 0,
                    'infrastructure': 0
                },
                'time_period': period,
                'service_status': {
                    'overall': "Sorry, we don't have services running for this location",
                    'status_color': "#f44336",
                    'unavailable': ['emergency_services', 'activity_data'],
                    'message': "Paddos is not available in this area yet. We're working to expand our coverage!"
                },
                'nearest': {
                    'hospital': None,
                    'police': None,
                    'bus_stop': None,
                    'train_station': None
                },
                'all_places': {
                    'hospitals': [],
                    'police_stations': [],
                    'bus_stops': [],
                    'train_stations': []
                },
                'stats': {
                    'activity_count': 0,
                    'infrastructure_count': 0,
                    'emergency_services_density': 0
                }
            }
        
        print(f"✓ Data: {len(hospitals)} hospitals, {len(police)} police, {len(activity)} activity")
        
        # Emergency proximity
        emergency = hospitals + police
        if emergency:
            min_dist = min(p['distance'] for p in emergency)
            if min_dist <= 0.8:
                emerg_score = 96
            elif min_dist <= 1.5:
                emerg_score = 85
            elif min_dist <= 2.5:
                emerg_score = 70
            elif min_dist <= 4.0:
                emerg_score = 50
            else:
                emerg_score = 30
        else:
            emerg_score = 22
        
        # Population density
        act_count = len(activity)
        if act_count >= 60:
            pop_score = 92
        elif act_count >= 40:
            pop_score = 82
        elif act_count >= 25:
            pop_score = 68
        elif act_count >= 12:
            pop_score = 50
        else:
            pop_score = 35
        
        if hour < 6 or hour > 22:
            pop_score *= 0.7
        
        # Infrastructure
        infra_count = len(infra) + len(bus_stops) + len(trains)
        if 6 <= hour <= 19:
            infra_score = 80 if infra_count >= 20 else 65
        else:
            if infra_count >= 20:
                infra_score = 85
            elif infra_count >= 10:
                infra_score = 60
            else:
                infra_score = 30
        
        # Calculate weighted score
        raw_score = (
            time_score * WEIGHTS['temporal_risk'] +
            emerg_score * WEIGHTS['emergency_proximity'] +
            pop_score * WEIGHTS['population_density'] +
            infra_score * WEIGHTS['infrastructure']
        )
        
        multiplier = COUNTRY_BASELINES.get(country_code.upper(), COUNTRY_BASELINES['DEFAULT'])
        final_score = min(max(raw_score * multiplier, 0), 100)
        
        # Rating
        if final_score >= 75:
            rating, color = "SAFE", "#4CAF50"
        elif final_score >= 55:
            rating, color = "MODERATE", "#FFC107"
        elif final_score >= 35:
            rating, color = "CAUTION", "#FF9800"
        else:
            rating, color = "HIGH RISK", "#F44336"
        
        print(f"✓ Final: {final_score:.1f} ({rating})\n")
        
        # Calculate confidence
        data_quality = sum([hosp_success, police_success, activity_success, infra_success]) / 4
        confidence = round(data_quality * 85, 1)
        
        # Service status
        unavailable = []
        if not hosp_success and not police_success:
            unavailable.append('emergency_services')
        if not activity_success:
            unavailable.append('activity_data')
        if not infra_success:
            unavailable.append('infrastructure')
        
        status_msg = "All services operational" if not unavailable else f"Limited data: {', '.join(unavailable)}"
        status_color = "#4CAF50" if not unavailable else "#FF9800"
        
        return {
            'score': round(final_score, 1),
            'rating': rating,
            'color': color,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'breakdown': {
                'temporal_risk': round(time_score, 1),
                'emergency_proximity': round(emerg_score, 1),
                'population_density': round(pop_score, 1),
                'infrastructure': round(infra_score, 1)
            },
            'time_period': period,
            'service_status': {
                'overall': status_msg,
                'status_color': status_color,
                'unavailable': unavailable,
                'message': None
            },
            'nearest': {
                'hospital': hospitals[0] if hospitals else None,
                'police': police[0] if police else None,
                'bus_stop': bus_stops[0] if bus_stops else None,
                'train_station': trains[0] if trains else None
            },
            'all_places': {
                'hospitals': hospitals[:5],
                'police_stations': police[:5],
                'bus_stops': bus_stops[:10],
                'train_stations': trains[:5]
            },
            'stats': {
                'activity_count': act_count,
                'infrastructure_count': infra_count,
                'emergency_services_density': round(len(emergency) / 25, 2) if emergency else 0
            }
        }
        
    except Exception as e:
        print(f"✗ Critical Error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'score': 0,
            'rating': "ERROR",
            'color': "#999999",
            'confidence': 0,
            'timestamp': datetime.now().isoformat(),
            'breakdown': {
                'temporal_risk': 0,
                'emergency_proximity': 0,
                'population_density': 0,
                'infrastructure': 0
            },
            'time_period': f"{datetime.now().hour}:00",
            'service_status': {
                'overall': "System error occurred",
                'status_color': "#f44336",
                'unavailable': ['all'],
                'message': f"Error: {str(e)[:100]}"
            },
            'nearest': {'hospital': None, 'police': None, 'bus_stop': None, 'train_station': None},
            'all_places': {'hospitals': [], 'police_stations': [], 'bus_stops': [], 'train_stations': []},
            'stats': {'activity_count': 0, 'infrastructure_count': 0, 'emergency_services_density': 0}
        }
