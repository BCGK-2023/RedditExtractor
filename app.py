import os
import sys
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import requests

current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
sys.path.append(src_path)

from yars.yars import YARS
from yars.validator import YARSValidator, ValidationError

app = Flask(__name__)

@app.route('/api/scrape', methods=['POST'])
def scrape_reddit():
    """Main scraping endpoint with full parameter support"""
    start_time = time.time()
    
    try:
        # Get request parameters
        params = request.get_json() or {}
        
        # Validate parameters
        try:
            validated_params = YARSValidator.validate_scrape_params(params)
        except ValidationError as e:
            if hasattr(e, 'details') and isinstance(e.details, list):
                return jsonify(YARSValidator.create_error_response(e.details, params)), 400
            else:
                return jsonify(YARSValidator.create_error_response([
                    {"code": e.code, "message": e.message, "details": e.details or ""}
                ], params)), 400
        
        # Initialize YARS with proxy support
        miner = YARS()
        
        # Determine scraping method based on parameters
        if validated_params.get('startUrls'):
            # URL-based scraping
            results = miner.scrape_by_urls(validated_params['startUrls'], validated_params)
        elif validated_params.get('searchTerm'):
            # Search-based scraping
            search_results = miner.search_reddit_global(
                validated_params['searchTerm'],
                limit=validated_params.get('maxItems', 100),
                sort=validated_params.get('sortSearch', 'relevance'),
                time_filter=validated_params.get('filterByDate', 'all')
            )
            
            # Filter results based on parameters
            results = {
                "posts": search_results if validated_params.get('searchForPosts', True) else [],
                "comments": [],
                "users": [],
                "communities": []
            }
            
            # Get comments for posts if requested
            if validated_params.get('searchForComments', True) and not validated_params.get('skipComments', False):
                for post in results['posts'][:5]:  # Limit comment scraping to first 5 posts
                    if post.get('permalink'):
                        post_details = miner.scrape_post_details(post['permalink'])
                        if post_details and post_details.get('comments'):
                            results['comments'].extend(post_details['comments'][:validated_params.get('commentsPerPage', 20)])
        else:
            # This shouldn't happen due to validation, but handle gracefully
            return jsonify(YARSValidator.create_error_response([
                {"code": "INVALID_PARAMS", "message": "No valid input source provided", "details": ""}
            ], params)), 400
        
        # Apply NSFW filtering if needed
        if not validated_params.get('includeNSFW', False):
            results['posts'] = [post for post in results['posts'] if not post.get('over_18', False)]
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Create success response
        response = YARSValidator.create_success_response(results, validated_params, execution_time)
        
        return jsonify(response)
        
    except Exception as e:
        # Handle unexpected errors
        execution_time = time.time() - start_time
        error_code = "UNKNOWN_ERROR"
        
        # Determine error type
        if "proxy" in str(e).lower():
            error_code = "PROXY_ERROR"
        elif "timeout" in str(e).lower():
            error_code = "TIMEOUT"
        elif "reddit" in str(e).lower() and "block" in str(e).lower():
            error_code = "REDDIT_BLOCKED"
        elif "rate" in str(e).lower() and "limit" in str(e).lower():
            error_code = "RATE_LIMITED"
        
        error_response = YARSValidator.create_error_response([
            {
                "code": error_code,
                "message": str(e),
                "details": f"Execution time: {execution_time:.2f}s"
            }
        ], params)
        
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

@app.route('/docs')
def api_documentation():
    """API documentation page"""
    docs_html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>YARS Reddit Scraper API Documentation</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { background: #FF4500; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
            .endpoint { background: #f5f5f5; padding: 15px; margin: 20px 0; border-left: 4px solid #FF4500; }
            .method { background: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-weight: bold; }
            .method.get { background: #007bff; }
            .method.post { background: #28a745; }
            .params { background: #e9ecef; padding: 10px; margin: 10px 0; border-radius: 3px; }
            .param { margin: 5px 0; }
            .param-name { font-weight: bold; color: #0066cc; }
            .param-type { color: #666; font-style: italic; }
            .example { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
            .response { background: #d4edda; padding: 10px; border-radius: 3px; }
            .error { background: #f8d7da; padding: 10px; border-radius: 3px; }
            code { background: #f8f9fa; padding: 2px 5px; border-radius: 3px; }
            pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
            .toc { background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            .toc ul { list-style-type: none; padding-left: 0; }
            .toc li { margin: 5px 0; }
            .toc a { text-decoration: none; color: #0066cc; }
            .toc a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 YARS Reddit Scraper API</h1>
            <p>Professional Reddit scraping API with proxy support and n8n compatibility</p>
        </div>
        
        <div class="toc">
            <h2>📋 Table of Contents</h2>
            <ul>
                <li><a href="#overview">Overview</a></li>
                <li><a href="#endpoints">API Endpoints</a></li>
                <li><a href="#parameters">Parameters Reference</a></li>
                <li><a href="#examples">Usage Examples</a></li>
                <li><a href="#n8n">n8n Integration</a></li>
                <li><a href="#errors">Error Handling</a></li>
            </ul>
        </div>
        
        <section id="overview">
            <h2>📖 Overview</h2>
            <p>YARS is a professional Reddit scraping API that provides structured access to Reddit content with proxy support and comprehensive parameter control. Perfect for automation workflows and data collection.</p>
            
            <h3>✨ Features</h3>
            <ul>
                <li>🔄 Proxy support with DataImpulse integration</li>
                <li>🎯 URL-based and search-based scraping</li>
                <li>📊 Structured JSON responses</li>
                <li>🔧 Comprehensive parameter control</li>
                <li>⚡ n8n and automation-friendly</li>
                <li>📈 Built-in error handling and logging</li>
            </ul>
        </section>
        
        <section id="endpoints">
            <h2>🔌 API Endpoints</h2>
            
            <div class="endpoint">
                <h3><span class="method post">POST</span> /api/scrape</h3>
                <p><strong>Main scraping endpoint</strong> - Scrape Reddit content with full parameter support</p>
                <div class="params">
                    <strong>Content-Type:</strong> application/json<br>
                    <strong>Request Body:</strong> JSON object with scraping parameters
                </div>
            </div>
            
            <div class="endpoint">
                <h3><span class="method get">GET</span> /health</h3>
                <p><strong>Health check</strong> - Verify API status and connectivity</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method get">GET</span> /test-proxy</h3>
                <p><strong>Proxy test</strong> - Test proxy connectivity and current IP</p>
            </div>
        </section>
        
        <section id="parameters">
            <h2>⚙️ Parameters Reference</h2>
            
            <h3>Input Sources (Choose One)</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">startUrls</span> <span class="param-type">Array</span><br>
                    List of Reddit URLs to scrape (subreddits, users, posts)<br>
                    Example: <code>["https://reddit.com/r/python", "https://reddit.com/user/someuser"]</code>
                </div>
                <div class="param">
                    <span class="param-name">searchTerm</span> <span class="param-type">String</span><br>
                    Search query to find posts across Reddit<br>
                    Example: <code>"machine learning"</code>
                </div>
            </div>
            
            <h3>Content Control</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">searchForPosts</span> <span class="param-type">Boolean</span> (default: true)<br>
                    Include posts in results
                </div>
                <div class="param">
                    <span class="param-name">searchForComments</span> <span class="param-type">Boolean</span> (default: true)<br>
                    Include comments in results
                </div>
                <div class="param">
                    <span class="param-name">skipComments</span> <span class="param-type">Boolean</span> (default: false)<br>
                    Skip comment scraping for better performance
                </div>
                <div class="param">
                    <span class="param-name">includeNSFW</span> <span class="param-type">Boolean</span> (default: false)<br>
                    Include NSFW content in results
                </div>
            </div>
            
            <h3>Sorting and Filtering</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">sortSearch</span> <span class="param-type">String</span> (default: "hot")<br>
                    Options: "hot", "new", "top", "rising", "relevance"
                </div>
                <div class="param">
                    <span class="param-name">filterByDate</span> <span class="param-type">String</span> (default: "all")<br>
                    Options: "hour", "day", "week", "month", "year", "all"
                </div>
                <div class="param">
                    <span class="param-name">postDateLimit</span> <span class="param-type">String</span> (optional)<br>
                    ISO date string to filter posts after this date<br>
                    Example: <code>"2024-01-01"</code> or <code>"2024-01-01T00:00:00Z"</code>
                </div>
            </div>
            
            <h3>Limits and Pagination</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">maxItems</span> <span class="param-type">Integer</span> (default: 100, max: 10000)<br>
                    Maximum total items to return
                </div>
                <div class="param">
                    <span class="param-name">postsPerPage</span> <span class="param-type">Integer</span> (default: 25, max: 100)<br>
                    Posts per page for pagination
                </div>
                <div class="param">
                    <span class="param-name">commentsPerPage</span> <span class="param-type">Integer</span> (default: 20, max: 100)<br>
                    Comments per page for pagination
                </div>
            </div>
        </section>
        
        <section id="examples">
            <h2>💡 Usage Examples</h2>
            
            <h3>Example 1: Scrape Subreddit Posts</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
POST /api/scrape
Content-Type: application/json

{
  "startUrls": ["https://reddit.com/r/python"],
  "searchForPosts": true,
  "maxItems": 50,
  "sortSearch": "hot",
  "filterByDate": "week"
}
                </pre>
            </div>
            
            <h3>Example 2: Search Across Reddit</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
POST /api/scrape
Content-Type: application/json

{
  "searchTerm": "artificial intelligence",
  "searchForPosts": true,
  "sortSearch": "relevance",
  "filterByDate": "month",
  "maxItems": 200
}
                </pre>
            </div>
            
            <h3>Example 3: User Posts Only</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
POST /api/scrape
Content-Type: application/json

{
  "startUrls": ["https://reddit.com/user/someuser"],
  "searchForPosts": true,
  "skipComments": true,
  "maxItems": 100
}
                </pre>
            </div>
        </section>
        
        <section id="n8n">
            <h2>🔗 n8n Integration</h2>
            <p>YARS is designed to work seamlessly with n8n workflows:</p>
            
            <div class="example">
                <strong>n8n HTTP Request Node Configuration:</strong>
                <pre>
Method: POST
URL: https://your-app.railway.app/api/scrape
Content-Type: application/json
Body: 
{
  "startUrls": ["https://reddit.com/r/{{$json.subreddit}}"],
  "maxItems": {{$json.limit}},
  "sortSearch": "{{$json.sort}}"
}
                </pre>
            </div>
            
            <p>The structured response format makes it easy to process results in subsequent n8n nodes.</p>
        </section>
        
        <section id="errors">
            <h2>🚨 Error Handling</h2>
            
            <h3>Error Response Format</h3>
            <div class="error">
                <pre>
{
  "success": false,
  "data": null,
  "metadata": {
    "requestParams": {...},
    "scrapedAt": "2025-07-16T17:00:07Z"
  },
  "errors": [
    {
      "code": "PROXY_ERROR",
      "message": "Proxy connection failed",
      "details": "Connection timeout after 10 seconds"
    }
  ]
}
                </pre>
            </div>
            
            <h3>Error Codes</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">PROXY_ERROR</span> - Proxy connection issues
                </div>
                <div class="param">
                    <span class="param-name">REDDIT_BLOCKED</span> - Reddit blocking requests
                </div>
                <div class="param">
                    <span class="param-name">INVALID_PARAMS</span> - Parameter validation failed
                </div>
                <div class="param">
                    <span class="param-name">TIMEOUT</span> - Request timeout
                </div>
                <div class="param">
                    <span class="param-name">RATE_LIMITED</span> - Reddit rate limiting
                </div>
            </div>
        </section>
        
        <footer style="margin-top: 50px; text-align: center; color: #666;">
            <p>🚀 YARS Reddit Scraper API - Built for Railway Template Marketplace</p>
        </footer>
    </body>
    </html>
    '''
    return docs_html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)