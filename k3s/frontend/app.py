from flask import Flask, send_from_directory, request, Response
import requests
import os

app = Flask(__name__, static_folder='static')

# Use short service name (k8s will resolve within same namespace)
API_URL = os.getenv('API_URL', 'http://rpod-api:6124')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_proxy(path):
    """Proxy API requests to backend"""
    url = f"{API_URL}/{path}"
    
    try:
        # Forward the request
        if request.method == 'POST':
            resp = requests.post(url, data=request.form, timeout=30)
        elif request.method == 'GET':
            resp = requests.get(url, params=request.args, timeout=30)
        elif request.method == 'PUT':
            resp = requests.put(url, data=request.data, timeout=30)
        elif request.method == 'DELETE':
            resp = requests.delete(url, timeout=30)
        
        # Return response
        return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))
    except Exception as e:
        app.logger.error(f"API proxy error: {e}")
        return Response(f"API connection error: {str(e)}", status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
