import re
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse, parse_qs

class RedditURLParser:
    """Parse and categorize Reddit URLs"""
    
    @staticmethod
    def parse_reddit_url(url: str) -> Dict[str, Union[str, None]]:
        """
        Parse a Reddit URL and extract relevant information
        
        Returns:
            dict: {
                'type': 'subreddit' | 'user' | 'post' | 'comment' | 'unknown',
                'subreddit': str or None,
                'username': str or None,
                'post_id': str or None,
                'comment_id': str or None,
                'cleaned_url': str
            }
        """
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        result = {
            'type': 'unknown',
            'subreddit': None,
            'username': None,
            'post_id': None,
            'comment_id': None,
            'cleaned_url': url
        }
        
        # Remove query parameters for cleaner URL
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        result['cleaned_url'] = clean_url
        
        # Subreddit patterns
        subreddit_patterns = [
            r'^r/([^/]+)/?$',  # /r/subreddit
            r'^r/([^/]+)/hot/?$',  # /r/subreddit/hot
            r'^r/([^/]+)/new/?$',  # /r/subreddit/new
            r'^r/([^/]+)/top/?$',  # /r/subreddit/top
            r'^r/([^/]+)/rising/?$',  # /r/subreddit/rising
        ]
        
        for pattern in subreddit_patterns:
            match = re.match(pattern, path)
            if match:
                result['type'] = 'subreddit'
                result['subreddit'] = match.group(1)
                return result
        
        # User patterns
        user_patterns = [
            r'^user/([^/]+)/?$',  # /user/username
            r'^user/([^/]+)/submitted/?$',  # /user/username/submitted
            r'^user/([^/]+)/comments/?$',  # /user/username/comments
            r'^user/([^/]+)/overview/?$',  # /user/username/overview
            r'^u/([^/]+)/?$',  # /u/username (alternative format)
        ]
        
        for pattern in user_patterns:
            match = re.match(pattern, path)
            if match:
                result['type'] = 'user'
                result['username'] = match.group(1)
                return result
        
        # Post patterns
        post_patterns = [
            r'^r/([^/]+)/comments/([^/]+)/?.*$',  # /r/subreddit/comments/post_id/...
        ]
        
        for pattern in post_patterns:
            match = re.match(pattern, path)
            if match:
                result['type'] = 'post'
                result['subreddit'] = match.group(1)
                result['post_id'] = match.group(2)
                
                # Check if this is a specific comment
                comment_match = re.search(r'/comments/[^/]+/[^/]+/([^/]+)/?', path)
                if comment_match:
                    result['type'] = 'comment'
                    result['comment_id'] = comment_match.group(1)
                
                return result
        
        return result
    
    @staticmethod
    def categorize_urls(urls: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """
        Categorize a list of Reddit URLs into subreddits, users, posts, etc.
        
        Returns:
            dict: {
                'subreddits': [{'name': str, 'url': str}],
                'users': [{'username': str, 'url': str}],
                'posts': [{'subreddit': str, 'post_id': str, 'url': str}],
                'comments': [{'subreddit': str, 'post_id': str, 'comment_id': str, 'url': str}],
                'unknown': [{'url': str}]
            }
        """
        categorized = {
            'subreddits': [],
            'users': [],
            'posts': [],
            'comments': [],
            'unknown': []
        }
        
        for url in urls:
            parsed = RedditURLParser.parse_reddit_url(url)
            
            if parsed['type'] == 'subreddit':
                categorized['subreddits'].append({
                    'name': parsed['subreddit'],
                    'url': parsed['cleaned_url']
                })
            elif parsed['type'] == 'user':
                categorized['users'].append({
                    'username': parsed['username'],
                    'url': parsed['cleaned_url']
                })
            elif parsed['type'] == 'post':
                categorized['posts'].append({
                    'subreddit': parsed['subreddit'],
                    'post_id': parsed['post_id'],
                    'url': parsed['cleaned_url']
                })
            elif parsed['type'] == 'comment':
                categorized['comments'].append({
                    'subreddit': parsed['subreddit'],
                    'post_id': parsed['post_id'],
                    'comment_id': parsed['comment_id'],
                    'url': parsed['cleaned_url']
                })
            else:
                categorized['unknown'].append({'url': url})
        
        return categorized
    
    @staticmethod
    def extract_subreddit_names(urls: List[str]) -> List[str]:
        """Extract unique subreddit names from a list of URLs"""
        subreddits = set()
        
        for url in urls:
            parsed = RedditURLParser.parse_reddit_url(url)
            if parsed['subreddit']:
                subreddits.add(parsed['subreddit'])
        
        return list(subreddits)
    
    @staticmethod
    def extract_usernames(urls: List[str]) -> List[str]:
        """Extract unique usernames from a list of URLs"""
        usernames = set()
        
        for url in urls:
            parsed = RedditURLParser.parse_reddit_url(url)
            if parsed['username']:
                usernames.add(parsed['username'])
        
        return list(usernames)
    
    @staticmethod
    def build_reddit_json_url(url_info: Dict[str, Union[str, None]], sort: str = 'hot', time_filter: str = 'all') -> str:
        """
        Build a Reddit JSON API URL from parsed URL info
        
        Args:
            url_info: Result from parse_reddit_url()
            sort: Sort order ('hot', 'new', 'top', 'rising')
            time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')
        
        Returns:
            str: Reddit JSON API URL
        """
        base_url = "https://www.reddit.com"
        
        if url_info['type'] == 'subreddit':
            if sort == 'hot':
                return f"{base_url}/r/{url_info['subreddit']}/hot.json"
            elif sort == 'new':
                return f"{base_url}/r/{url_info['subreddit']}/new.json"
            elif sort == 'top':
                return f"{base_url}/r/{url_info['subreddit']}/top.json"
            elif sort == 'rising':
                return f"{base_url}/r/{url_info['subreddit']}/rising.json"
        
        elif url_info['type'] == 'user':
            if sort == 'hot':
                return f"{base_url}/user/{url_info['username']}/submitted/hot.json"
            elif sort == 'new':
                return f"{base_url}/user/{url_info['username']}/submitted/new.json"
            elif sort == 'top':
                return f"{base_url}/user/{url_info['username']}/submitted/top.json"
        
        elif url_info['type'] == 'post':
            return f"{base_url}/r/{url_info['subreddit']}/comments/{url_info['post_id']}.json"
        
        return None
    
    @staticmethod
    def normalize_reddit_url(url: str) -> str:
        """
        Normalize a Reddit URL to a standard format
        
        Args:
            url: Reddit URL to normalize
            
        Returns:
            str: Normalized URL
        """
        # Remove old.reddit.com and replace with www.reddit.com
        url = re.sub(r'https?://old\.reddit\.com', 'https://www.reddit.com', url)
        
        # Remove www. if present and add it back consistently
        url = re.sub(r'https?://www\.reddit\.com', 'https://reddit.com', url)
        url = re.sub(r'https?://reddit\.com', 'https://www.reddit.com', url)
        
        # Remove trailing slashes
        url = url.rstrip('/')
        
        # Remove query parameters
        if '?' in url:
            url = url.split('?')[0]
        
        # Remove fragment identifiers
        if '#' in url:
            url = url.split('#')[0]
        
        return url