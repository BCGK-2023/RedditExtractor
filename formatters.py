import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Any, Optional
from io import StringIO
from email.utils import formatdate
import time

class OutputFormatter:
    """
    Handles formatting of scraped Reddit data into different output formats
    """
    
    @staticmethod
    def format_data(data: Dict[str, Any], output_format: str, metadata: Dict[str, Any] = None) -> str:
        """
        Format data into the specified output format
        
        Args:
            data: The scraped data dictionary
            output_format: The desired output format ('json', 'csv', 'rss', 'xml')
            metadata: Additional metadata for formatting
            
        Returns:
            Formatted string data
        """
        metadata = metadata or {}
        
        if output_format == 'json':
            return OutputFormatter._format_json(data)
        elif output_format == 'csv':
            return OutputFormatter._format_csv(data)
        elif output_format == 'rss':
            return OutputFormatter._format_rss(data, metadata)
        elif output_format == 'xml':
            return OutputFormatter._format_xml(data, metadata)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
    
    @staticmethod
    def _format_json(data: Dict[str, Any]) -> str:
        """Format data as JSON"""
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    @staticmethod
    def _format_csv(data: Dict[str, Any]) -> str:
        """Format data as CSV"""
        output = StringIO()
        
        # Get all posts and comments
        posts = data.get('posts', [])
        comments = data.get('comments', [])
        
        if posts:
            # Write posts CSV
            if posts:
                writer = csv.writer(output)
                
                # Write header for posts
                post_headers = [
                    'type', 'id', 'title', 'url', 'author', 'subreddit', 
                    'score', 'num_comments', 'created_utc', 'permalink',
                    'selftext', 'domain', 'is_nsfw', 'is_pinned'
                ]
                writer.writerow(post_headers)
                
                # Write post data
                for post in posts:
                    row = [
                        'post',
                        post.get('id', ''),
                        post.get('title', '').replace('\n', ' ').replace('\r', ' '),
                        post.get('url', ''),
                        post.get('author', ''),
                        post.get('subreddit', ''),
                        post.get('score', 0),
                        post.get('num_comments', 0),
                        post.get('created_utc', ''),
                        post.get('permalink', ''),
                        (post.get('selftext', '') or '').replace('\n', ' ').replace('\r', ' ')[:500],
                        post.get('domain', ''),
                        post.get('over_18', False),
                        post.get('pinned', False)
                    ]
                    writer.writerow(row)
        
        if comments:
            # Add separator if we have both posts and comments
            if posts:
                output.write('\n')
            
            writer = csv.writer(output)
            
            # Write header for comments
            comment_headers = [
                'type', 'id', 'body', 'author', 'subreddit',
                'score', 'created_utc', 'permalink', 'parent_id', 'post_title'
            ]
            writer.writerow(comment_headers)
            
            # Write comment data
            for comment in comments:
                row = [
                    'comment',
                    comment.get('id', ''),
                    (comment.get('body', '') or '').replace('\n', ' ').replace('\r', ' ')[:500],
                    comment.get('author', ''),
                    comment.get('subreddit', ''),
                    comment.get('score', 0),
                    comment.get('created_utc', ''),
                    comment.get('permalink', ''),
                    comment.get('parent_id', ''),
                    (comment.get('post_title', '') or '').replace('\n', ' ').replace('\r', ' ')
                ]
                writer.writerow(row)
        
        return output.getvalue()
    
    @staticmethod
    def _format_rss(data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Format data as RSS feed"""
        posts = data.get('posts', [])
        request_params = metadata.get('requestParams', {})
        
        # Create RSS structure
        rss = ET.Element('rss', version='2.0')
        rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
        
        channel = ET.SubElement(rss, 'channel')
        
        # Channel metadata
        title_text = "RedditExtractor Feed"
        if request_params.get('searchTerm'):
            title_text = f"Reddit Search: {request_params['searchTerm']}"
        elif request_params.get('startUrls'):
            title_text = f"Reddit Content from {len(request_params['startUrls'])} sources"
        
        title = ET.SubElement(channel, 'title')
        title.text = title_text
        
        description = ET.SubElement(channel, 'description')
        description.text = f"Reddit content extracted by RedditExtractor - {len(posts)} posts"
        
        link = ET.SubElement(channel, 'link')
        link.text = "https://reddit.com"
        
        generator = ET.SubElement(channel, 'generator')
        generator.text = "RedditExtractor API"
        
        last_build_date = ET.SubElement(channel, 'lastBuildDate')
        last_build_date.text = formatdate(time.time())
        
        # Add posts as RSS items
        for post in posts[:50]:  # Limit to 50 items for RSS
            item = ET.SubElement(channel, 'item')
            
            item_title = ET.SubElement(item, 'title')
            item_title.text = post.get('title', 'Untitled Post')
            
            item_link = ET.SubElement(item, 'link')
            item_link.text = post.get('url', f"https://reddit.com{post.get('permalink', '')}")
            
            item_description = ET.SubElement(item, 'description')
            description_text = post.get('selftext', '') or f"Reddit post from r/{post.get('subreddit', 'unknown')}"
            if len(description_text) > 500:
                description_text = description_text[:500] + "..."
            item_description.text = description_text
            
            item_author = ET.SubElement(item, 'author')
            item_author.text = f"u/{post.get('author', 'unknown')}"
            
            item_category = ET.SubElement(item, 'category')
            item_category.text = f"r/{post.get('subreddit', 'unknown')}"
            
            item_guid = ET.SubElement(item, 'guid', isPermaLink='false')
            item_guid.text = post.get('id', '')
            
            # Convert created_utc to pubDate
            if post.get('created_utc'):
                try:
                    created_timestamp = float(post['created_utc'])
                    pub_date = ET.SubElement(item, 'pubDate')
                    pub_date.text = formatdate(created_timestamp)
                except (ValueError, TypeError):
                    pass
        
        # Convert to string
        return ET.tostring(rss, encoding='unicode', xml_declaration=True)
    
    @staticmethod
    def _format_xml(data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Format data as XML"""
        root = ET.Element('redditData')
        
        # Add metadata
        meta_elem = ET.SubElement(root, 'metadata')
        for key, value in metadata.items():
            meta_child = ET.SubElement(meta_elem, key)
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    sub_elem = ET.SubElement(meta_child, subkey)
                    sub_elem.text = str(subvalue) if subvalue is not None else ''
            else:
                meta_child.text = str(value) if value is not None else ''
        
        # Add posts
        if data.get('posts'):
            posts_elem = ET.SubElement(root, 'posts')
            for post in data['posts']:
                post_elem = ET.SubElement(posts_elem, 'post')
                for key, value in post.items():
                    if value is not None:
                        child = ET.SubElement(post_elem, key)
                        if isinstance(value, (dict, list)):
                            child.text = json.dumps(value)
                        else:
                            child.text = str(value)
        
        # Add comments
        if data.get('comments'):
            comments_elem = ET.SubElement(root, 'comments')
            for comment in data['comments']:
                comment_elem = ET.SubElement(comments_elem, 'comment')
                for key, value in comment.items():
                    if value is not None:
                        child = ET.SubElement(comment_elem, key)
                        if isinstance(value, (dict, list)):
                            child.text = json.dumps(value)
                        else:
                            child.text = str(value)
        
        # Add users
        if data.get('users'):
            users_elem = ET.SubElement(root, 'users')
            for user in data['users']:
                user_elem = ET.SubElement(users_elem, 'user')
                for key, value in user.items():
                    if value is not None:
                        child = ET.SubElement(user_elem, key)
                        if isinstance(value, (dict, list)):
                            child.text = json.dumps(value)
                        else:
                            child.text = str(value)
        
        # Add communities
        if data.get('communities'):
            communities_elem = ET.SubElement(root, 'communities')
            for community in data['communities']:
                community_elem = ET.SubElement(communities_elem, 'community')
                for key, value in community.items():
                    if value is not None:
                        child = ET.SubElement(community_elem, key)
                        if isinstance(value, (dict, list)):
                            child.text = json.dumps(value)
                        else:
                            child.text = str(value)
        
        return ET.tostring(root, encoding='unicode', xml_declaration=True)
    
    @staticmethod
    def get_content_type(output_format: str) -> str:
        """Get the appropriate Content-Type header for the output format"""
        content_types = {
            'json': 'application/json',
            'csv': 'text/csv',
            'rss': 'application/rss+xml',
            'xml': 'application/xml'
        }
        return content_types.get(output_format, 'application/json')
    
    @staticmethod
    def get_file_extension(output_format: str) -> str:
        """Get the appropriate file extension for the output format"""
        extensions = {
            'json': 'json',
            'csv': 'csv', 
            'rss': 'xml',
            'xml': 'xml'
        }
        return extensions.get(output_format, 'json')