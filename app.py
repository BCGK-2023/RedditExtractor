import os
import sys
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, Response
import requests

from yars import YARS
from validator import YARSValidator, ValidationError
from validator_v2 import RedditExtractorValidator, ValidationWarning
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

@app.route('/api/v2/scrape', methods=['POST'])
def scrape_reddit_v2():
    """Enhanced scraping endpoint with new nested parameter structure and smart input processing"""
    start_time = time.time()
    
    try:
        # Get request parameters
        params = request.get_json() or {}
        
        # Validate using new v2 validator
        try:
            validated_params, warnings = RedditExtractorValidator.validate_request(params)
        except ValidationError as e:
            # Enhanced error response is already created in the validator
            if hasattr(e, 'details') and isinstance(e.details, dict):
                return jsonify(e.details), 400
            else:
                # Fallback for simple errors
                return jsonify(RedditExtractorValidator.create_error_response([
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
                response = RedditExtractorValidator.create_success_response(
                    results, validated_params, execution_time, warnings
                )
                # Add processing report to metadata
                response['metadata']['processingReport'] = SmartInputProcessor.create_processing_report(processed_sources, strategy)
                return jsonify(response)
            else:
                # Format data according to requested format
                try:
                    response_data = RedditExtractorValidator.create_success_response(
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
                    return jsonify(RedditExtractorValidator.create_error_response([
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
        
        return jsonify(RedditExtractorValidator.create_error_response([
            {
                "code": error_code,
                "message": user_message,
                "details": actionable_details
            }
        ])), 500

@app.route('/api/scrape', methods=['POST'])
def scrape_reddit():
    """Main scraping endpoint with synchronous and asynchronous support"""
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
        
        # Check if webhookUrl is provided for async processing
        webhook_url = validated_params.get('webhookUrl')
        
        if webhook_url:
            # Asynchronous processing with webhook
            job_id = job_manager.create_job(validated_params, webhook_url)
            
            return jsonify({
                "jobId": job_id,
                "status": "pending",
                "message": "Job created successfully. Results will be sent to your webhook URL when complete.",
                "webhookUrl": webhook_url,
                "statusUrl": f"/api/jobs/{job_id}",
                "estimatedTime": f"{validated_params.get('maxItems', 100) * 0.1:.1f}s",
                "createdAt": datetime.utcnow().isoformat() + "Z"
            }), 202
        
        else:
            # Synchronous processing (original behavior)
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
            
            # Handle different output formats
            output_format = validated_params.get('outputFormat', 'json')
            
            if output_format == 'json':
                return jsonify(response)
            else:
                # Format data according to requested format
                try:
                    formatted_data = OutputFormatter.format_data(
                        results, 
                        output_format, 
                        response.get('metadata', {})
                    )
                    
                    content_type = OutputFormatter.get_content_type(output_format)
                    file_extension = OutputFormatter.get_file_extension(output_format)
                    
                    # Create filename based on search term or timestamp
                    if validated_params.get('searchTerm'):
                        filename = f"reddit-search-{validated_params['searchTerm'][:20]}.{file_extension}"
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
                    # Fall back to JSON if formatting fails
                    return jsonify(YARSValidator.create_error_response([
                        {
                            "code": "FORMAT_ERROR",
                            "message": f"Failed to format data as {output_format}",
                            "details": "Falling back to JSON format"
                        }
                    ], validated_params)), 500
        
    except Exception as e:
        # Handle unexpected errors
        execution_time = time.time() - start_time
        error_code = "UNKNOWN_ERROR"
        user_message = "An unexpected error occurred while processing your request"
        actionable_details = "Please try again or contact support if the issue persists"
        
        # Determine error type and provide actionable messages
        error_str = str(e).lower()
        if "proxy" in error_str or "connection" in error_str:
            error_code = "PROXY_ERROR"
            user_message = "Proxy connection failed"
            actionable_details = "Check your proxy configuration and network connectivity"
        elif "timeout" in error_str:
            error_code = "TIMEOUT"
            user_message = "Request timed out"
            actionable_details = "Try reducing maxItems or check your network connection"
        elif "reddit" in error_str and ("block" in error_str or "forbidden" in error_str):
            error_code = "REDDIT_BLOCKED"
            user_message = "Reddit blocked the request"
            actionable_details = "Use a proxy or wait before retrying"
        elif "rate" in error_str and "limit" in error_str:
            error_code = "RATE_LIMITED"
            user_message = "Rate limit exceeded"
            actionable_details = "Wait a few minutes before making another request"
        elif "json" in error_str or "parse" in error_str:
            error_code = "INVALID_RESPONSE"
            user_message = "Invalid response from Reddit"
            actionable_details = "The requested content may not exist or be available"
        
        error_response = YARSValidator.create_error_response([
            {
                "code": error_code,
                "message": user_message,
                "details": actionable_details
            }
        ], params)
        
        return jsonify(error_response), 500

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
        is_legacy = RedditExtractorValidator._is_legacy_format(params)
        
        if is_legacy:
            # Convert legacy to new format and show comparison
            original_params = params.copy()
            converted_params = RedditExtractorValidator._convert_legacy_to_new(params)
            
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
            validated_params, warnings = RedditExtractorValidator.validate_request(params)
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
    """API documentation page"""
    docs_html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RedditExtractor API Documentation</title>
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
            <h1>🔍 RedditExtractor API</h1>
            <p>A professional, proxy-enabled Reddit scraping API designed for the modern automation stack</p>
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
            <p>RedditExtractor is a powerful, production-ready API for scraping Reddit. It comes with full proxy support, a flexible API for fetching posts, comments, and user data, and is designed for seamless integration with n8n, Zapier, or any custom workflow.</p>
            
            <p><strong>This is the first tool in the Extractor Suite</strong> - a series of professional scraping APIs designed for the modern automation stack.</p>
            
            <h3>✨ Features</h3>
            <ul>
                <li>🔄 Proxy support for production use</li>
                <li>🎯 URL-based and search-based scraping</li>
                <li>📊 Multiple output formats (JSON, CSV, RSS, XML)</li>
                <li>🔄 Asynchronous processing with webhooks</li>
                <li>📈 Job queue and progress tracking</li>
                <li>🔧 Comprehensive parameter control</li>
                <li>⚡ Perfect for n8n, Zapier, and custom workflows</li>
                <li>🛡️ Built-in error handling and logging</li>
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
                <h3><span class="method get">GET</span> /api/jobs/{jobId}</h3>
                <p><strong>Job status</strong> - Get status and details of a specific job</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method get">GET</span> /api/jobs</h3>
                <p><strong>List jobs</strong> - Get recent jobs with optional status filtering</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method post">POST</span> /api/webhook/test</h3>
                <p><strong>Test webhook</strong> - Test webhook URL connectivity</p>
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
            
            <h3>Output and Delivery</h3>
            <div class="params">
                <div class="param">
                    <span class="param-name">outputFormat</span> <span class="param-type">String</span> (default: "json")<br>
                    Output format for the response data<br>
                    Options: "json", "csv", "rss", "xml"<br>
                    Note: Non-JSON formats will be returned as downloadable files
                </div>
                <div class="param">
                    <span class="param-name">webhookUrl</span> <span class="param-type">String</span> (optional)<br>
                    URL to receive webhook when job completes (enables async processing)<br>
                    Example: <code>"https://your-webhook.com/reddit-results"</code>
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
            
            <h3>Example 1: Synchronous Scraping</h3>
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
            
            <h3>Example 2: Asynchronous Scraping with Webhook</h3>
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
  "maxItems": 5000,
  "webhookUrl": "https://your-webhook.com/reddit-results"
}
                </pre>
                <strong>Response (202 Accepted):</strong>
                <pre>
{
  "jobId": "abc-123-def",
  "status": "pending",
  "statusUrl": "/api/jobs/abc-123-def",
  "webhookUrl": "https://your-webhook.com/reddit-results"
}
                </pre>
            </div>
            
            <h3>Example 3: CSV Export</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
POST /api/scrape
Content-Type: application/json

{
  "searchTerm": "python programming",
  "searchForPosts": true,
  "maxItems": 100,
  "outputFormat": "csv"
}
                </pre>
                <strong>Response:</strong> Downloads a CSV file with structured Reddit data
            </div>
            
            <h3>Example 4: RSS Feed Generation</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
POST /api/scrape
Content-Type: application/json

{
  "startUrls": ["https://reddit.com/r/technology"],
  "searchForPosts": true,
  "maxItems": 50,
  "outputFormat": "rss",
  "sortSearch": "hot"
}
                </pre>
                <strong>Response:</strong> Downloads an RSS feed suitable for feed readers
            </div>
            
            <h3>Example 5: Check Job Status</h3>
            <div class="example">
                <strong>Request:</strong>
                <pre>
GET /api/jobs/abc-123-def
                </pre>
                <strong>Response:</strong>
                <pre>
{
  "jobId": "abc-123-def",
  "status": "running",
  "progress": 45,
  "itemsScraped": 2250,
  "totalItems": 5000
}
                </pre>
            </div>
        </section>
        
        <section id="n8n">
            <h2>🔗 Automation Integration</h2>
            <p>RedditExtractor is designed to work seamlessly with automation platforms:</p>
            
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
            
            <div class="example">
                <strong>Zapier Webhook Configuration:</strong>
                <pre>
Method: POST
URL: https://your-app.railway.app/api/scrape
Headers: Content-Type: application/json
Data: 
{
  "searchTerm": "{{inputData.query}}",
  "maxItems": 50,
  "sortSearch": "relevance"
}
                </pre>
            </div>
            
            <p>The structured response format makes it easy to process results in subsequent workflow nodes.</p>
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
                    <span class="param-name">PROXY_ERROR</span> - Proxy connection issues<br>
                    <small>Action: Check proxy configuration and network connectivity</small>
                </div>
                <div class="param">
                    <span class="param-name">REDDIT_BLOCKED</span> - Reddit blocking requests<br>
                    <small>Action: Use a proxy or wait before retrying</small>
                </div>
                <div class="param">
                    <span class="param-name">INVALID_PARAMS</span> - Parameter validation failed<br>
                    <small>Action: Check parameter values and types</small>
                </div>
                <div class="param">
                    <span class="param-name">TIMEOUT</span> - Request timeout<br>
                    <small>Action: Try reducing maxItems or check network connection</small>
                </div>
                <div class="param">
                    <span class="param-name">RATE_LIMITED</span> - Reddit rate limiting<br>
                    <small>Action: Wait a few minutes before making another request</small>
                </div>
                <div class="param">
                    <span class="param-name">INVALID_RESPONSE</span> - Invalid response from Reddit<br>
                    <small>Action: The requested content may not exist or be available</small>
                </div>
            </div>
        </section>
        
        <footer style="margin-top: 50px; text-align: center; color: #666;">
            <p>🚀 RedditExtractor - Part of the Extractor Suite</p>
            <p>Built with ❤️ for the modern automation stack</p>
        </footer>
    </body>
    </html>
    '''
    return docs_html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)