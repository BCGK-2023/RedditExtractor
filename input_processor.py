import re
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class SourceType(Enum):
    REDDIT_URL = "reddit_url"
    SUBREDDIT_NAME = "subreddit_name"
    USER_NAME = "user_name"
    SEARCH_TERM = "search_term"

@dataclass
class ProcessedSource:
    original: str
    type: SourceType
    normalized: str
    reddit_url: Optional[str] = None
    estimated_items: int = 100

class SmartInputProcessor:
    """
    Intelligent processor that handles mixed URL and search term sources
    """
    
    @staticmethod
    def process_sources(sources: List[str], limits: Dict[str, Any]) -> Tuple[List[ProcessedSource], Dict[str, Any]]:
        """
        Process mixed sources and return organized processing plan
        
        Returns:
            - List of ProcessedSource objects
            - Processing strategy dict
        """
        processed_sources = []
        
        for source in sources:
            processed = SmartInputProcessor._process_single_source(source.strip())
            processed_sources.append(processed)
        
        # Create processing strategy
        strategy = SmartInputProcessor._create_processing_strategy(processed_sources, limits)
        
        return processed_sources, strategy
    
    @staticmethod
    def _process_single_source(source: str) -> ProcessedSource:
        """Process a single source and determine its type"""
        
        # Reddit URL patterns
        reddit_url_patterns = [
            (r'^https?://(www\.|old\.)?reddit\.com/r/(\w+)/?$', SourceType.REDDIT_URL, 'subreddit'),
            (r'^https?://(www\.|old\.)?reddit\.com/user/(\w+)/?$', SourceType.REDDIT_URL, 'user'),
            (r'^https?://(www\.|old\.)?reddit\.com/r/(\w+)/comments/.*', SourceType.REDDIT_URL, 'post')
        ]
        
        for pattern, source_type, url_type in reddit_url_patterns:
            match = re.match(pattern, source)
            if match:
                return ProcessedSource(
                    original=source,
                    type=source_type,
                    normalized=source,
                    reddit_url=source,
                    estimated_items=SmartInputProcessor._estimate_items_for_url(source, url_type)
                )
        
        # Subreddit shorthand (r/programming)
        subreddit_match = re.match(r'^r/(\w+)$', source)
        if subreddit_match:
            subreddit_name = subreddit_match.group(1)
            reddit_url = f"https://reddit.com/r/{subreddit_name}"
            return ProcessedSource(
                original=source,
                type=SourceType.SUBREDDIT_NAME,
                normalized=subreddit_name,
                reddit_url=reddit_url,
                estimated_items=100
            )
        
        # User shorthand (u/username)
        user_match = re.match(r'^u/(\w+)$', source)
        if user_match:
            username = user_match.group(1)
            reddit_url = f"https://reddit.com/user/{username}"
            return ProcessedSource(
                original=source,
                type=SourceType.USER_NAME,
                normalized=username,
                reddit_url=reddit_url,
                estimated_items=50
            )
        
        # Bare subreddit name (programming)
        if re.match(r'^\w+$', source) and len(source) > 2:
            reddit_url = f"https://reddit.com/r/{source}"
            return ProcessedSource(
                original=source,
                type=SourceType.SUBREDDIT_NAME,
                normalized=source,
                reddit_url=reddit_url,
                estimated_items=100
            )
        
        # Everything else is a search term
        return ProcessedSource(
            original=source,
            type=SourceType.SEARCH_TERM,
            normalized=source,
            estimated_items=200
        )
    
    @staticmethod
    def _estimate_items_for_url(url: str, url_type: str) -> int:
        """Estimate how many items a URL might return"""
        estimates = {
            'subreddit': 100,
            'user': 50,
            'post': 25  # Post + comments
        }
        return estimates.get(url_type, 100)
    
    @staticmethod
    def _create_processing_strategy(sources: List[ProcessedSource], limits: Dict[str, Any]) -> Dict[str, Any]:
        """Create optimized processing strategy based on sources and limits"""
        
        total_items = limits.get('totalItems', 100)
        items_per_source = limits.get('itemsPerSource')
        
        # Group sources by type
        url_sources = [s for s in sources if s.type == SourceType.REDDIT_URL or s.reddit_url]
        search_sources = [s for s in sources if s.type == SourceType.SEARCH_TERM]
        
        # Calculate distribution
        if items_per_source:
            # Fixed per-source allocation
            distribution = {
                source.original: min(items_per_source, total_items // len(sources))
                for source in sources
            }
        else:
            # Smart distribution based on estimated capacity
            total_estimated = sum(s.estimated_items for s in sources)
            distribution = {}
            
            for source in sources:
                # Proportional allocation based on estimated capacity
                proportion = source.estimated_items / total_estimated
                allocated = int(total_items * proportion)
                distribution[source.original] = max(1, allocated)
        
        # Ensure we don't exceed total_items
        current_total = sum(distribution.values())
        if current_total > total_items:
            # Scale down proportionally
            scale_factor = total_items / current_total
            for key in distribution:
                distribution[key] = max(1, int(distribution[key] * scale_factor))
        
        strategy = {
            "distribution": distribution,
            "processing_order": SmartInputProcessor._optimize_processing_order(sources),
            "url_sources": [s.original for s in url_sources],
            "search_sources": [s.original for s in search_sources],
            "mixed_mode": len(url_sources) > 0 and len(search_sources) > 0,
            "total_estimated_time": SmartInputProcessor._estimate_processing_time(sources, distribution)
        }
        
        return strategy
    
    @staticmethod
    def _optimize_processing_order(sources: List[ProcessedSource]) -> List[str]:
        """Optimize the order of processing sources for best performance"""
        
        # Priority order: URLs first (faster), then search terms
        url_sources = [s for s in sources if s.type != SourceType.SEARCH_TERM]
        search_sources = [s for s in sources if s.type == SourceType.SEARCH_TERM]
        
        # Sort URLs by estimated speed (posts fastest, then users, then subreddits)
        url_priority = {
            'post': 1,
            'user': 2,
            'subreddit': 3
        }
        
        def get_url_priority(source):
            if 'comments/' in source.reddit_url or '/comments/' in source.reddit_url:
                return url_priority['post']
            elif '/user/' in source.reddit_url:
                return url_priority['user']
            else:
                return url_priority['subreddit']
        
        url_sources.sort(key=get_url_priority)
        
        # Return optimized order
        ordered = [s.original for s in url_sources] + [s.original for s in search_sources]
        return ordered
    
    @staticmethod
    def _estimate_processing_time(sources: List[ProcessedSource], distribution: Dict[str, int]) -> float:
        """Estimate total processing time in seconds"""
        
        # Base time estimates (seconds per item)
        time_per_item = {
            SourceType.REDDIT_URL: 0.1,
            SourceType.SUBREDDIT_NAME: 0.1,
            SourceType.USER_NAME: 0.15,
            SourceType.SEARCH_TERM: 0.2
        }
        
        total_time = 0
        for source in sources:
            items_count = distribution.get(source.original, 0)
            item_time = time_per_item.get(source.type, 0.1)
            total_time += items_count * item_time
        
        # Add base overhead
        total_time += 2.0  # Base processing overhead
        
        return total_time
    
    @staticmethod
    def convert_to_legacy_params(processed_sources: List[ProcessedSource], strategy: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert processed sources back to legacy parameter format for existing scraping logic
        """
        legacy_params = {}
        
        # Separate URLs and search terms
        urls = []
        search_terms = []
        
        for source in processed_sources:
            if source.reddit_url and source.type != SourceType.SEARCH_TERM:
                urls.append(source.reddit_url)
            else:
                search_terms.append(source.normalized)
        
        # Set appropriate legacy parameters
        if urls and not search_terms:
            # URL-only mode
            legacy_params['startUrls'] = urls
        elif search_terms and not urls:
            # Search-only mode (combine multiple search terms)
            legacy_params['searchTerm'] = ' OR '.join(f'({term})' for term in search_terms)
        else:
            # Mixed mode - prioritize URLs, add search terms as additional context
            legacy_params['startUrls'] = urls
            if search_terms:
                legacy_params['_additionalSearchTerms'] = search_terms
        
        return legacy_params
    
    @staticmethod
    def create_processing_report(sources: List[ProcessedSource], strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed report of how sources will be processed"""
        
        source_analysis = []
        for source in sources:
            analysis = {
                "input": source.original,
                "detected_type": source.type.value,
                "normalized": source.normalized,
                "reddit_url": source.reddit_url,
                "allocated_items": strategy["distribution"].get(source.original, 0),
                "estimated_items": source.estimated_items
            }
            source_analysis.append(analysis)
        
        report = {
            "total_sources": len(sources),
            "source_breakdown": {
                "urls": len([s for s in sources if s.type != SourceType.SEARCH_TERM]),
                "search_terms": len([s for s in sources if s.type == SourceType.SEARCH_TERM])
            },
            "processing_strategy": {
                "mode": "mixed" if strategy["mixed_mode"] else "uniform",
                "estimated_duration": f"{strategy['total_estimated_time']:.1f}s",
                "processing_order": strategy["processing_order"]
            },
            "source_analysis": source_analysis,
            "item_distribution": strategy["distribution"]
        }
        
        return report