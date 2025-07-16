import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify
import requests

current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
sys.path.append(src_path)

from yars.yars import YARS

app = Flask(__name__)

@app.route('/api/subreddit/<subreddit_name>')
def get_subreddit_posts(subreddit_name):
    try:
        limit = int(request.args.get('limit', 25))
        sort = request.args.get('sort', 'hot')
        
        # Map sort parameter to YARS category
        category_map = {
            'hot': 'hot',
            'top': 'top',
            'new': 'new'
        }
        
        category = category_map.get(sort, 'hot')
        
        # Initialize YARS with proxy support
        miner = YARS()
        
        # Fetch subreddit posts
        posts = miner.fetch_subreddit_posts(
            subreddit_name, 
            limit=limit, 
            category=category, 
            time_filter="all"
        )
        
        # Format response
        response = {
            "success": True,
            "subreddit": subreddit_name,
            "posts": posts,
            "count": len(posts),
            "scraped_at": datetime.utcnow().isoformat() + "Z"
        }
        
        return jsonify(response)
        
    except Exception as e:
        error_response = {
            "success": False,
            "error": str(e),
            "subreddit": subreddit_name,
            "posts": [],
            "count": 0,
            "scraped_at": datetime.utcnow().isoformat() + "Z"
        }
        return jsonify(error_response), 500

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "YARS Reddit Scraper"
    })

@app.route('/test-proxy')
def test_proxy():
    try:
        # Initialize YARS to test proxy connectivity
        miner = YARS()
        
        # Test proxy by making a request to a simple endpoint
        if miner.proxy:
            # Use the same session that YARS uses to test proxy
            response = miner.session.get('https://httpbin.org/ip', timeout=10)
            response.raise_for_status()
            ip_data = response.json()
            
            return jsonify({
                "success": True,
                "proxy_configured": True,
                "proxy_url": miner.proxy,
                "current_ip": ip_data.get('origin', 'unknown'),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
        else:
            return jsonify({
                "success": False,
                "proxy_configured": False,
                "message": "No proxy configured",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "proxy_configured": True if hasattr(miner, 'proxy') and miner.proxy else False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)