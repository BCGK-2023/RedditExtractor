from datetime import datetime
from typing import Dict, List, Optional, Union, Any
import re

class ValidationError(Exception):
    def __init__(self, code: str, message: str, details: str = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

class YARSValidator:
    
    VALID_SORT_OPTIONS = ["hot", "new", "top", "rising", "relevance"]
    VALID_DATE_FILTERS = ["hour", "day", "week", "month", "year", "all"]
    
    @staticmethod
    def validate_scrape_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize parameters for the /api/scrape endpoint
        Returns cleaned parameters or raises ValidationError
        """
        errors = []
        cleaned_params = {}
        
        # Validate input sources (mutually exclusive)
        start_urls = params.get('startUrls')
        search_term = params.get('searchTerm')
        
        if start_urls and search_term:
            errors.append({
                "code": "INVALID_PARAMS",
                "message": "startUrls and searchTerm are mutually exclusive",
                "details": "Provide either startUrls or searchTerm, not both"
            })
        
        if not start_urls and not search_term:
            errors.append({
                "code": "INVALID_PARAMS", 
                "message": "Either startUrls or searchTerm is required",
                "details": "You must provide either startUrls array or searchTerm string"
            })
        
        # Validate startUrls
        if start_urls:
            if not isinstance(start_urls, list):
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "startUrls must be an array",
                    "details": "startUrls should be a JSON array of Reddit URLs"
                })
            else:
                valid_urls = []
                for url in start_urls:
                    if not isinstance(url, str):
                        errors.append({
                            "code": "INVALID_PARAMS",
                            "message": "All startUrls must be strings",
                            "details": f"Invalid URL type: {type(url)}"
                        })
                    elif not YARSValidator._is_valid_reddit_url(url):
                        errors.append({
                            "code": "INVALID_PARAMS",
                            "message": f"Invalid Reddit URL: {url}",
                            "details": "URLs must be valid Reddit URLs (reddit.com or old.reddit.com)"
                        })
                    else:
                        valid_urls.append(url)
                cleaned_params['startUrls'] = valid_urls
        
        # Validate searchTerm
        if search_term:
            if not isinstance(search_term, str):
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "searchTerm must be a string",
                    "details": f"Received type: {type(search_term)}"
                })
            elif len(search_term.strip()) == 0:
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "searchTerm cannot be empty",
                    "details": "Provide a non-empty search term"
                })
            elif len(search_term) > 500:
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "searchTerm too long",
                    "details": "Search term must be 500 characters or less"
                })
            else:
                cleaned_params['searchTerm'] = search_term.strip()
        
        # Validate boolean flags
        bool_params = [
            'skipComments', 'skipUserPosts', 'skipCommunity', 
            'searchForPosts', 'searchForComments', 'searchForCommunities', 
            'searchForUsers', 'includeNSFW'
        ]
        
        for param in bool_params:
            value = params.get(param)
            if value is not None:
                if not isinstance(value, bool):
                    errors.append({
                        "code": "INVALID_PARAMS",
                        "message": f"{param} must be a boolean",
                        "details": f"Received type: {type(value)}"
                    })
                else:
                    cleaned_params[param] = value
            else:
                # Set defaults
                defaults = {
                    'skipComments': False,
                    'skipUserPosts': False, 
                    'skipCommunity': False,
                    'searchForPosts': True,
                    'searchForComments': True,
                    'searchForCommunities': False,
                    'searchForUsers': False,
                    'includeNSFW': False
                }
                cleaned_params[param] = defaults.get(param, False)
        
        # Validate sortSearch
        sort_search = params.get('sortSearch', 'hot')
        if sort_search not in YARSValidator.VALID_SORT_OPTIONS:
            errors.append({
                "code": "INVALID_PARAMS",
                "message": f"Invalid sortSearch value: {sort_search}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_SORT_OPTIONS)}"
            })
        else:
            cleaned_params['sortSearch'] = sort_search
        
        # Validate filterByDate
        filter_by_date = params.get('filterByDate', 'all')
        if filter_by_date not in YARSValidator.VALID_DATE_FILTERS:
            errors.append({
                "code": "INVALID_PARAMS",
                "message": f"Invalid filterByDate value: {filter_by_date}",
                "details": f"Valid options: {', '.join(YARSValidator.VALID_DATE_FILTERS)}"
            })
        else:
            cleaned_params['filterByDate'] = filter_by_date
        
        # Validate webhookUrl if provided
        webhook_url = params.get('webhookUrl')
        if webhook_url is not None:
            if not isinstance(webhook_url, str):
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "webhookUrl must be a string",
                    "details": f"Received type: {type(webhook_url)}"
                })
            elif not webhook_url.startswith(('http://', 'https://')):
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "webhookUrl must be a valid HTTP/HTTPS URL",
                    "details": f"Invalid URL: {webhook_url}"
                })
            else:
                cleaned_params['webhookUrl'] = webhook_url
        
        # Validate outputFormat
        output_format = params.get('outputFormat', 'json')
        valid_formats = ['json', 'csv', 'rss', 'xml']
        if output_format not in valid_formats:
            errors.append({
                "code": "INVALID_PARAMS",
                "message": f"Invalid outputFormat: {output_format}",
                "details": f"Valid options: {', '.join(valid_formats)}"
            })
        else:
            cleaned_params['outputFormat'] = output_format
        
        # Validate numeric parameters
        numeric_params = {
            'maxItems': {'default': 100, 'min': 1, 'max': 10000},
            'postsPerPage': {'default': 25, 'min': 1, 'max': 100},
            'commentsPerPage': {'default': 20, 'min': 1, 'max': 100},
            'communityPagesLimit': {'default': 1, 'min': 1, 'max': 50},
            'userPagesLimit': {'default': 1, 'min': 1, 'max': 50},
            'pageScrollTimeout': {'default': 30, 'min': 5, 'max': 300}
        }
        
        for param, config in numeric_params.items():
            value = params.get(param, config['default'])
            if not isinstance(value, int):
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": f"{param} must be an integer",
                    "details": f"Received type: {type(value)}"
                })
            elif value < config['min'] or value > config['max']:
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": f"{param} must be between {config['min']} and {config['max']}",
                    "details": f"Received value: {value}"
                })
            else:
                cleaned_params[param] = value
        
        # Validate postDateLimit
        post_date_limit = params.get('postDateLimit')
        if post_date_limit is not None:
            if isinstance(post_date_limit, str):
                try:
                    # Try to parse ISO date string
                    parsed_date = datetime.fromisoformat(post_date_limit.replace('Z', '+00:00'))
                    cleaned_params['postDateLimit'] = parsed_date
                except ValueError:
                    errors.append({
                        "code": "INVALID_PARAMS",
                        "message": "Invalid postDateLimit format",
                        "details": "Must be ISO 8601 date string (e.g., '2024-01-01' or '2024-01-01T00:00:00Z')"
                    })
            else:
                errors.append({
                    "code": "INVALID_PARAMS",
                    "message": "postDateLimit must be a string or null",
                    "details": f"Received type: {type(post_date_limit)}"
                })
        
        # If there are validation errors, raise exception
        if errors:
            raise ValidationError(
                code="INVALID_PARAMS",
                message="Parameter validation failed",
                details=errors
            )
        
        return cleaned_params
    
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
    def create_error_response(errors: List[Dict[str, str]], request_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "success": False,
            "data": None,
            "metadata": {
                "requestParams": request_params or {},
                "scrapedAt": datetime.utcnow().isoformat() + "Z"
            },
            "errors": errors
        }
    
    @staticmethod
    def create_success_response(data: Dict[str, Any], request_params: Dict[str, Any], execution_time: float) -> Dict[str, Any]:
        """Create standardized success response"""
        total_items = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
        
        return {
            "success": True,
            "data": data,
            "metadata": {
                "totalItems": total_items,
                "itemsReturned": total_items,
                "requestParams": request_params,
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
                "executionTime": f"{execution_time:.2f}s"
            },
            "errors": []
        }