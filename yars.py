from __future__ import annotations
from sessions import RandomUserAgentSession
from url_parser import RedditURLParser
import time
import random
import logging
import requests
import os
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.basicConfig(
    filename="YARS.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class YARS:
    __slots__ = ("headers", "session", "proxy", "timeout")

    def __init__(self, proxy=None, timeout=10, random_user_agent=True):
        self.session = RandomUserAgentSession() if random_user_agent else requests.Session()
        self.timeout = timeout

        # Configure DataImpulse proxy from environment variables if available
        if proxy is None:
            proxy_host = os.getenv('PROXY_HOST')
            proxy_port = os.getenv('PROXY_PORT')
            proxy_username = os.getenv('PROXY_USERNAME')
            proxy_password = os.getenv('PROXY_PASSWORD')
            
            if all([proxy_host, proxy_port, proxy_username, proxy_password]):
                proxy = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
        
        self.proxy = proxy

        retries = Retry(
            total=5,
            backoff_factor=2,  # Exponential backoff
            status_forcelist=[429, 500, 502, 503, 504],
        )

        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
    def handle_search(self,url, params, after=None, before=None):
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            logging.info("Search request successful")
        except Exception as e:
            if response.status_code != 200:
                logging.info("Search request unsuccessful due to: %s", e)
                print(f"Failed to fetch search results: {response.status_code}")
                return []

        data = response.json()
        results = []
        for post in data["data"]["children"]:
            post_data = post["data"]
            results.append(
                {
                    "title": post_data["title"],
                    "link": f"https://www.reddit.com{post_data['permalink']}",
                    "description": post_data.get("selftext", "")[:269],
                }
            )
        logging.info("Search Results Retrned %d Results", len(results))
        return results
    def search_reddit(self, query, limit=10, after=None, before=None):
        url = "https://www.reddit.com/search.json"
        params = {"q": query, "limit": limit, "sort": "relevance", "type": "link"}
        return self.handle_search(url, params, after, before)
    def search_subreddit(self, subreddit, query, limit=10, after=None, before=None, sort="relevance"):
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "limit": limit, "sort": "relevance", "type": "link","restrict_sr":"on"}
        return self.handle_search(url, params, after, before)

    def scrape_post_details(self, permalink):
        url = f"https://www.reddit.com{permalink}.json"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            logging.info("Post details request successful : %s", url)
        except Exception as e:
            logging.info("Post details request unsccessful: %e", e)
            if response.status_code != 200:
                print(f"Failed to fetch post data: {response.status_code}")
                return None

        post_data = response.json()
        if not isinstance(post_data, list) or len(post_data) < 2:
            logging.info("Unexpected post data structre")
            print("Unexpected post data structure")
            return None

        main_post = post_data[0]["data"]["children"][0]["data"]
        title = main_post["title"]
        body = main_post.get("selftext", "")

        comments = self._extract_comments(post_data[1]["data"]["children"])
        logging.info("Successfully scraped post: %s", title)
        return {"title": title, "body": body, "comments": comments}

    def _extract_comments(self, comments):
        logging.info("Extracting comments")
        extracted_comments = []
        for comment in comments:
            if isinstance(comment, dict) and comment.get("kind") == "t1":
                comment_data = comment.get("data", {})
                extracted_comment = {
                    "author": comment_data.get("author", ""),
                    "body": comment_data.get("body", ""),
                    "score": comment_data.get("score",""),
                    "replies": [],
                }

                replies = comment_data.get("replies", "")
                if isinstance(replies, dict):
                    extracted_comment["replies"] = self._extract_comments(
                        replies.get("data", {}).get("children", [])
                    )
                extracted_comments.append(extracted_comment)
        logging.info("Successfully extracted comments")
        return extracted_comments

    def _extract_users_from_post(self, post_info: Dict[str, Any], max_users: int) -> List[Dict[str, Any]]:
        """
        Extract users from a post (author + commenters)
        
        Args:
            post_info: Post dictionary containing author and comments
            max_users: Maximum number of users to extract
            
        Returns:
            List of user dictionaries
        """
        users = []
        seen_users = set()
        
        # Add post author
        author_username = post_info.get("author", {}).get("username", "")
        if author_username and author_username not in seen_users:
            users.append({
                "username": author_username,
                "role": "author",
                "profile_url": f"https://reddit.com/user/{author_username}"
            })
            seen_users.add(author_username)
        
        # Add commenters
        def extract_commenters(comments):
            for comment in comments:
                if len(users) >= max_users:
                    break
                    
                commenter = comment.get("author", "")
                if commenter and commenter not in seen_users:
                    users.append({
                        "username": commenter,
                        "role": "commenter",
                        "profile_url": f"https://reddit.com/user/{commenter}"
                    })
                    seen_users.add(commenter)
                
                # Process replies recursively
                if comment.get("replies"):
                    extract_commenters(comment["replies"])
        
        extract_commenters(post_info.get("comments", []))
        
        return users[:max_users]

    def scrape_user_data(self, username, limit=10):
        logging.info("Scraping user data for %s, limit: %d", username, limit)
        base_url = f"https://www.reddit.com/user/{username}/.json"
        params = {"limit": limit, "after": None}
        all_items = []
        count = 0

        while count < limit:
            try:
                response = self.session.get(
                    base_url, params=params, timeout=self.timeout
                )
                response.raise_for_status()
                logging.info("User data request successful")
            except Exception as e:
                logging.info("User data request unsuccessful: %s", e)
                if response.status_code != 200:
                    print(
                        f"Failed to fetch data for user {username}: {response.status_code}"
                    )
                    break
            try:
                data = response.json()
            except ValueError:
                print(f"Failed to parse JSON response for user {username}.")
                break

            if "data" not in data or "children" not in data["data"]:
                print(
                    f"No 'data' or 'children' field found in response for user {username}."
                )
                logging.info("No 'data' or 'children' field found in response")
                break

            items = data["data"]["children"]
            if not items:
                print(f"No more items found for user {username}.")
                logging.info("No more items found for user")
                break

            for item in items:
                kind = item["kind"]
                item_data = item["data"]
                if kind == "t3":
                    post_url = f"https://www.reddit.com{item_data.get('permalink', '')}"
                    all_items.append(
                        {
                            "type": "post",
                            "title": item_data.get("title", ""),
                            "subreddit": item_data.get("subreddit", ""),
                            "url": post_url,
                            "created_utc": item_data.get("created_utc", ""),
                        }
                    )
                elif kind == "t1":
                    comment_url = (
                        f"https://www.reddit.com{item_data.get('permalink', '')}"
                    )
                    all_items.append(
                        {
                            "type": "comment",
                            "subreddit": item_data.get("subreddit", ""),
                            "body": item_data.get("body", ""),
                            "created_utc": item_data.get("created_utc", ""),
                            "url": comment_url,
                        }
                    )
                count += 1
                if count >= limit:
                    break

            params["after"] = data["data"].get("after")
            if not params["after"]:
                break

            time.sleep(random.uniform(1, 2))
            logging.info("Sleeping for random time")

        logging.info("Successfully scraped user data for %s", username)
        return all_items

    def fetch_subreddit_posts(
        self, subreddit, max_posts=10, max_comments_per_post=0, max_users_per_post=0, category="hot", time_filter="all"
    ):
        logging.info(
            "Fetching subreddit/user posts for %s, max_posts: %d, max_comments_per_post: %d, category: %s, time_filter: %s",
            subreddit,
            max_posts,
            max_comments_per_post,
            category,
            time_filter,
        )
        if category not in ["hot", "top", "new", "userhot", "usertop", "usernew"]:
            raise ValueError("Category for Subredit must be either 'hot', 'top', or 'new' or for User must be 'userhot', 'usertop', or 'usernew'")

        batch_size = min(100, max_posts)
        total_fetched = 0
        after = None
        all_posts = []

        while total_fetched < max_posts:
            if category == "hot":
                url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            elif category == "top":
                url = f"https://www.reddit.com/r/{subreddit}/top.json"
            elif category == "new":
                url = f"https://www.reddit.com/r/{subreddit}/new.json"
            elif category == "userhot":
                url = f"https://www.reddit.com/user/{subreddit}/submitted/hot.json"
            elif category == "usertop":
                url = f"https://www.reddit.com/user/{subreddit}/submitted/top.json"
            else:
                url = f"https://www.reddit.com/user/{subreddit}/submitted/new.json"

            params = {
                "limit": batch_size,
                "after": after,
                "raw_json": 1,
                "t": time_filter,
            }
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                logging.info("Subreddit/user posts request successful")
            except Exception as e:
                logging.info("Subreddit/user posts request unsuccessful: %s", e)
                if response.status_code != 200:
                    print(
                        f"Failed to fetch posts for subreddit/user {subreddit}: {response.status_code}"
                    )
                    break

            data = response.json()
            posts = data["data"]["children"]
            if not posts:
                break

            for post in posts:
                post_data = post["data"]
                
                # Build enhanced post structure
                post_info = {
                    "title": post_data.get("title", ""),
                    "author": {
                        "username": post_data.get("author", ""),
                        "profile_url": f"https://reddit.com/user/{post_data.get('author', '')}" if post_data.get("author") else ""
                    },
                    "content": post_data.get("selftext", ""),
                    "metadata": {
                        "score": post_data.get("score", 0),
                        "num_comments": post_data.get("num_comments", 0),
                        "created_utc": post_data.get("created_utc", 0),
                        "subreddit": subreddit,
                        "permalink": post_data.get("permalink", ""),
                        "url": post_data.get("url", "")
                    },
                    "comments": [],
                    "users": []
                }
                
                # Add image URLs if available
                if post_data.get("post_hint") == "image" and "url" in post_data:
                    post_info["metadata"]["image_url"] = post_data["url"]
                elif "preview" in post_data and "images" in post_data["preview"]:
                    post_info["metadata"]["image_url"] = post_data["preview"]["images"][0]["source"]["url"]
                
                if "thumbnail" in post_data and post_data["thumbnail"] not in ["self", "default", ""]:
                    post_info["metadata"]["thumbnail_url"] = post_data["thumbnail"]
                
                # Fetch comments if requested
                if max_comments_per_post > 0:
                    post_details = self.scrape_post_details(post_data.get("permalink", ""))
                    if post_details and post_details.get("comments"):
                        post_info["comments"] = post_details["comments"][:max_comments_per_post]
                
                # Extract users if requested
                if max_users_per_post > 0:
                    users = self._extract_users_from_post(post_info, max_users_per_post)
                    post_info["users"] = users

                all_posts.append(post_info)
                total_fetched += 1
                if total_fetched >= max_posts:
                    break

            after = data["data"].get("after")
            if not after:
                break

            time.sleep(random.uniform(1, 2))
            logging.info("Sleeping for random time")

        logging.info("Successfully fetched subreddit posts for %s", subreddit)
        return all_posts

    def search_reddit_global(self, query: str, max_posts: int = 10, max_comments_per_post: int = 0, max_users_per_post: int = 0, sort: str = "relevance", time_filter: str = "all") -> List[Dict[str, Any]]:
        """
        Search across all of Reddit for posts matching a query
        
        Args:
            query: Search query string
            max_posts: Maximum number of posts to return
            max_comments_per_post: Maximum comments per post to fetch (0 = no comments)
            max_users_per_post: Maximum users per post to extract (0 = no users)
            sort: Sort order ('relevance', 'hot', 'top', 'new')
            time_filter: Time filter ('hour', 'day', 'week', 'month', 'year', 'all')
        
        Returns:
            List of post dictionaries with nested comments and users
        """
        logging.info("Searching Reddit globally for query: %s, max_posts: %d, max_comments_per_post: %d", query, max_posts, max_comments_per_post)
        
        url = "https://www.reddit.com/search.json"
        params = {
            "q": query,
            "limit": min(100, max_posts),
            "sort": sort,
            "type": "link",
            "t": time_filter
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            logging.info("Global search request successful")
        except Exception as e:
            logging.error("Global search request failed: %s", e)
            return []

        data = response.json()
        results = []
        
        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            
            # Build enhanced post structure
            post_info = {
                "title": post_data.get("title", ""),
                "author": {
                    "username": post_data.get("author", ""),
                    "profile_url": f"https://reddit.com/user/{post_data.get('author', '')}" if post_data.get("author") else ""
                },
                "content": post_data.get("selftext", ""),
                "metadata": {
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "created_utc": post_data.get("created_utc", 0),
                    "subreddit": post_data.get("subreddit", ""),
                    "permalink": post_data.get("permalink", ""),
                    "url": post_data.get("url", "")
                },
                "comments": [],
                "users": []
            }
            
            # Add image URLs if available
            if post_data.get("post_hint") == "image" and "url" in post_data:
                post_info["metadata"]["image_url"] = post_data["url"]
            elif "preview" in post_data and "images" in post_data["preview"]:
                post_info["metadata"]["image_url"] = post_data["preview"]["images"][0]["source"]["url"]
            
            if "thumbnail" in post_data and post_data["thumbnail"] not in ["self", "default", ""]:
                post_info["metadata"]["thumbnail_url"] = post_data["thumbnail"]
            
            # Fetch comments if requested
            if max_comments_per_post > 0:
                post_details = self.scrape_post_details(post_data.get("permalink", ""))
                if post_details and post_details.get("comments"):
                    post_info["comments"] = post_details["comments"][:max_comments_per_post]
            
            # Extract users if requested
            if max_users_per_post > 0:
                users = self._extract_users_from_post(post_info, max_users_per_post)
                post_info["users"] = users
            
            results.append(post_info)
            
            if len(results) >= max_posts:
                break
        
        logging.info("Successfully completed global search for %s, found %d results", query, len(results))
        return results[:max_posts]
    
    def scrape_by_urls(self, urls: List[str], params: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scrape Reddit content from a list of URLs
        
        Args:
            urls: List of Reddit URLs to scrape
            params: Scraping parameters with new structure
            
        Returns:
            Dictionary with categorized results (posts with nested comments and users)
        """
        logging.info("Starting URL-based scraping for %d URLs", len(urls))
        
        # Extract new parameters
        max_posts = params.get('maxPosts', 100)
        max_comments_per_post = params.get('maxCommentsPerPost', 0)
        max_users_per_post = params.get('maxUsersPerPost', 0)
        
        # Categorize URLs
        categorized = RedditURLParser.categorize_urls(urls)
        
        results = {
            "posts": [],
            "communities": []
        }
        
        # Scrape subreddits
        for subreddit_info in categorized['subreddits']:
            if not params.get('skipCommunity', False):
                subreddit_name = subreddit_info['name']
                posts = self.fetch_subreddit_posts(
                    subreddit_name,
                    max_posts=max_posts,
                    max_comments_per_post=max_comments_per_post,
                    max_users_per_post=max_users_per_post,
                    category=params.get('sortSearch', 'hot'),
                    time_filter=params.get('filterByDate', 'all')
                )
                
                # Filter posts by date if specified
                if params.get('postDateLimit'):
                    posts = self._filter_posts_by_date(posts, params['postDateLimit'])
                
                results['posts'].extend(posts)
                
                # Add community info
                if params.get('searchForCommunities', False):
                    results['communities'].append({
                        'name': subreddit_name,
                        'url': subreddit_info['url'],
                        'type': 'subreddit',
                        'posts_count': len(posts)
                    })
        
        # Scrape users (convert to new structure)
        for user_info in categorized['users']:
            if not params.get('skipUserPosts', False):
                username = user_info['username']
                user_posts = self.scrape_user_data(
                    username,
                    limit=max_posts
                )
                
                # Convert user posts to new structure
                converted_posts = []
                for user_post in user_posts:
                    if len(converted_posts) >= max_posts:
                        break
                        
                    # Convert old user post structure to new structure
                    post_info = {
                        "title": user_post.get("title", ""),
                        "author": {
                            "username": username,
                            "profile_url": f"https://reddit.com/user/{username}"
                        },
                        "content": "",
                        "metadata": {
                            "score": 0,
                            "num_comments": 0,
                            "created_utc": user_post.get("created_utc", 0),
                            "subreddit": user_post.get("subreddit", ""),
                            "permalink": "",
                            "url": user_post.get("url", "")
                        },
                        "comments": [],
                        "users": []
                    }
                    
                    # Add post author to users if requested
                    if max_users_per_post > 0:
                        post_info["users"].append({
                            "username": username,
                            "role": "author",
                            "profile_url": f"https://reddit.com/user/{username}"
                        })
                    
                    converted_posts.append(post_info)
                
                # Filter user posts by date if specified
                if params.get('postDateLimit'):
                    converted_posts = self._filter_posts_by_date(converted_posts, params['postDateLimit'])
                
                results['posts'].extend(converted_posts)
        
        # Scrape individual posts
        for post_info in categorized['posts']:
            if params.get('searchForPosts', True):
                permalink = f"/r/{post_info['subreddit']}/comments/{post_info['post_id']}"
                post_details = self.scrape_post_details(permalink)
                
                if post_details:
                    # Build new post structure
                    post_with_details = {
                        "title": post_details['title'],
                        "author": {
                            "username": "unknown",
                            "profile_url": ""
                        },
                        "content": post_details['body'],
                        "metadata": {
                            "score": 0,
                            "num_comments": len(post_details.get('comments', [])),
                            "created_utc": 0,
                            "subreddit": post_info['subreddit'],
                            "permalink": permalink,
                            "url": post_info['url']
                        },
                        "comments": post_details.get('comments', [])[:max_comments_per_post] if max_comments_per_post > 0 else [],
                        "users": []
                    }
                    
                    # Extract users if requested
                    if max_users_per_post > 0:
                        users = self._extract_users_from_post(post_with_details, max_users_per_post)
                        post_with_details["users"] = users
                    
                    results['posts'].append(post_with_details)
        
        # Apply maxPosts limit
        results['posts'] = results['posts'][:max_posts]
        
        logging.info("URL-based scraping completed: %d posts", len(results['posts']))
        
        return results
    
    def _filter_posts_by_date(self, posts: List[Dict[str, Any]], date_limit: datetime) -> List[Dict[str, Any]]:
        """Filter posts by date limit"""
        filtered_posts = []
        
        for post in posts:
            # Handle both old and new post structures
            created_utc = post.get('created_utc', 0)
            if created_utc == 0 and 'metadata' in post:
                created_utc = post['metadata'].get('created_utc', 0)
            
            post_date = datetime.fromtimestamp(created_utc)
            if post_date >= date_limit:
                filtered_posts.append(post)
        
        return filtered_posts
    
    def _filter_user_posts_by_date(self, user_posts: List[Dict[str, Any]], date_limit: datetime) -> List[Dict[str, Any]]:
        """Filter user posts by date limit"""
        filtered_posts = []
        
        for post in user_posts:
            post_date = datetime.fromtimestamp(post.get('created_utc', 0))
            if post_date >= date_limit:
                filtered_posts.append(post)
        
        return filtered_posts
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics for the current session"""
        return {
            "proxy_configured": bool(self.proxy),
            "proxy_url": self.proxy if self.proxy else None,
            "timeout": self.timeout,
            "session_type": "RandomUserAgent" if isinstance(self.session, RandomUserAgentSession) else "Standard"
        }
