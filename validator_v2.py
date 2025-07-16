from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Tuple
import re
from error_enhancer import ErrorEnhancer

class ValidationError(Exception):
    def __init__(self, code: str, message: str, details: str = None, suggestions: List[str] = None):
        self.code = code
        self.message = message
        self.details = details
        self.suggestions = suggestions or []
        super().__init__(message)

class ValidationWarning:
    def __init__(self, code: str, message: str, suggestion: str = None):
        self.code = code
        self.message = message
        self.suggestion = suggestion

class RedditExtractorValidator:
    """
    Next-generation validator supporting both legacy flat structure and new nested structure
    """
    
    VALID_SORT_OPTIONS = ["hot", "new", "top", "rising", "relevance"]
    VALID_DATE_FILTERS = ["hour", "day", "week", "month", "year", "all"]
    VALID_CONTENT_TYPES = ["posts", "comments", "users", "communities"]
    VALID_OUTPUT_FORMATS = ["json", "csv", "rss", "xml"]
    VALID_DELIVERY_MODES = ["sync", "async"]
    
    @staticmethod
    def validate_request(params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[ValidationWarning]]:
        """
        Main validation entry point supporting both legacy and new format
        Returns: (validated_params, warnings)
        """
        warnings = []
        
        # Detect if this is legacy format or new format
        if RedditExtractorValidator._is_legacy_format(params):
            # Convert legacy format to new format
            converted_params = RedditExtractorValidator._convert_legacy_to_new(params)
            warnings.append(ValidationWarning(
                "LEGACY_FORMAT", 
                "Using legacy parameter format",
                "Consider migrating to new nested structure for better clarity"
            ))
            params = converted_params
        
        # Validate the new nested structure
        validated_params, additional_warnings = RedditExtractorValidator._validate_new_format(params)
        warnings.extend(additional_warnings)
        
        return validated_params, warnings
    
    @staticmethod
    def _is_legacy_format(params: Dict[str, Any]) -> bool:
        """Detect if parameters use legacy flat structure"""
        legacy_indicators = [
            'startUrls', 'searchTerm', 'maxItems', 'searchForPosts', 
            'searchForComments', 'skipComments', 'postsPerPage', 'commentsPerPage'
        ]
        return any(key in params for key in legacy_indicators)
    
    @staticmethod
    def _convert_legacy_to_new(legacy_params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy flat structure to new nested structure"""
        new_params = {
            "input": {
                "sources": [],
                "filters": {}
            },
            "content": {
                "include": [],
                "limits": {}
            },
            "output": {
                "format": "json",
                "delivery": {
                    "mode": "sync"
                }
            }
        }
        
        # Convert input sources
        if legacy_params.get('startUrls'):
            new_params["input"]["sources"].extend(legacy_params['startUrls'])
        if legacy_params.get('searchTerm'):
            new_params["input"]["sources"].append(legacy_params['searchTerm'])
        
        # Convert input filters
        if legacy_params.get('filterByDate'):
            new_params["input"]["filters"]["timeframe"] = legacy_params['filterByDate']
        if legacy_params.get('sortSearch'):
            new_params["input"]["filters"]["sortBy"] = legacy_params['sortSearch']
        if legacy_params.get('includeNSFW') is not None:
            new_params["input"]["filters"]["includeNSFW"] = legacy_params['includeNSFW']
        if legacy_params.get('postDateLimit'):
            new_params["input"]["filters"]["afterDate"] = legacy_params['postDateLimit']
        
        # Convert content preferences
        content_include = []
        if legacy_params.get('searchForPosts', True):
            content_include.append('posts')
        if legacy_params.get('searchForComments', True) and not legacy_params.get('skipComments', False):
            content_include.append('comments')
        if legacy_params.get('searchForUsers', False):
            content_include.append('users')
        if legacy_params.get('searchForCommunities', False):
            content_include.append('communities')
        new_params["content"]["include"] = content_include
        
        # Convert limits
        if legacy_params.get('maxItems'):
            new_params["content"]["limits"]["totalItems"] = legacy_params['maxItems']
        if legacy_params.get('commentsPerPage'):
            new_params["content"]["limits"]["commentsPerPost"] = legacy_params['commentsPerPage']
        if legacy_params.get('postsPerPage'):
            new_params["content"]["limits"]["itemsPerPage"] = legacy_params['postsPerPage']
        
        # Convert output preferences
        if legacy_params.get('outputFormat'):
            new_params["output"]["format"] = legacy_params['outputFormat']
        if legacy_params.get('webhookUrl'):
            new_params["output"]["delivery"]["mode"] = "async"
            new_params["output"]["delivery"]["webhookUrl"] = legacy_params['webhookUrl']
        
        return new_params
    
    @staticmethod
    def _validate_new_format(params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[ValidationWarning]]:
        """Validate the new nested parameter structure"""
        errors = []
        warnings = []
        validated = {}
        
        # Validate input section
        input_section = params.get('input', {})
        validated['input'] = RedditExtractorValidator._validate_input_section(input_section, errors)
        
        # Validate content section
        content_section = params.get('content', {})
        validated['content'] = RedditExtractorValidator._validate_content_section(content_section, errors, warnings)
        
        # Validate output section
        output_section = params.get('output', {})
        validated['output'] = RedditExtractorValidator._validate_output_section(output_section, errors)
        
        # Cross-section validation and warnings
        RedditExtractorValidator._validate_cross_section_rules(validated, errors, warnings)
        
        if errors:
            # Create enhanced error response for context
            error_response = RedditExtractorValidator.create_error_response(errors, warnings, params)
            
            raise ValidationError(
                code="VALIDATION_FAILED",
                message="Parameter validation failed",
                details=error_response
            )
        
        return validated, warnings
    
    @staticmethod
    def _validate_input_section(input_params: Dict[str, Any], errors: List[Dict]) -> Dict[str, Any]:
        """Validate input section parameters"""
        validated_input = {
            "sources": [],
            "filters": {}
        }
        
        # Validate sources
        sources = input_params.get('sources', [])
        if not sources:
            errors.append({
                "code": "NO_INPUT_SOURCES",
                "message": "At least one input source is required",
                "details": "Provide Reddit URLs, search terms, or subreddit names in the sources array"
            })
        elif not isinstance(sources, list):
            errors.append({
                "code": "INVALID_SOURCES_TYPE",
                "message": "Sources must be an array",
                "details": "Provide an array of strings containing URLs, search terms, or subreddit names"
            })
        else:
            validated_sources = []
            for source in sources:
                if not isinstance(source, str):
                    errors.append({
                        "code": "INVALID_SOURCE_TYPE",
                        "message": f"Source must be a string, got {type(source)}",
                        "details": "Each source should be a URL, search term, or subreddit name"
                    })
                elif source.strip():
                    validated_sources.append(source.strip())
            validated_input["sources"] = validated_sources
        
        # Validate filters
        filters = input_params.get('filters', {})
        validated_filters = {}
        
        # Timeframe filter
        timeframe = filters.get('timeframe', 'all')
        if timeframe not in RedditExtractorValidator.VALID_DATE_FILTERS:
            errors.append({
                "code": "INVALID_TIMEFRAME",
                "message": f"Invalid timeframe: {timeframe}",
                "details": f"Valid options: {', '.join(RedditExtractorValidator.VALID_DATE_FILTERS)}"
            })
        else:
            validated_filters['timeframe'] = timeframe
        
        # Sort filter
        sort_by = filters.get('sortBy', 'hot')
        if sort_by not in RedditExtractorValidator.VALID_SORT_OPTIONS:
            errors.append({
                "code": "INVALID_SORT",
                "message": f"Invalid sortBy: {sort_by}",
                "details": f"Valid options: {', '.join(RedditExtractorValidator.VALID_SORT_OPTIONS)}"
            })
        else:
            validated_filters['sortBy'] = sort_by
        
        # NSFW filter
        include_nsfw = filters.get('includeNSFW', False)
        if not isinstance(include_nsfw, bool):
            errors.append({
                "code": "INVALID_NSFW_FLAG",
                "message": "includeNSFW must be a boolean",
                "details": f"Received type: {type(include_nsfw)}"
            })
        else:
            validated_filters['includeNSFW'] = include_nsfw
        
        # After date filter
        after_date = filters.get('afterDate')
        if after_date is not None:
            if isinstance(after_date, str):
                try:
                    parsed_date = datetime.fromisoformat(after_date.replace('Z', '+00:00'))
                    validated_filters['afterDate'] = parsed_date
                except ValueError:
                    errors.append({
                        "code": "INVALID_DATE_FORMAT",
                        "message": "Invalid afterDate format",
                        "details": "Must be ISO 8601 date string (e.g., '2024-01-01' or '2024-01-01T00:00:00Z')"
                    })
            else:
                errors.append({
                    "code": "INVALID_DATE_TYPE",
                    "message": "afterDate must be a string",
                    "details": f"Received type: {type(after_date)}"
                })
        
        validated_input["filters"] = validated_filters
        return validated_input
    
    @staticmethod
    def _validate_content_section(content_params: Dict[str, Any], errors: List[Dict], warnings: List[ValidationWarning]) -> Dict[str, Any]:
        """Validate content section parameters"""
        validated_content = {
            "include": [],
            "limits": {}
        }
        
        # Validate include array
        include = content_params.get('include', ['posts'])
        if not isinstance(include, list):
            errors.append({
                "code": "INVALID_INCLUDE_TYPE",
                "message": "include must be an array",
                "details": f"Valid content types: {', '.join(RedditExtractorValidator.VALID_CONTENT_TYPES)}"
            })
        else:
            validated_include = []
            for content_type in include:
                if content_type not in RedditExtractorValidator.VALID_CONTENT_TYPES:
                    errors.append({
                        "code": "INVALID_CONTENT_TYPE",
                        "message": f"Invalid content type: {content_type}",
                        "details": f"Valid options: {', '.join(RedditExtractorValidator.VALID_CONTENT_TYPES)}"
                    })
                else:
                    validated_include.append(content_type)
            
            if not validated_include:
                errors.append({
                    "code": "NO_CONTENT_TYPES",
                    "message": "At least one content type must be included",
                    "details": f"Choose from: {', '.join(RedditExtractorValidator.VALID_CONTENT_TYPES)}"
                })
            
            validated_content["include"] = validated_include
        
        # Validate limits
        limits = content_params.get('limits', {})
        validated_limits = {}
        
        # Total items limit
        total_items = limits.get('totalItems', 100)
        if not isinstance(total_items, int) or total_items < 1 or total_items > 10000:
            errors.append({
                "code": "INVALID_TOTAL_ITEMS",
                "message": "totalItems must be an integer between 1 and 10000",
                "details": f"Received: {total_items}"
            })
        else:
            validated_limits['totalItems'] = total_items
        
        # Items per source limit
        items_per_source = limits.get('itemsPerSource')
        if items_per_source is not None:
            if not isinstance(items_per_source, int) or items_per_source < 1:
                errors.append({
                    "code": "INVALID_ITEMS_PER_SOURCE",
                    "message": "itemsPerSource must be a positive integer",
                    "details": f"Received: {items_per_source}"
                })
            else:
                validated_limits['itemsPerSource'] = items_per_source
        
        # Comments per post limit
        comments_per_post = limits.get('commentsPerPost', 20)
        if not isinstance(comments_per_post, int) or comments_per_post < 0 or comments_per_post > 100:
            errors.append({
                "code": "INVALID_COMMENTS_PER_POST",
                "message": "commentsPerPost must be an integer between 0 and 100",
                "details": f"Received: {comments_per_post}"
            })
        else:
            validated_limits['commentsPerPost'] = comments_per_post
        
        # Add warnings for potentially problematic configurations
        if total_items > 1000 and 'comments' in validated_content.get('include', []):
            warnings.append(ValidationWarning(
                "LARGE_REQUEST_WITH_COMMENTS",
                "Large requests with comments may be slow",
                "Consider using async delivery mode or reducing totalItems"
            ))
        
        # Warn about inefficient comment limits
        if comments_per_post > 50 and 'comments' in validated_content.get('include', []):
            warnings.append(ValidationWarning(
                "HIGH_COMMENTS_PER_POST",
                f"High commentsPerPost ({comments_per_post}) may slow down processing",
                "Consider reducing commentsPerPost for better performance"
            ))
        
        # Warn about very low limits
        if total_items < 10:
            warnings.append(ValidationWarning(
                "VERY_LOW_TOTAL_ITEMS",
                f"Very low totalItems ({total_items}) may not provide useful data",
                "Consider increasing totalItems for more comprehensive results"
            ))
        
        # Suggest optimal limits for different content types
        if 'users' in validated_content.get('include', []) and total_items > 50:
            warnings.append(ValidationWarning(
                "USERS_WITH_HIGH_LIMIT",
                "User data scraping is typically slower than posts",
                "Consider separate requests for user data or reduce totalItems"
            ))
        
        validated_content["limits"] = validated_limits
        return validated_content
    
    @staticmethod
    def _validate_output_section(output_params: Dict[str, Any], errors: List[Dict]) -> Dict[str, Any]:
        """Validate output section parameters"""
        validated_output = {
            "format": "json",
            "delivery": {
                "mode": "sync"
            }
        }
        
        # Validate format
        output_format = output_params.get('format', 'json')
        if output_format not in RedditExtractorValidator.VALID_OUTPUT_FORMATS:
            errors.append({
                "code": "INVALID_OUTPUT_FORMAT",
                "message": f"Invalid output format: {output_format}",
                "details": f"Valid options: {', '.join(RedditExtractorValidator.VALID_OUTPUT_FORMATS)}"
            })
        else:
            validated_output["format"] = output_format
        
        # Validate delivery
        delivery = output_params.get('delivery', {})
        validated_delivery = {}
        
        # Delivery mode
        mode = delivery.get('mode', 'sync')
        if mode not in RedditExtractorValidator.VALID_DELIVERY_MODES:
            errors.append({
                "code": "INVALID_DELIVERY_MODE",
                "message": f"Invalid delivery mode: {mode}",
                "details": f"Valid options: {', '.join(RedditExtractorValidator.VALID_DELIVERY_MODES)}"
            })
        else:
            validated_delivery['mode'] = mode
        
        # Webhook URL (required for async mode)
        webhook_url = delivery.get('webhookUrl')
        if mode == 'async':
            if not webhook_url:
                errors.append({
                    "code": "MISSING_WEBHOOK_URL",
                    "message": "webhookUrl is required for async delivery mode",
                    "details": "Provide a valid HTTP/HTTPS URL to receive results"
                })
            elif not isinstance(webhook_url, str) or not webhook_url.startswith(('http://', 'https://')):
                errors.append({
                    "code": "INVALID_WEBHOOK_URL",
                    "message": "webhookUrl must be a valid HTTP/HTTPS URL",
                    "details": f"Received: {webhook_url}"
                })
            else:
                validated_delivery['webhookUrl'] = webhook_url
        elif webhook_url:
            # Webhook provided but mode is sync - auto-switch to async
            validated_delivery['mode'] = 'async'
            if isinstance(webhook_url, str) and webhook_url.startswith(('http://', 'https://')):
                validated_delivery['webhookUrl'] = webhook_url
            else:
                errors.append({
                    "code": "INVALID_WEBHOOK_URL",
                    "message": "webhookUrl must be a valid HTTP/HTTPS URL",
                    "details": f"Received: {webhook_url}"
                })
        
        validated_output["delivery"] = validated_delivery
        return validated_output
    
    @staticmethod
    def _validate_cross_section_rules(params: Dict[str, Any], errors: List[Dict], warnings: List[ValidationWarning]):
        """Validate rules that span multiple sections"""
        
        # Extract key parameters
        total_items = params.get('content', {}).get('limits', {}).get('totalItems', 100)
        delivery_mode = params.get('output', {}).get('delivery', {}).get('mode', 'sync')
        output_format = params.get('output', {}).get('format', 'json')
        sources = params.get('input', {}).get('sources', [])
        items_per_source = params.get('content', {}).get('limits', {}).get('itemsPerSource')
        content_include = params.get('content', {}).get('include', [])
        timeframe = params.get('input', {}).get('filters', {}).get('timeframe', 'all')
        sort_by = params.get('input', {}).get('filters', {}).get('sortBy', 'hot')
        
        # Check for sync mode with large requests
        if delivery_mode == 'sync' and total_items > 1000:
            warnings.append(ValidationWarning(
                "LARGE_SYNC_REQUEST",
                f"Sync mode with {total_items} items may timeout",
                "Consider using async delivery mode for large requests"
            ))
        
        # Check for non-JSON format with async mode
        if delivery_mode == 'async' and output_format != 'json':
            warnings.append(ValidationWarning(
                "NON_JSON_ASYNC",
                f"Async mode with {output_format} format will include formatted data in webhook",
                "Webhook will receive both JSON and formatted data"
            ))
        
        # Check for multiple sources without per-source limits
        if len(sources) > 1 and not items_per_source:
            warnings.append(ValidationWarning(
                "MULTIPLE_SOURCES_NO_LIMIT",
                f"Multiple sources ({len(sources)}) without itemsPerSource limit",
                "Items will be distributed based on source activity - consider setting itemsPerSource for even distribution"
            ))
        
        # Suggest CSV format for data analysis
        if total_items > 500 and output_format == 'json' and delivery_mode == 'sync':
            warnings.append(ValidationWarning(
                "LARGE_JSON_RESPONSE",
                f"Large JSON response ({total_items} items) may be difficult to analyze",
                "Consider using 'csv' format for easier data analysis in spreadsheets"
            ))
        
        # Warn about inefficient source combinations
        search_sources = [s for s in sources if not (s.startswith('http') or s.startswith('r/') or s.startswith('u/'))]
        url_sources = [s for s in sources if s != search_sources]
        
        if len(search_sources) > 3:
            warnings.append(ValidationWarning(
                "MANY_SEARCH_TERMS",
                f"Multiple search terms ({len(search_sources)}) may produce overlapping results",
                "Consider combining related terms or making separate requests"
            ))
        
        # Suggest optimal sorting for different timeframes
        if timeframe in ['hour', 'day'] and sort_by == 'top':
            warnings.append(ValidationWarning(
                "SHORT_TIMEFRAME_TOP_SORT",
                f"Sorting by 'top' with '{timeframe}' timeframe may have limited results",
                "Consider using 'hot' or 'new' sorting for recent timeframes"
            ))
        
        # Warn about potential rate limiting
        if len(sources) > 5 and delivery_mode == 'sync':
            warnings.append(ValidationWarning(
                "MANY_SOURCES_SYNC",
                f"Processing {len(sources)} sources synchronously may hit rate limits",
                "Consider using async mode or reducing the number of sources"
            ))
        
        # Suggest appropriate content types for different source types
        if any('user' in str(s) for s in sources) and 'posts' not in content_include:
            warnings.append(ValidationWarning(
                "USER_SOURCE_NO_POSTS",
                "User sources typically provide posts - consider including 'posts' in content types",
                "Add 'posts' to content.include array for user-based sources"
            ))
        
        # Performance optimization suggestions
        if 'comments' in content_include and len(sources) > 3:
            warnings.append(ValidationWarning(
                "COMMENTS_MANY_SOURCES",
                "Including comments with multiple sources significantly increases processing time",
                "Consider making separate requests for comments or reducing sources"
            ))
        
        # Format-specific suggestions
        if output_format == 'rss' and 'comments' in content_include:
            warnings.append(ValidationWarning(
                "RSS_WITH_COMMENTS",
                "RSS format works best with posts only - comments may not display well",
                "Consider excluding comments for RSS output or use JSON/CSV format"
            ))
        
        # Smart limit suggestions based on content mix
        total_content_types = len(content_include)
        if total_content_types > 2 and total_items < 50:
            warnings.append(ValidationWarning(
                "LOW_ITEMS_MANY_TYPES",
                f"Low totalItems ({total_items}) with {total_content_types} content types may yield sparse results",
                f"Consider increasing totalItems to at least {total_content_types * 25} for balanced results"
            ))
    
    @staticmethod
    def create_error_response(errors: List[Dict], warnings: List[ValidationWarning] = None, request_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create standardized error response with enhanced messaging"""
        
        # Enhance errors with detailed context and suggestions
        enhanced_errors = ErrorEnhancer.enhance_error_list(errors, request_context)
        
        # Create error summary for multiple errors
        error_summary = ErrorEnhancer.create_error_summary(enhanced_errors) if len(enhanced_errors) > 1 else None
        
        response = {
            "success": False,
            "data": None,
            "metadata": {
                "validatedAt": datetime.utcnow().isoformat() + "Z",
                "errorCount": len(enhanced_errors),
                "warningCount": len(warnings or [])
            },
            "errors": enhanced_errors,
            "warnings": [{"code": w.code, "message": w.message, "suggestion": w.suggestion} for w in (warnings or [])]
        }
        
        # Add error summary for complex validation failures
        if error_summary:
            response["errorSummary"] = error_summary
        
        # Add alternative suggestions for failed requests
        if request_context:
            alternatives = ErrorEnhancer.suggest_alternatives(request_context)
            if alternatives:
                response["alternatives"] = alternatives
        
        return response
    
    @staticmethod
    def create_success_response(data: Dict[str, Any], validated_params: Dict[str, Any], execution_time: float, warnings: List[ValidationWarning] = None) -> Dict[str, Any]:
        """Create standardized success response"""
        total_items = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
        
        return {
            "success": True,
            "data": data,
            "metadata": {
                "totalItems": total_items,
                "itemsReturned": total_items,
                "requestParams": validated_params,
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
                "executionTime": f"{execution_time:.2f}s"
            },
            "warnings": [{"code": w.code, "message": w.message, "suggestion": w.suggestion} for w in (warnings or [])],
            "errors": []
        }
    
    @staticmethod
    def _detect_source_type(source: str) -> str:
        """Detect if source is a URL, subreddit name, or search term"""
        # Reddit URL patterns
        reddit_url_patterns = [
            r'^https?://(www\.|old\.)?reddit\.com/r/\w+',
            r'^https?://(www\.|old\.)?reddit\.com/user/\w+',
            r'^https?://(www\.|old\.)?reddit\.com/r/\w+/comments/'
        ]
        
        for pattern in reddit_url_patterns:
            if re.match(pattern, source):
                return 'url'
        
        # Subreddit shorthand (r/subreddit)
        if re.match(r'^r/\w+$', source):
            return 'subreddit'
        
        # User shorthand (u/username)
        if re.match(r'^u/\w+$', source):
            return 'user'
        
        # Otherwise treat as search term
        return 'search'