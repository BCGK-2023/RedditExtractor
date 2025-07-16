import threading
import time
import logging
from typing import Dict, Any
from datetime import datetime

from yars import YARS
from jobs import get_job_manager, JobStatus
from webhooks import get_webhook_delivery
from validator import YARSValidator
from formatters import OutputFormatter

class BackgroundWorker:
    """
    Background worker to process scraping jobs asynchronously
    """
    
    def __init__(self):
        self.job_manager = get_job_manager()
        self.webhook_delivery = get_webhook_delivery()
        self.is_running = False
        self.worker_thread = None
        self.check_interval = 5  # Check for new jobs every 5 seconds
    
    def start(self):
        """Start the background worker"""
        if self.is_running:
            return
        
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logging.info("Background worker started")
    
    def stop(self):
        """Stop the background worker"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=10)
        logging.info("Background worker stopped")
    
    def _worker_loop(self):
        """Main worker loop"""
        while self.is_running:
            try:
                # Find pending jobs
                pending_jobs = self._get_pending_jobs()
                
                for job_id in pending_jobs:
                    if not self.is_running:
                        break
                    
                    # Process the job
                    self._process_job(job_id)
                
                # Sleep before checking for more jobs
                time.sleep(self.check_interval)
                
            except Exception as e:
                logging.error(f"Error in background worker: {e}")
                time.sleep(self.check_interval)
    
    def _get_pending_jobs(self):
        """Get list of pending job IDs"""
        pending_jobs = []
        
        # Get recent jobs and filter for pending ones
        recent_jobs = self.job_manager.get_recent_jobs(limit=100)
        for job in recent_jobs:
            if job.get("status") == JobStatus.PENDING.value:
                pending_jobs.append(job["id"])
        
        return pending_jobs
    
    def _process_job(self, job_id: str):
        """Process a single scraping job"""
        try:
            # Get job details
            job = self.job_manager.get_job(job_id)
            if not job:
                logging.error(f"Job {job_id} not found")
                return
            
            # Mark job as running
            self.job_manager.update_job_status(job_id, JobStatus.RUNNING)
            logging.info(f"Starting job {job_id}")
            
            # Extract job parameters
            params = job.get("parameters", {})
            webhook_url = job.get("webhook_url")
            
            # Initialize YARS scraper
            miner = YARS()
            
            # Perform the scraping based on parameters
            start_time = time.time()
            
            if params.get('startUrls'):
                # URL-based scraping
                results = miner.scrape_by_urls(params['startUrls'], params)
            elif params.get('searchTerm'):
                # Search-based scraping
                search_results = miner.search_reddit_global(
                    params['searchTerm'],
                    limit=params.get('maxItems', 100),
                    sort=params.get('sortSearch', 'relevance'),
                    time_filter=params.get('filterByDate', 'all')
                )
                
                # Filter results based on parameters
                results = {
                    "posts": search_results if params.get('searchForPosts', True) else [],
                    "comments": [],
                    "users": [],
                    "communities": []
                }
                
                # Get comments for posts if requested
                if params.get('searchForComments', True) and not params.get('skipComments', False):
                    comment_count = 0
                    max_comments = params.get('commentsPerPage', 20)
                    
                    for post in results['posts'][:5]:  # Limit comment scraping to first 5 posts
                        if comment_count >= max_comments:
                            break
                            
                        if post.get('permalink'):
                            try:
                                post_details = miner.scrape_post_details(post['permalink'])
                                if post_details and post_details.get('comments'):
                                    remaining_comments = max_comments - comment_count
                                    new_comments = post_details['comments'][:remaining_comments]
                                    results['comments'].extend(new_comments)
                                    comment_count += len(new_comments)
                                    
                                    # Update progress
                                    self.job_manager.update_job_progress(job_id, len(results['posts']) + comment_count)
                                    
                            except Exception as e:
                                logging.warning(f"Failed to get comments for post {post.get('permalink')}: {e}")
            else:
                raise ValueError("No valid scraping parameters provided")
            
            # Apply NSFW filtering if needed
            if not params.get('includeNSFW', False):
                results['posts'] = [post for post in results['posts'] if not post.get('over_18', False)]
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Create success response
            response = YARSValidator.create_success_response(results, params, execution_time)
            
            # Handle output format for webhook delivery
            output_format = params.get('outputFormat', 'json')
            
            if output_format != 'json' and webhook_url:
                # Format the data for webhook delivery
                try:
                    formatted_data = OutputFormatter.format_data(
                        results, 
                        output_format, 
                        response.get('metadata', {})
                    )
                    # Include formatted data in the response for webhook
                    response['formatted_data'] = {
                        'format': output_format,
                        'content_type': OutputFormatter.get_content_type(output_format),
                        'data': formatted_data
                    }
                except Exception as format_error:
                    logging.warning(f"Failed to format data as {output_format} for job {job_id}: {format_error}")
            
            # Mark job as completed
            self.job_manager.complete_job(job_id, response)
            logging.info(f"Job {job_id} completed successfully in {execution_time:.2f}s")
            
            # Deliver webhook if provided
            if webhook_url:
                success = self.webhook_delivery.deliver_webhook(webhook_url, job)
                if success:
                    logging.info(f"Webhook delivered for job {job_id}")
                else:
                    logging.warning(f"Failed to deliver webhook for job {job_id}")
        
        except Exception as e:
            # Mark job as failed
            error_message = str(e)
            self.job_manager.fail_job(job_id, error_message)
            logging.error(f"Job {job_id} failed: {error_message}")
            
            # Try to deliver failure webhook
            if job and job.get("webhook_url"):
                try:
                    self.webhook_delivery.deliver_webhook(job["webhook_url"], job)
                except Exception as webhook_error:
                    logging.error(f"Failed to deliver failure webhook for job {job_id}: {webhook_error}")

# Global background worker instance
background_worker = BackgroundWorker()

def get_background_worker() -> BackgroundWorker:
    """Get the global background worker instance"""
    return background_worker

def start_background_worker():
    """Start the background worker"""
    background_worker.start()

def stop_background_worker():
    """Stop the background worker"""
    background_worker.stop()