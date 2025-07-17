import os
import sys
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, Response
import requests

from yars import YARS
from validator import YARSValidator, ValidationError, ValidationWarning
from input_processor import SmartInputProcessor
from jobs import get_job_manager
from webhooks import get_webhook_delivery
from background_worker import start_background_worker
from formatters import OutputFormatter

app = Flask(__name__)

# Start background worker for async job processing
start_background_worker()

# Get global instances
job_manager = get_job_manager()
webhook_delivery = get_webhook_delivery()

@app.route('/api/scrape', methods=['POST'])
def scrape_reddit():
    """Enhanced scraping endpoint with new nested parameter structure and smart input processing"""
    start_time = time.time()
    
    try:
        # Get request parameters
        params = request.get_json() or {}
        
        # Validate using enhanced validator
        try:
            validated_params, warnings = YARSValidator.validate_request(params)
        except ValidationError as e:
            # Enhanced error response is already created in the validator
            if hasattr(e, 'details') and isinstance(e.details, dict):
                return jsonify(e.details), 400
            else:
                # Fallback for simple errors
                return jsonify(YARSValidator.create_error_response([
                    {"code": e.code, "message": e.message, "details": str(e.details) if e.details else ""}
                ], request_context=params)), 400
        
        # Process input sources using smart processor
        input_sources = validated_params['input']['sources']
        content_limits = validated_params['content']['limits']
        
        processed_sources, strategy = SmartInputProcessor.process_sources(input_sources, content_limits)
        
        # Check delivery mode
        delivery_mode = validated_params['output']['delivery']['mode']
        webhook_url = validated_params['output']['delivery'].get('webhookUrl')
        
        if delivery_mode == 'async':
            # Create processing report for user
            processing_report = SmartInputProcessor.create_processing_report(processed_sources, strategy)
            
            # Create async job with v2 parameters
            job_id = job_manager.create_job(validated_params, webhook_url)
            
            return jsonify({
                "jobId": job_id,
                "status": "pending",
                "message": "Job created successfully. Results will be sent to your webhook URL when complete.",
                "processingReport": processing_report,
                "webhookUrl": webhook_url,
                "statusUrl": f"/api/jobs/{job_id}",
                "estimatedDuration": f"{strategy['total_estimated_time']:.1f}s",
                "createdAt": datetime.utcnow().isoformat() + "Z",
                "warnings": [{"code": w.code, "message": w.message, "suggestion": w.suggestion} for w in warnings]
            }), 202
        
        else:
            # Synchronous processing with smart input handling
            results = {"posts": [], "comments": [], "users": [], "communities": []}
            
            # Process each source according to strategy
            miner = YARS()
            content_include = validated_params['content']['include']
            
            for source in processed_sources:
                allocated_items = strategy['distribution'].get(source.original, 0)
                if allocated_items == 0:
                    continue
                
                try:
                    if source.type.value == 'search_term':
                        # Handle search term
                        search_results = miner.search_reddit_global(
                            source.normalized,
                            limit=allocated_items,
                            sort=validated_params['input']['filters'].get('sortBy', 'relevance'),
                            time_filter=validated_params['input']['filters'].get('timeframe', 'all')
                        )
                        
                        if 'posts' in content_include:
                            results['posts'].extend(search_results[:allocated_items])
                        
                    else:
                        # Handle URL-based source
                        source_results = miner.scrape_by_urls([source.reddit_url], {
                            'maxItems': allocated_items,
                            'searchForPosts': 'posts' in content_include,
                            'searchForComments': 'comments' in content_include,
                            'searchForUsers': 'users' in content_include,
                            'searchForCommunities': 'communities' in content_include,
                            'sortSearch': validated_params['input']['filters'].get('sortBy', 'hot'),
                            'filterByDate': validated_params['input']['filters'].get('timeframe', 'all'),
                            'includeNSFW': validated_params['input']['filters'].get('includeNSFW', False)
                        })
                        
                        # Merge results
                        for content_type in ['posts', 'comments', 'users', 'communities']:
                            if content_type in content_include and content_type in source_results:
                                results[content_type].extend(source_results[content_type])
                
                except Exception as source_error:
                    # Log source error but continue with other sources
                    print(f"Error processing source {source.original}: {source_error}")
                    continue
            
            # Apply global filters
            if not validated_params['input']['filters'].get('includeNSFW', False):
                results['posts'] = [post for post in results['posts'] if not post.get('over_18', False)]
            
            # Apply total items limit
            total_limit = validated_params['content']['limits'].get('totalItems', 100)
            current_total = sum(len(results[key]) for key in results)
            
            if current_total > total_limit:
                # Trim results proportionally
                scale_factor = total_limit / current_total
                for key in results:
                    if results[key]:
                        new_length = max(1, int(len(results[key]) * scale_factor))
                        results[key] = results[key][:new_length]
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Handle output format
            output_format = validated_params['output']['format']
            
            if output_format == 'json':
                response = YARSValidator.create_success_response(
                    results, validated_params, execution_time, warnings
                )
                # Add processing report to metadata
                response['metadata']['processingReport'] = SmartInputProcessor.create_processing_report(processed_sources, strategy)
                return jsonify(response)
            else:
                # Format data according to requested format
                try:
                    response_data = YARSValidator.create_success_response(
                        results, validated_params, execution_time, warnings
                    )
                    
                    formatted_data = OutputFormatter.format_data(
                        results, 
                        output_format, 
                        response_data.get('metadata', {})
                    )
                    
                    content_type = OutputFormatter.get_content_type(output_format)
                    file_extension = OutputFormatter.get_file_extension(output_format)
                    
                    # Create filename
                    search_terms = [s.normalized for s in processed_sources if s.type.value == 'search_term']
                    if search_terms:
                        filename = f"reddit-search-{search_terms[0][:20]}.{file_extension}"
                    else:
                        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                        filename = f"reddit-data-{timestamp}.{file_extension}"
                    
                    # Sanitize filename
                    filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
                    
                    return Response(
                        formatted_data,
                        mimetype=content_type,
                        headers={
                            "Content-Disposition": f"attachment; filename={filename}",
                            "Content-Type": content_type
                        }
                    )
                except Exception as format_error:
                    return jsonify(YARSValidator.create_error_response([
                        {
                            "code": "FORMAT_ERROR",
                            "message": f"Failed to format data as {output_format}",
                            "details": "Falling back to JSON format"
                        }
                    ], warnings)), 500
        
    except Exception as e:
        # Handle unexpected errors
        execution_time = time.time() - start_time
        error_code = "UNKNOWN_ERROR"
        user_message = "An unexpected error occurred while processing your request"
        actionable_details = "Please try again or contact support if the issue persists"
        
        # Enhanced error detection
        error_str = str(e).lower()
        if "proxy" in error_str or "connection" in error_str:
            error_code = "PROXY_ERROR"
            user_message = "Proxy connection failed"
            actionable_details = "Check your proxy configuration and network connectivity"
        elif "timeout" in error_str:
            error_code = "TIMEOUT"
            user_message = "Request timed out"
            actionable_details = "Try reducing totalItems or using async delivery mode"
        elif "reddit" in error_str and ("block" in error_str or "forbidden" in error_str):
            error_code = "REDDIT_BLOCKED"
            user_message = "Reddit blocked the request"
            actionable_details = "Use a proxy or wait before retrying"
        elif "rate" in error_str and "limit" in error_str:
            error_code = "RATE_LIMITED"
            user_message = "Rate limit exceeded"
            actionable_details = "Wait a few minutes before making another request"
        
        return jsonify(YARSValidator.create_error_response([
            {
                "code": error_code,
                "message": user_message,
                "details": actionable_details
            }
        ])), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get status and details of a specific job"""
    job = job_manager.get_job(job_id)
    
    if not job:
        return jsonify({
            "success": False,
            "error": "Job not found",
            "jobId": job_id
        }), 404
    
    # Create response with job details
    response = {
        "jobId": job["id"],
        "status": job["status"],
        "createdAt": job["created_at"],
        "startedAt": job.get("started_at"),
        "completedAt": job.get("completed_at"),
        "progress": job.get("progress", 0),
        "itemsScraped": job.get("items_scraped", 0),
        "totalItems": job.get("total_items", 0),
        "webhookUrl": job.get("webhook_url")
    }
    
    # Add result data if job is completed
    if job["status"] == "completed" and job.get("result"):
        response["result"] = job["result"]
    
    # Add error if job failed
    if job["status"] == "failed" and job.get("error"):
        response["error"] = job["error"]
    
    return jsonify(response)

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List recent jobs with optional filtering"""
    limit = min(int(request.args.get('limit', 10)), 50)
    status_filter = request.args.get('status')
    
    jobs = job_manager.get_recent_jobs(limit=limit * 2)  # Get more to allow for filtering
    
    # Filter by status if specified
    if status_filter:
        jobs = [job for job in jobs if job.get("status") == status_filter]
    
    # Limit results
    jobs = jobs[:limit]
    
    # Remove sensitive data and result payload for list view
    simplified_jobs = []
    for job in jobs:
        simplified_job = {
            "jobId": job["id"],
            "status": job["status"],
            "createdAt": job["created_at"],
            "completedAt": job.get("completed_at"),
            "progress": job.get("progress", 0),
            "itemsScraped": job.get("items_scraped", 0),
            "totalItems": job.get("total_items", 0),
            "hasWebhook": bool(job.get("webhook_url"))
        }
        simplified_jobs.append(simplified_job)
    
    return jsonify({
        "jobs": simplified_jobs,
        "count": len(simplified_jobs),
        "summary": job_manager.get_jobs_summary()
    })

@app.route('/api/compare', methods=['POST'])
def compare_api_formats():
    """Compare v1 (legacy) and v2 (new) API formats and show migration path"""
    try:
        params = request.get_json() or {}
        
        # Detect format
        is_legacy = YARSValidator._is_legacy_format(params)
        
        if is_legacy:
            # Convert legacy to new format and show comparison
            original_params = params.copy()
            converted_params = YARSValidator._convert_legacy_to_new(params)
            
            # Process with smart input processor
            input_sources = converted_params['input']['sources']
            content_limits = converted_params['content']['limits']
            processed_sources, strategy = SmartInputProcessor.process_sources(input_sources, content_limits)
            
            return jsonify({
                "detectedFormat": "v1 (legacy)",
                "original": original_params,
                "converted": converted_params,
                "processingAnalysis": SmartInputProcessor.create_processing_report(processed_sources, strategy),
                "migrationNotes": [
                    "Your request uses the legacy flat parameter structure",
                    "Consider migrating to v2 nested structure for better clarity",
                    "Use /api/v2/scrape endpoint for the new format",
                    "The new format provides better parameter organization and smart input processing"
                ],
                "benefits": [
                    "Mixed URL and search term sources in single request",
                    "Clear parameter grouping (input, content, output)",
                    "Smart distribution across multiple sources", 
                    "Better validation warnings and suggestions",
                    "Processing time estimates and source analysis"
                ]
            })
        else:
            # Validate new format and show analysis
            validated_params, warnings = YARSValidator.validate_request(params)
            input_sources = validated_params['input']['sources']
            content_limits = validated_params['content']['limits']
            processed_sources, strategy = SmartInputProcessor.process_sources(input_sources, content_limits)
            
            return jsonify({
                "detectedFormat": "v2 (new)",
                "validated": validated_params,
                "warnings": [{"code": w.code, "message": w.message, "suggestion": w.suggestion} for w in warnings],
                "processingAnalysis": SmartInputProcessor.create_processing_report(processed_sources, strategy),
                "optimizations": [
                    f"Estimated processing time: {strategy['total_estimated_time']:.1f}s",
                    f"Sources will be processed in order: {strategy['processing_order']}",
                    f"Mixed mode enabled: {strategy['mixed_mode']}",
                    f"Item distribution: {strategy['distribution']}"
                ]
            })
    
    except ValidationError as e:
        return jsonify({
            "error": "VALIDATION_FAILED",
            "message": "Could not process request parameters",
            "details": e.details if hasattr(e, 'details') else str(e),
            "suggestion": "Check parameter format and try again"
        }), 400
    
    except Exception as e:
        return jsonify({
            "error": "COMPARISON_FAILED", 
            "message": "Could not compare API formats",
            "details": str(e)
        }), 500

@app.route('/api/webhook/test', methods=['POST'])
def test_webhook():
    """Test webhook URL connectivity"""
    data = request.get_json() or {}
    webhook_url = data.get('webhookUrl')
    
    if not webhook_url:
        return jsonify({
            "success": False,
            "error": "webhookUrl is required"
        }), 400
    
    # Test the webhook URL
    test_result = webhook_delivery.test_webhook_url(webhook_url)
    
    return jsonify(test_result)

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "RedditExtractor API"
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
        error_str = str(e).lower()
        if "proxy" in error_str or "connection" in error_str:
            user_message = "Proxy connection test failed"
            actionable_details = "Check your proxy configuration and network connectivity"
        elif "timeout" in error_str:
            user_message = "Proxy test timed out"
            actionable_details = "Your proxy server may be slow or unresponsive"
        else:
            user_message = "Proxy test failed"
            actionable_details = "Unable to test proxy connectivity"
            
        return jsonify({
            "success": False,
            "proxy_configured": True if hasattr(miner, 'proxy') and miner.proxy else False,
            "error": user_message,
            "details": actionable_details,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 500

@app.route('/docs')
def api_documentation():
    """Interactive API documentation page with Apify-style interface"""
    docs_html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RedditExtractor API - Interactive Documentation</title>
        <style>
            * { box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f5f7fa; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            
            /* Header */
            .header { background: linear-gradient(135deg, #FF4500, #FF6B35); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; text-align: center; }
            .header h1 { margin: 0; font-size: 2.5em; }
            .header p { margin: 10px 0 0 0; font-size: 1.2em; opacity: 0.9; }
            
            /* Main Layout */
            .main-content { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
            .left-panel, .right-panel { background: white; border-radius: 10px; padding: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            
            /* Form Styles */
            .form-group { margin-bottom: 20px; }
            .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
            .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 12px; border: 2px solid #e1e5e9; border-radius: 6px; font-size: 14px; transition: border-color 0.3s; }
            .form-group input:focus, .form-group select:focus, .form-group textarea:focus { outline: none; border-color: #FF4500; }
            .form-group small { color: #666; font-size: 12px; margin-top: 5px; display: block; }
            
            /* Checkboxes */
            .checkbox-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
            .checkbox-item { display: flex; align-items: center; }
            .checkbox-item input[type="checkbox"] { margin-right: 8px; }
            
            /* Buttons */
            .btn { padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.3s; }
            .btn-primary { background: #FF4500; color: white; }
            .btn-primary:hover { background: #e63e00; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; }
            .btn-success { background: #28a745; color: white; }
            .btn-success:hover { background: #218838; }
            
            /* Code display */
            .code-block { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 15px; margin: 10px 0; overflow-x: auto; }
            .code-block pre { margin: 0; font-family: 'Monaco', 'Menlo', monospace; font-size: 13px; line-height: 1.5; }
            
            /* Tabs */
            .tabs { display: flex; border-bottom: 2px solid #e9ecef; margin-bottom: 20px; }
            .tab { padding: 12px 20px; cursor: pointer; border: none; background: none; font-weight: 600; color: #666; }
            .tab.active { color: #FF4500; border-bottom: 2px solid #FF4500; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            
            /* Response display */
            .response-container { margin-top: 20px; }
            .response-success { background: #d4edda; border: 1px solid #c3e6cb; border-radius: 6px; padding: 15px; }
            .response-error { background: #f8d7da; border: 1px solid #f1b0b7; border-radius: 6px; padding: 15px; }
            .response-pending { background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px; padding: 15px; }
            
            /* Loading spinner */
            .spinner { border: 3px solid #f3f3f3; border-top: 3px solid #FF4500; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: inline-block; margin-right: 10px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            
            /* Responsive */
            @media (max-width: 768px) {
                .main-content { grid-template-columns: 1fr; }
                .checkbox-group { grid-template-columns: 1fr; }
            }
            
            /* Advanced options */
            .advanced-toggle { cursor: pointer; color: #FF4500; font-size: 14px; margin-top: 15px; }
            .advanced-options { display: none; margin-top: 15px; padding-top: 15px; border-top: 1px solid #e9ecef; }
            .advanced-options.show { display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔍 RedditExtractor API</h1>
                <p>Interactive API Documentation & Testing Interface</p>
            </div>
            
            <div class="main-content">
                <!-- Left Panel - Form -->
                <div class="left-panel">
                    <h2>🚀 Try the API</h2>
                    <form id="apiForm">
                        <!-- Input Sources -->
                        <div class="form-group">
                            <label>Input Type</label>
                            <select id="inputType" onchange="toggleInputType()">
                                <option value="search">Search Term</option>
                                <option value="urls">Reddit URLs</option>
                            </select>
                        </div>
                        
                        <div class="form-group" id="searchTermGroup">
                            <label for="searchTerm">Search Term</label>
                            <input type="text" id="searchTerm" placeholder="e.g., artificial intelligence, python programming">
                            <small>Search for posts across all of Reddit</small>
                        </div>
                        
                        <div class="form-group" id="urlsGroup" style="display: none;">
                            <label for="startUrls">Reddit URLs (one per line)</label>
                            <textarea id="startUrls" rows="3" placeholder="https://reddit.com/r/python
https://reddit.com/r/MachineLearning
https://reddit.com/user/someuser"></textarea>
                            <small>Enter Reddit URLs for subreddits, users, or specific posts</small>
                        </div>
                        
                        <!-- Content Types -->
                        <div class="form-group">
                            <label>Content to Include</label>
                            <div class="checkbox-group">
                                <div class="checkbox-item">
                                    <input type="checkbox" id="searchForPosts" checked>
                                    <label for="searchForPosts">Posts</label>
                                </div>
                                <div class="checkbox-item">
                                    <input type="checkbox" id="searchForComments" checked>
                                    <label for="searchForComments">Comments</label>
                                </div>
                                <div class="checkbox-item">
                                    <input type="checkbox" id="searchForUsers">
                                    <label for="searchForUsers">Users</label>
                                </div>
                                <div class="checkbox-item">
                                    <input type="checkbox" id="searchForCommunities">
                                    <label for="searchForCommunities">Communities</label>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Basic Options -->
                        <div class="form-group">
                            <label for="maxItems">Max Items</label>
                            <input type="number" id="maxItems" value="50" min="1" max="10000">
                            <small>Maximum number of items to return (1-10000)</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="sortSearch">Sort By</label>
                            <select id="sortSearch">
                                <option value="hot">Hot</option>
                                <option value="new">New</option>
                                <option value="top">Top</option>
                                <option value="rising">Rising</option>
                                <option value="relevance">Relevance</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label for="filterByDate">Time Filter</label>
                            <select id="filterByDate">
                                <option value="all">All Time</option>
                                <option value="hour">Past Hour</option>
                                <option value="day">Past Day</option>
                                <option value="week">Past Week</option>
                                <option value="month">Past Month</option>
                                <option value="year">Past Year</option>
                            </select>
                        </div>
                        
                        <!-- Advanced Options Toggle -->
                        <div class="advanced-toggle" onclick="toggleAdvanced()">
                            ⚙️ Advanced Options
                        </div>
                        
                        <div class="advanced-options" id="advancedOptions">
                            <div class="form-group">
                                <label for="outputFormat">Output Format</label>
                                <select id="outputFormat">
                                    <option value="json">JSON</option>
                                    <option value="csv">CSV</option>
                                    <option value="rss">RSS</option>
                                    <option value="xml">XML</option>
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label for="webhookUrl">Webhook URL (for async processing)</label>
                                <input type="url" id="webhookUrl" placeholder="https://your-webhook.com/endpoint">
                                <small>Leave empty for synchronous processing</small>
                            </div>
                            
                            <div class="form-group">
                                <div class="checkbox-item">
                                    <input type="checkbox" id="includeNSFW">
                                    <label for="includeNSFW">Include NSFW Content</label>
                                </div>
                            </div>
                            
                            <div class="form-group">
                                <div class="checkbox-item">
                                    <input type="checkbox" id="skipComments">
                                    <label for="skipComments">Skip Comments (faster processing)</label>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Action Buttons -->
                        <div style="margin-top: 25px;">
                            <button type="button" class="btn btn-primary" onclick="makeRequest()">
                                🚀 Run API Call
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="generateJSON()" style="margin-left: 10px;">
                                📋 Generate JSON
                            </button>
                            <button type="button" class="btn btn-success" onclick="copyJSON()" style="margin-left: 10px;">
                                📄 Copy JSON
                            </button>
                        </div>
                    </form>
                </div>
                
                <!-- Right Panel - Response -->
                <div class="right-panel">
                    <div class="tabs">
                        <button class="tab active" onclick="showTab('response')">Response</button>
                        <button class="tab" onclick="showTab('json')">JSON Body</button>
                        <button class="tab" onclick="showTab('curl')">cURL</button>
                    </div>
                    
                    <div id="response-tab" class="tab-content active">
                        <div id="responseContainer">
                            <div style="text-align: center; padding: 40px; color: #666;">
                                <h3>👆 Configure your request and click "Run API Call"</h3>
                                <p>The response will appear here</p>
                            </div>
                        </div>
                    </div>
                    
                    <div id="json-tab" class="tab-content">
                        <div class="code-block">
                            <pre id="jsonOutput">{
  "searchTerm": "artificial intelligence",
  "maxItems": 50,
  "sortSearch": "hot",
  "filterByDate": "all",
  "searchForPosts": true,
  "searchForComments": true
}</pre>
                        </div>
                    </div>
                    
                    <div id="curl-tab" class="tab-content">
                        <div class="code-block">
                            <pre id="curlOutput">curl -X POST "{{BASE_URL}}/api/scrape" \\
  -H "Content-Type: application/json" \\
  -d '{
    "searchTerm": "artificial intelligence",
    "maxItems": 50,
    "sortSearch": "hot",
    "filterByDate": "all",
    "searchForPosts": true,
    "searchForComments": true
  }'</pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let currentRequest = null;
            
            function toggleInputType() {
                const inputType = document.getElementById('inputType').value;
                const searchGroup = document.getElementById('searchTermGroup');
                const urlsGroup = document.getElementById('urlsGroup');
                
                if (inputType === 'search') {
                    searchGroup.style.display = 'block';
                    urlsGroup.style.display = 'none';
                } else {
                    searchGroup.style.display = 'none';
                    urlsGroup.style.display = 'block';
                }
                
                generateJSON();
            }
            
            function toggleAdvanced() {
                const options = document.getElementById('advancedOptions');
                options.classList.toggle('show');
            }
            
            function showTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Show selected tab
                document.getElementById(tabName + '-tab').classList.add('active');
                event.target.classList.add('active');
            }
            
            function generateJSON() {
                const inputType = document.getElementById('inputType').value;
                const requestBody = {};
                
                // Input sources
                if (inputType === 'search') {
                    const searchTerm = document.getElementById('searchTerm').value;
                    if (searchTerm) requestBody.searchTerm = searchTerm;
                } else {
                    const urls = document.getElementById('startUrls').value;
                    if (urls) {
                        requestBody.startUrls = urls.split('\\n').filter(url => url.trim());
                    }
                }
                
                // Content types
                requestBody.searchForPosts = document.getElementById('searchForPosts').checked;
                requestBody.searchForComments = document.getElementById('searchForComments').checked;
                requestBody.searchForUsers = document.getElementById('searchForUsers').checked;
                requestBody.searchForCommunities = document.getElementById('searchForCommunities').checked;
                
                // Basic options
                requestBody.maxItems = parseInt(document.getElementById('maxItems').value);
                requestBody.sortSearch = document.getElementById('sortSearch').value;
                requestBody.filterByDate = document.getElementById('filterByDate').value;
                
                // Advanced options
                requestBody.outputFormat = document.getElementById('outputFormat').value;
                requestBody.includeNSFW = document.getElementById('includeNSFW').checked;
                requestBody.skipComments = document.getElementById('skipComments').checked;
                
                const webhookUrl = document.getElementById('webhookUrl').value;
                if (webhookUrl) requestBody.webhookUrl = webhookUrl;
                
                // Update JSON display
                document.getElementById('jsonOutput').textContent = JSON.stringify(requestBody, null, 2);
                
                // Update cURL display
                const curlCommand = `curl -X POST "${window.location.origin}/api/scrape" \\\\
  -H "Content-Type: application/json" \\\\
  -d '${JSON.stringify(requestBody, null, 2)}'`;
                document.getElementById('curlOutput').textContent = curlCommand;
                
                return requestBody;
            }
            
            function copyJSON() {
                const jsonText = document.getElementById('jsonOutput').textContent;
                navigator.clipboard.writeText(jsonText).then(() => {
                    alert('JSON copied to clipboard!');
                });
            }
            
            async function makeRequest() {
                const requestBody = generateJSON();
                const responseContainer = document.getElementById('responseContainer');
                
                // Show loading state
                responseContainer.innerHTML = `
                    <div class="response-pending">
                        <div class="spinner"></div>
                        Making API request...
                    </div>
                `;
                
                try {
                    const response = await fetch('/api/scrape', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(requestBody)
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        responseContainer.innerHTML = `
                            <div class="response-success">
                                <h4>✅ Success (${response.status})</h4>
                                <div class="code-block">
                                    <pre>${JSON.stringify(data, null, 2)}</pre>
                                </div>
                            </div>
                        `;
                    } else {
                        responseContainer.innerHTML = `
                            <div class="response-error">
                                <h4>❌ Error (${response.status})</h4>
                                <div class="code-block">
                                    <pre>${JSON.stringify(data, null, 2)}</pre>
                                </div>
                            </div>
                        `;
                    }
                } catch (error) {
                    responseContainer.innerHTML = `
                        <div class="response-error">
                            <h4>❌ Network Error</h4>
                            <p>Failed to make request: ${error.message}</p>
                        </div>
                    `;
                }
            }
            
            // Generate initial JSON
            document.addEventListener('DOMContentLoaded', () => {
                generateJSON();
                
                // Add event listeners to form fields
                document.querySelectorAll('input, select, textarea').forEach(field => {
                    field.addEventListener('input', generateJSON);
                    field.addEventListener('change', generateJSON);
                });
            });
        </script>
    </body>
    </html>
    '''
    return docs_html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)