"""
DEVINA - WOMEN'S SAFETY MAP
============================

"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import requests
import threading
import time
from safety_engine import calculate_safety_score
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'paddos-safety-key-2025'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

active_sessions = {}
session_lock = threading.Lock()


def get_location_multi_source():
    """Detecting location with fallback"""
    apis = [
        {
            'url': 'https://ipapi.co/json/',
            'parse': lambda d: {
                'lat': d.get('latitude'), 'lon': d.get('longitude'),
                'city': d.get('city', 'Unknown'), 'country': d.get('country_name', 'Unknown'),
                'code': d.get('country_code', 'XX')
            }
        },
        {
            'url': 'http://ip-api.com/json/',
            'parse': lambda d: {
                'lat': d.get('lat'), 'lon': d.get('lon'),
                'city': d.get('city', 'Unknown'), 'country': d.get('country', 'Unknown'),
                'code': d.get('countryCode', 'XX')
            }
        }
    ]
    
    for api in apis:
        try:
            resp = requests.get(api['url'], timeout=5)
            if resp.status_code == 200:
                loc = api['parse'](resp.json())
                if loc['lat'] and loc['lon']:
                    return loc
        except:
            continue
    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/location')
def api_location():
    location = get_location_multi_source()
    if location:
        return jsonify({'success': True, 'data': location})
    return jsonify({'success': False, 'error': 'Location detection failed'}), 503


@app.route('/api/safety', methods=['POST'])
def api_safety():
    try:
        data = request.json
        lat = data.get('latitude')
        lon = data.get('longitude')
        country_code = data.get('country_code', 'XX')
        
        if not (lat and lon):
            return jsonify({'success': False, 'error': 'Invalid coordinates'}), 400
        
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return jsonify({'success': False, 'error': 'Coordinates out of range'}), 400
        
        result = calculate_safety_score(lat, lon, country_code)
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    print(f'✓ Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to Paddos'})


@socketio.on('disconnect')
def handle_disconnect():
    with session_lock:
        if request.sid in active_sessions:
            active_sessions[request.sid]['active'] = False
            del active_sessions[request.sid]


@socketio.on('start_monitoring')
def handle_start_monitoring(data):
    try:
        lat = data.get('latitude')
        lon = data.get('longitude')
        country_code = data.get('country_code', 'XX')
        
        if not (lat and lon):
            emit('error', {'message': 'Invalid coordinates'})
            return
        
        with session_lock:
            active_sessions[request.sid] = {
                'active': True, 'latitude': lat, 'longitude': lon,
                'country_code': country_code, 'update_count': 0
            }
        
        thread = threading.Thread(
            target=monitor_location,
            args=(request.sid, lat, lon, country_code),
            daemon=True
        )
        thread.start()
        emit('monitoring_started', {'message': 'Monitoring started'})
        
    except Exception as e:
        emit('error', {'message': str(e)})


@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    with session_lock:
        if request.sid in active_sessions:
            active_sessions[request.sid]['active'] = False
            del active_sessions[request.sid]
            emit('monitoring_stopped', {'message': 'Monitoring stopped'})


def monitor_location(session_id, lat, lon, country_code):
    while True:
        with session_lock:
            if session_id not in active_sessions or not active_sessions[session_id]['active']:
                break
        
        try:
            result = calculate_safety_score(lat, lon, country_code)
            
            with session_lock:
                if session_id in active_sessions:
                    active_sessions[session_id]['update_count'] += 1
            
            socketio.emit('safety_update', result, room=session_id)
            time.sleep(30)
            
        except Exception as e:
            print(f'Monitor error: {e}')
            time.sleep(5)


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🛡️  DEVINA - WOMEN'S SAFETY MAP".center(70))
    print("="*70)
    print("\n✓ Server starting at http://localhost:5000")
    print("✓ Press Ctrl+C to stop\n")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

