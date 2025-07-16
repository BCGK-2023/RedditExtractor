import requests
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

class WebhookDelivery:
    """
    Handles webhook delivery for completed scraping jobs
    """
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        
        # Set up session headers
        self.session.headers.update({
            'User-Agent': 'RedditExtractor-Webhook/1.0',
            'Content-Type': 'application/json'
        })
    
    def deliver_webhook(self, webhook_url: str, job_data: Dict[str, Any]) -> bool:
        """
        Deliver webhook payload to the specified URL
        
        Args:
            webhook_url: The URL to send the webhook to
            job_data: The job result data to send
            
        Returns:
            bool: True if delivery was successful, False otherwise
        """
        if not webhook_url:
            return False
        
        # Prepare webhook payload
        payload = self._prepare_payload(job_data)
        
        # Attempt delivery with retries
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    webhook_url,
                    json=payload,
                    timeout=self.timeout
                )
                
                # Check if delivery was successful
                if 200 <= response.status_code < 300:
                    logging.info(f"Webhook delivered successfully to {webhook_url} (attempt {attempt + 1})")
                    return True
                else:
                    logging.warning(f"Webhook delivery failed with status {response.status_code} (attempt {attempt + 1})")
                    
            except requests.exceptions.Timeout:
                logging.warning(f"Webhook delivery timeout to {webhook_url} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError:
                logging.warning(f"Webhook delivery connection error to {webhook_url} (attempt {attempt + 1})")
            except Exception as e:
                logging.error(f"Webhook delivery error to {webhook_url}: {e} (attempt {attempt + 1})")
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                import time
                time.sleep(2 ** attempt)
        
        logging.error(f"Webhook delivery failed after {self.max_retries} attempts to {webhook_url}")
        return False
    
    def _prepare_payload(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare the webhook payload
        
        Args:
            job_data: The job data from the job manager
            
        Returns:
            Dict containing the webhook payload
        """
        # Extract the result data
        result = job_data.get("result", {})
        
        # Create webhook payload
        payload = {
            "jobId": job_data.get("id"),
            "status": job_data.get("status"),
            "completedAt": job_data.get("completed_at"),
            "executionTime": self._calculate_execution_time(job_data),
            "webhook": {
                "deliveredAt": datetime.utcnow().isoformat() + "Z",
                "version": "1.0"
            }
        }
        
        # Add result data if job completed successfully
        if job_data.get("status") == "completed" and result:
            payload.update({
                "success": result.get("success", True),
                "data": result.get("data", {}),
                "metadata": result.get("metadata", {}),
                "errors": result.get("errors", [])
            })
        
        # Add error information if job failed
        elif job_data.get("status") == "failed":
            payload.update({
                "success": False,
                "data": None,
                "errors": [
                    {
                        "code": "JOB_FAILED",
                        "message": "Scraping job failed",
                        "details": job_data.get("error", "Unknown error")
                    }
                ]
            })
        
        return payload
    
    def _calculate_execution_time(self, job_data: Dict[str, Any]) -> Optional[str]:
        """Calculate job execution time"""
        started_at = job_data.get("started_at")
        completed_at = job_data.get("completed_at")
        
        if not started_at or not completed_at:
            return None
        
        try:
            from datetime import datetime
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            duration = end_time - start_time
            return f"{duration.total_seconds():.2f}s"
        except Exception:
            return None
    
    def test_webhook_url(self, webhook_url: str) -> Dict[str, Any]:
        """
        Test if a webhook URL is reachable
        
        Args:
            webhook_url: The URL to test
            
        Returns:
            Dict with test results
        """
        test_payload = {
            "test": True,
            "message": "RedditExtractor webhook test",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            response = self.session.post(
                webhook_url,
                json=test_payload,
                timeout=10
            )
            
            return {
                "success": True,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds(),
                "reachable": True
            }
            
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Webhook URL timeout",
                "reachable": False
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "Cannot connect to webhook URL",
                "reachable": False
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "reachable": False
            }

# Global webhook delivery instance
webhook_delivery = WebhookDelivery()

def get_webhook_delivery() -> WebhookDelivery:
    """Get the global webhook delivery instance"""
    return webhook_delivery