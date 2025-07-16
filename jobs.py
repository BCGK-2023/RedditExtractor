import json
import time
import uuid
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobManager:
    """
    Simple in-memory job queue manager for async scraping tasks.
    For production, consider using Redis or a proper message queue.
    """
    
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.cleanup_interval = 3600  # 1 hour
        self.max_job_age = 86400  # 24 hours
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_old_jobs, daemon=True)
        self.cleanup_thread.start()
    
    def create_job(self, scrape_params: Dict[str, Any], webhook_url: Optional[str] = None) -> str:
        """Create a new scraping job"""
        job_id = str(uuid.uuid4())
        
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "status": JobStatus.PENDING.value,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "started_at": None,
                "completed_at": None,
                "parameters": scrape_params,
                "webhook_url": webhook_url,
                "result": None,
                "error": None,
                "progress": 0,
                "total_items": scrape_params.get("maxItems", 100),
                "items_scraped": 0
            }
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        with self.lock:
            return self.jobs.get(job_id)
    
    def update_job_status(self, job_id: str, status: JobStatus, **kwargs):
        """Update job status and metadata"""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = status.value
                
                if status == JobStatus.RUNNING and not self.jobs[job_id]["started_at"]:
                    self.jobs[job_id]["started_at"] = datetime.utcnow().isoformat() + "Z"
                
                if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    self.jobs[job_id]["completed_at"] = datetime.utcnow().isoformat() + "Z"
                
                # Update any additional fields
                for key, value in kwargs.items():
                    self.jobs[job_id][key] = value
    
    def update_job_progress(self, job_id: str, items_scraped: int):
        """Update job progress"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job["items_scraped"] = items_scraped
                total_items = job.get("total_items", 100)
                job["progress"] = min(100, int((items_scraped / total_items) * 100))
    
    def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Mark job as completed with result"""
        self.update_job_status(
            job_id, 
            JobStatus.COMPLETED, 
            result=result,
            items_scraped=result.get("metadata", {}).get("itemsReturned", 0),
            progress=100
        )
    
    def fail_job(self, job_id: str, error: str):
        """Mark job as failed with error"""
        self.update_job_status(job_id, JobStatus.FAILED, error=error)
    
    def get_jobs_summary(self) -> Dict[str, Any]:
        """Get summary of all jobs"""
        with self.lock:
            total_jobs = len(self.jobs)
            status_counts = {}
            
            for job in self.jobs.values():
                status = job["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_jobs": total_jobs,
                "status_breakdown": status_counts,
                "active_jobs": status_counts.get("pending", 0) + status_counts.get("running", 0)
            }
    
    def get_recent_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent jobs"""
        with self.lock:
            jobs_list = list(self.jobs.values())
            # Sort by created_at descending
            jobs_list.sort(key=lambda x: x["created_at"], reverse=True)
            return jobs_list[:limit]
    
    def _cleanup_old_jobs(self):
        """Background thread to clean up old completed jobs"""
        while True:
            try:
                cutoff_time = datetime.utcnow() - timedelta(seconds=self.max_job_age)
                cutoff_iso = cutoff_time.isoformat() + "Z"
                
                with self.lock:
                    jobs_to_remove = []
                    for job_id, job in self.jobs.items():
                        # Remove old completed/failed jobs
                        if (job["status"] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value] and
                            job["created_at"] < cutoff_iso):
                            jobs_to_remove.append(job_id)
                    
                    for job_id in jobs_to_remove:
                        del self.jobs[job_id]
                
                if jobs_to_remove:
                    print(f"Cleaned up {len(jobs_to_remove)} old jobs")
                
            except Exception as e:
                print(f"Error during job cleanup: {e}")
            
            time.sleep(self.cleanup_interval)

# Global job manager instance
job_manager = JobManager()

def get_job_manager() -> JobManager:
    """Get the global job manager instance"""
    return job_manager