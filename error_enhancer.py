from typing import Dict, List, Any, Optional
import re

class ErrorEnhancer:
    """
    Enhanced error messaging system that provides actionable suggestions and help
    """
    
    ERROR_CONTEXT = {
        "NO_INPUT_SOURCES": {
            "category": "Input Configuration",
            "severity": "error",
            "user_message": "No input sources provided",
            "explanation": "The API needs to know what Reddit content to scrape. You must specify at least one source.",
            "examples": [
                '"sources": ["r/python"]',
                '"sources": ["machine learning"]',
                '"sources": ["https://reddit.com/r/javascript"]'
            ],
            "help_url": "/docs#input-sources"
        },
        
        "INVALID_SOURCES_TYPE": {
            "category": "Input Configuration",
            "severity": "error",
            "user_message": "Sources must be provided as an array",
            "explanation": "The sources parameter expects a JSON array of strings, not a single string or other type.",
            "fix_examples": [
                "❌ Wrong: \"sources\": \"r/python\"",
                "✅ Correct: \"sources\": [\"r/python\"]"
            ],
            "help_url": "/docs#input-sources"
        },
        
        "INVALID_TIMEFRAME": {
            "category": "Input Filters",
            "severity": "error",
            "user_message": "Invalid time filter specified",
            "explanation": "Reddit supports specific time ranges for filtering content by recency.",
            "valid_options": ["hour", "day", "week", "month", "year", "all"],
            "help_url": "/docs#time-filters"
        },
        
        "INVALID_SORT": {
            "category": "Input Filters", 
            "severity": "error",
            "user_message": "Invalid sorting option specified",
            "explanation": "Reddit provides different ways to sort content. Choose the one that best fits your use case.",
            "valid_options": ["hot", "new", "top", "rising", "relevance"],
            "recommendations": {
                "hot": "Trending content (good for current discussions)",
                "new": "Latest posts (good for real-time monitoring)",
                "top": "Highest scoring content (good for quality posts)",
                "rising": "Gaining momentum (good for emerging trends)",
                "relevance": "Most relevant to search terms (best for searches)"
            },
            "help_url": "/docs#sorting-options"
        },
        
        "INVALID_CONTENT_TYPE": {
            "category": "Content Configuration",
            "severity": "error", 
            "user_message": "Invalid content type specified",
            "explanation": "You can choose which types of Reddit content to include in your results.",
            "valid_options": ["posts", "comments", "users", "communities"],
            "use_cases": {
                "posts": "Reddit submissions and discussions",
                "comments": "User replies and conversations",
                "users": "Profile information and activity",
                "communities": "Subreddit information and stats"
            },
            "help_url": "/docs#content-types"
        },
        
        "INVALID_TOTAL_ITEMS": {
            "category": "Limits",
            "severity": "error",
            "user_message": "Invalid total items limit",
            "explanation": "The totalItems limit controls how much data you get back. Choose based on your needs and processing capabilities.",
            "recommendations": {
                "1-50": "Quick sampling or testing",
                "51-200": "Standard analysis or reports", 
                "201-1000": "Comprehensive research (consider async mode)",
                "1000+": "Large datasets (requires async mode)"
            },
            "help_url": "/docs#limits"
        },
        
        "MISSING_WEBHOOK_URL": {
            "category": "Async Configuration",
            "severity": "error",
            "user_message": "Webhook URL required for async processing",
            "explanation": "Async mode sends results to your webhook when processing is complete. This prevents timeouts for large requests.",
            "setup_guide": [
                "1. Set up a webhook endpoint on your server",
                "2. Ensure it accepts POST requests",
                "3. Handle the JSON payload we'll send",
                "4. Return a 200 status code to confirm receipt"
            ],
            "help_url": "/docs#webhooks"
        },
        
        "INVALID_WEBHOOK_URL": {
            "category": "Async Configuration", 
            "severity": "error",
            "user_message": "Invalid webhook URL format",
            "explanation": "Webhook URLs must be valid HTTP/HTTPS endpoints that can receive POST requests.",
            "requirements": [
                "Must start with http:// or https://",
                "Must be a valid URL format",
                "Should be publicly accessible",
                "Should return 200 OK for POST requests"
            ],
            "help_url": "/docs#webhook-setup"
        },
        
        "INVALID_OUTPUT_FORMAT": {
            "category": "Output Configuration",
            "severity": "error",
            "user_message": "Invalid output format specified",
            "explanation": "Choose the format that best suits your use case and downstream processing needs.",
            "format_guide": {
                "json": "Default format, best for APIs and programming",
                "csv": "Spreadsheet format, great for analysis in Excel/Google Sheets",
                "rss": "Feed format, perfect for content syndication",
                "xml": "Structured markup, good for legacy systems"
            },
            "help_url": "/docs#output-formats"
        }
    }
    
    @staticmethod
    def enhance_error(error_code: str, original_message: str, details: str = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Enhance a basic error with detailed context, suggestions, and help
        """
        base_error = ErrorEnhancer.ERROR_CONTEXT.get(error_code, {})
        
        enhanced = {
            "code": error_code,
            "message": base_error.get("user_message", original_message),
            "details": details or base_error.get("explanation", ""),
            "category": base_error.get("category", "General"),
            "severity": base_error.get("severity", "error"),
            "help": {}
        }
        
        # Add context-specific help
        if "examples" in base_error:
            enhanced["help"]["examples"] = base_error["examples"]
        
        if "fix_examples" in base_error:
            enhanced["help"]["how_to_fix"] = base_error["fix_examples"]
        
        if "valid_options" in base_error:
            enhanced["help"]["valid_options"] = base_error["valid_options"]
        
        if "recommendations" in base_error:
            enhanced["help"]["recommendations"] = base_error["recommendations"]
        
        if "use_cases" in base_error:
            enhanced["help"]["use_cases"] = base_error["use_cases"]
        
        if "format_guide" in base_error:
            enhanced["help"]["format_guide"] = base_error["format_guide"]
        
        if "setup_guide" in base_error:
            enhanced["help"]["setup_guide"] = base_error["setup_guide"]
        
        if "requirements" in base_error:
            enhanced["help"]["requirements"] = base_error["requirements"]
        
        if "help_url" in base_error:
            enhanced["help"]["documentation"] = base_error["help_url"]
        
        # Add smart suggestions based on context
        suggestions = ErrorEnhancer._generate_smart_suggestions(error_code, context)
        if suggestions:
            enhanced["help"]["suggestions"] = suggestions
        
        return enhanced
    
    @staticmethod
    def _generate_smart_suggestions(error_code: str, context: Dict[str, Any] = None) -> List[str]:
        """Generate context-aware suggestions for errors"""
        if not context:
            return []
        
        suggestions = []
        
        if error_code == "NO_INPUT_SOURCES":
            suggestions.append("Try starting with a simple source like 'r/popular' to test the API")
            suggestions.append("You can mix URLs and search terms: ['r/python', 'machine learning']")
        
        elif error_code == "INVALID_TOTAL_ITEMS":
            current_value = context.get("current_value")
            if current_value:
                if current_value > 10000:
                    suggestions.append("Consider breaking large requests into smaller batches")
                    suggestions.append("Use async mode with webhooks for processing large datasets")
                elif current_value < 1:
                    suggestions.append("Set totalItems to at least 10 for meaningful results")
        
        elif error_code == "MISSING_WEBHOOK_URL":
            suggestions.append("Test with sync mode first using smaller totalItems (< 1000)")
            suggestions.append("Use webhook.site to create a test webhook URL for development")
            suggestions.append("Consider using ngrok to expose your local development server")
        
        elif error_code == "INVALID_OUTPUT_FORMAT":
            current_format = context.get("current_format", "")
            if "xls" in current_format.lower():
                suggestions.append("Use 'csv' format instead - it opens in Excel and is more compatible")
            elif "txt" in current_format.lower():
                suggestions.append("Use 'csv' format for structured data or 'json' for programming use")
        
        return suggestions
    
    @staticmethod
    def enhance_error_list(errors: List[Dict[str, Any]], context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Enhance a list of errors with detailed context"""
        enhanced_errors = []
        
        for error in errors:
            error_code = error.get("code", "UNKNOWN_ERROR")
            original_message = error.get("message", "")
            details = error.get("details", "")
            
            enhanced = ErrorEnhancer.enhance_error(error_code, original_message, details, context)
            enhanced_errors.append(enhanced)
        
        return enhanced_errors
    
    @staticmethod
    def create_error_summary(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a helpful summary of multiple errors"""
        if not errors:
            return {}
        
        # Categorize errors
        categories = {}
        for error in errors:
            category = error.get("category", "General")
            if category not in categories:
                categories[category] = []
            categories[category].append(error)
        
        # Generate summary
        summary = {
            "total_errors": len(errors),
            "categories": categories,
            "quick_fixes": [],
            "next_steps": []
        }
        
        # Add category-specific quick fixes
        if "Input Configuration" in categories:
            summary["quick_fixes"].append("Check your input sources array format")
            summary["next_steps"].append("Review the input section of your request")
        
        if "Limits" in categories:
            summary["quick_fixes"].append("Verify your numeric limits are within valid ranges")
            summary["next_steps"].append("Consider using smaller limits for testing")
        
        if "Async Configuration" in categories:
            summary["quick_fixes"].append("Set up a webhook URL for async processing")
            summary["next_steps"].append("Test with sync mode first using smaller datasets")
        
        # Add general guidance
        summary["next_steps"].extend([
            "Check the API documentation for examples",
            "Use the /api/compare endpoint to validate your request format",
            "Start with a minimal request and add parameters gradually"
        ])
        
        return summary
    
    @staticmethod
    def suggest_alternatives(failed_request: Dict[str, Any]) -> List[Dict[str, str]]:
        """Suggest alternative request configurations that might work"""
        alternatives = []
        
        # If large sync request failed, suggest async
        content_limits = failed_request.get("content", {}).get("limits", {})
        delivery_mode = failed_request.get("output", {}).get("delivery", {}).get("mode", "sync")
        total_items = content_limits.get("totalItems", 0)
        
        if delivery_mode == "sync" and total_items > 1000:
            alternatives.append({
                "title": "Use Async Processing",
                "description": "Switch to async mode to handle large requests without timeouts",
                "change": "Set output.delivery.mode to 'async' and add a webhookUrl"
            })
        
        # If complex request failed, suggest simpler version
        sources = failed_request.get("input", {}).get("sources", [])
        content_include = failed_request.get("content", {}).get("include", [])
        
        if len(sources) > 3 or len(content_include) > 2:
            alternatives.append({
                "title": "Simplify Request",
                "description": "Start with fewer sources and content types, then expand gradually",
                "change": "Reduce to 1-2 sources and focus on 'posts' only initially"
            })
        
        # If validation failed, suggest using legacy format
        alternatives.append({
            "title": "Try Legacy Format",
            "description": "Use the simpler v1 API format while learning the new structure",
            "change": "Use /api/scrape endpoint with flat parameter structure"
        })
        
        return alternatives