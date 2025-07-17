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

class YARSValidator:
    """
    Enhanced validator supporting both legacy flat structure and new nested structure
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
        if YARSValidator._is_legacy_format(params):
            # Convert legacy format to new format
            converted_params = YARSValidator._convert_legacy_to_new(params)
            warnings.append(ValidationWarning(
                "LEGACY_FORMAT", 
                "Using legacy parameter format",
                "Consider migrating to new nested structure for better clarity"
            ))
            params = converted_params
        
        # Validate the new nested structure
        validated_params, additional_warnings = YARSValidator._validate_new_format(params)
        warnings.extend(additional_warnings)
        
        return validated_params, warnings
    
    @staticmethod
    def validate_scrape_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility
        """
        validated_params, warnings = YARSValidator.validate_request(params)
        return validated_params
    
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
        
        # Convert limits to new structure
        if legacy_params.get('maxItems'):
            new_params["content"]["limits"]["maxPosts"] = legacy_params['maxItems']
        if legacy_params.get('maxPosts'):
            new_params["content"]["limits"]["maxPosts"] = legacy_params['maxPosts']
        if legacy_params.get('commentsPerPage'):
            new_params["content"]["limits"]["maxCommentsPerPost"] = legacy_params['commentsPerPage']
        if legacy_params.get('maxCommentsPerPost'):
            new_params["content"]["limits"]["maxCommentsPerPost"] = legacy_params['maxCommentsPerPost']
        if legacy_params.get('maxUsersPerPost'):
            new_params["content"]["limits"]["maxUsersPerPost"] = legacy_params['maxUsersPerPost']
        
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
        validated['input'] = YARSValidator._validate_input_section(input_section, errors)
        
        # Validate content section
        content_section = params.get('content', {})
        validated['content'] = YARSValidator._validate_content_section(content_section, errors, warnings)
        
        # Validate output section
        output_section = params.get('output', {})
        validated['output'] = YARSValidator._validate_output_section(output_section, errors)
        
        # Cross-section validation and warnings
        YARSValidator._validate_cross_section_rules(validated, errors, warnings)
        
        if errors:
            # Create enhanced error response for context
            error_response = YARSValidator.create_error_response(errors, warnings, params)
            
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
        if timeframe not in YARSValidator.VALID_DATE_FILTERS:
            errors.append({
                "code": "INVALID_TIMEFRAME",
                "message": f"Invalid timeframe: {timeframe}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_DATE_FILTERS)}"
            })
        else:
            validated_filters['timeframe'] = timeframe
        
        # Sort filter
        sort_by = filters.get('sortBy', 'hot')
        if sort_by not in YARSValidator.VALID_SORT_OPTIONS:
            errors.append({
                "code": "INVALID_SORT",
                "message": f"Invalid sortBy: {sort_by}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_SORT_OPTIONS)}"
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
                "details": f"Valid content types: {', '.join(YARSValidator.VALID_CONTENT_TYPES)}"
            })
        else:
            validated_include = []
            for content_type in include:
                if content_type not in YARSValidator.VALID_CONTENT_TYPES:
                    errors.append({
                        "code": "INVALID_CONTENT_TYPE",
                        "message": f"Invalid content type: {content_type}",
                        "details": f"Valid options: {', '.join(YARSValidator.VALID_CONTENT_TYPES)}"
                    })
                else:
                    validated_include.append(content_type)
            
            if not validated_include:
                errors.append({
                    "code": "NO_CONTENT_TYPES",
                    "message": "At least one content type must be included",
                    "details": f"Choose from: {', '.join(YARSValidator.VALID_CONTENT_TYPES)}"
                })
            
            validated_content["include"] = validated_include
        
        # Validate limits
        limits = content_params.get('limits', {})
        validated_limits = {}
        
        # Max posts limit
        max_posts = limits.get('maxPosts', 100)
        if not isinstance(max_posts, int) or max_posts < 1 or max_posts > 10000:
            errors.append({
                "code": "INVALID_MAX_POSTS",
                "message": "maxPosts must be an integer between 1 and 10000",
                "details": f"Received: {max_posts}"
            })
        else:
            validated_limits['maxPosts'] = max_posts
        
        # Comments per post limit
        max_comments_per_post = limits.get('maxCommentsPerPost', 0)
        if not isinstance(max_comments_per_post, int) or max_comments_per_post < 0 or max_comments_per_post > 500:
            errors.append({
                "code": "INVALID_MAX_COMMENTS_PER_POST",
                "message": "maxCommentsPerPost must be an integer between 0 and 500",
                "details": f"Received: {max_comments_per_post}"
            })
        else:
            validated_limits['maxCommentsPerPost'] = max_comments_per_post
        
        # Users per post limit
        max_users_per_post = limits.get('maxUsersPerPost', 0)
        if not isinstance(max_users_per_post, int) or max_users_per_post < 0 or max_users_per_post > 100:
            errors.append({
                "code": "INVALID_MAX_USERS_PER_POST",
                "message": "maxUsersPerPost must be an integer between 0 and 100",
                "details": f"Received: {max_users_per_post}"
            })
        else:
            validated_limits['maxUsersPerPost'] = max_users_per_post
        
        # Max communities limit
        max_communities = limits.get('maxCommunities', 10)
        if not isinstance(max_communities, int) or max_communities < 0 or max_communities > 100:
            errors.append({
                "code": "INVALID_MAX_COMMUNITIES",
                "message": "maxCommunities must be an integer between 0 and 100",
                "details": f"Received: {max_communities}"
            })
        else:
            validated_limits['maxCommunities'] = max_communities
        
        # Add warnings for potentially problematic configurations
        if max_posts > 1000 and max_comments_per_post > 0:
            warnings.append(ValidationWarning(
                "LARGE_REQUEST_WITH_COMMENTS",
                "Large requests with comments may be slow",
                "Consider using async delivery mode or reducing maxPosts"
            ))
        
        # Warn about inefficient comment limits
        if max_comments_per_post > 50:
            warnings.append(ValidationWarning(
                "HIGH_COMMENTS_PER_POST",
                f"High maxCommentsPerPost ({max_comments_per_post}) may slow down processing",
                "Consider reducing maxCommentsPerPost for better performance"
            ))
        
        # Warn about very high user extraction
        if max_users_per_post > 20:
            warnings.append(ValidationWarning(
                "HIGH_USERS_PER_POST",
                f"High maxUsersPerPost ({max_users_per_post}) may slow down processing",
                "Consider reducing maxUsersPerPost for better performance"
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
        if output_format not in YARSValidator.VALID_OUTPUT_FORMATS:
            errors.append({
                "code": "INVALID_OUTPUT_FORMAT",
                "message": f"Invalid output format: {output_format}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_OUTPUT_FORMATS)}"
            })
        else:
            validated_output["format"] = output_format
        
        # Validate delivery
        delivery = output_params.get('delivery', {})
        validated_delivery = {}
        
        # Delivery mode
        mode = delivery.get('mode', 'sync')
        if mode not in YARSValidator.VALID_DELIVERY_MODES:
            errors.append({
                "code": "INVALID_DELIVERY_MODE",
                "message": f"Invalid delivery mode: {mode}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_DELIVERY_MODES)}"
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
        max_posts = params.get('content', {}).get('limits', {}).get('maxPosts', 100)
        max_comments_per_post = params.get('content', {}).get('limits', {}).get('maxCommentsPerPost', 0)
        max_users_per_post = params.get('content', {}).get('limits', {}).get('maxUsersPerPost', 0)
        delivery_mode = params.get('output', {}).get('delivery', {}).get('mode', 'sync')
        output_format = params.get('output', {}).get('format', 'json')
        sources = params.get('input', {}).get('sources', [])
        content_include = params.get('content', {}).get('include', [])
        
        # Check for sync mode with large requests
        if delivery_mode == 'sync' and max_posts > 1000:
            warnings.append(ValidationWarning(
                "LARGE_SYNC_REQUEST",
                f"Sync mode with {max_posts} posts may timeout",
                "Consider using async delivery mode for large requests"
            ))
        
        # Check for sync mode with comments enabled
        if delivery_mode == 'sync' and max_comments_per_post > 0 and max_posts > 50:
            warnings.append(ValidationWarning(
                "SYNC_WITH_COMMENTS",
                f"Sync mode with {max_posts} posts and comments may be slow",
                "Consider using async delivery mode or reducing maxPosts"
            ))
        
        # Check for multiple sources
        if len(sources) > 1:
            warnings.append(ValidationWarning(
                "MULTIPLE_SOURCES",
                f"Multiple sources ({len(sources)}) will be processed sequentially",
                "Results will be combined from all sources"
            ))
    
    @staticmethod
    def _is_valid_reddit_url(url: str) -> bool:
        """Check if URL is a valid Reddit URL"""
        reddit_patterns = [
            r'^https?://(www\.)?reddit\.com/r/\w+/?',  # Subreddit
            r'^https?://(www\.)?reddit\.com/user/\w+/?',  # User
            r'^https?://(www\.)?reddit\.com/r/\w+/comments/\w+/',  # Post
            r'^https?://old\.reddit\.com/r/\w+/?',  # Old Reddit subreddit
            r'^https?://old\.reddit\.com/user/\w+/?',  # Old Reddit user
            r'^https?://old\.reddit\.com/r/\w+/comments/\w+/',  # Old Reddit post
        ]
        
        for pattern in reddit_patterns:
            if re.match(pattern, url):
                return True
        return False
    
    @staticmethod
    def create_error_response(errors: List[Dict], warnings: List[ValidationWarning] = None, request_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create standardized error response with enhanced messaging"""
        
        # Enhance errors with detailed context and suggestions
        try:
            enhanced_errors = ErrorEnhancer.enhance_error_list(errors, request_context)
        except:
            # Fallback if ErrorEnhancer fails
            enhanced_errors = errors
        
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
        
        return response
    
    @staticmethod
    def create_success_response(data: Dict[str, Any], request_params: Dict[str, Any], execution_time: float, warnings: List[ValidationWarning] = None) -> Dict[str, Any]:
        """Create standardized success response"""
        total_posts = len(data.get('posts', []))
        total_comments = sum(len(post.get('comments', [])) for post in data.get('posts', []))
        total_users = sum(len(post.get('users', [])) for post in data.get('posts', []))
        total_communities = len(data.get('communities', []))
        
        return {
            "success": True,
            "data": data,
            "metadata": {
                "totalPosts": total_posts,
                "totalComments": total_comments,
                "totalUsers": total_users,
                "totalCommunities": total_communities,
                "requestParams": request_params,
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
                "executionTime": f"{execution_time:.2f}s"
            },
            "warnings": [{"code": w.code, "message": w.message, "suggestion": w.suggestion} for w in (warnings or [])],
            "errors": []
        }