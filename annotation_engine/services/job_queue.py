"""
AnnotationEngine Desktop - Job Queue
"""
import uuid
from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication


@dataclass
class Job:
    id: str
    job_type: str
    func: Callable
    args: tuple
    kwargs: dict
    priority: int = 0


class JobWorker(QObject):
    """Worker for executing jobs in a separate thread."""
    
    progress = Signal(int, str)  # percent, message
    finished = Signal(dict)      # result
    error = Signal(str)          # error message
    
    def __init__(self, job: Job):
        super().__init__()
        self.job = job
        self._cancelled = False
    
    @Slot()
    def run(self):
        """Execute the job."""
        try:
            def progress_callback(percent: int, message: str = ""):
                if self._cancelled:
                    raise InterruptedError("Job cancelled")
                self.progress.emit(percent, message)
            
            # Add progress callback to kwargs
            self.job.kwargs['progress_callback'] = progress_callback
            
            result = self.job.func(*self.job.args, **self.job.kwargs)
            self.finished.emit(result or {})
            
        except InterruptedError:
            self.error.emit("Job cancelled")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
    
    def cancel(self):
        """Request job cancellation."""
        self._cancelled = True


class JobQueue(QObject):
    """Job queue for background processing."""
    
    # Signals
    jobStarted = Signal(str)
    jobProgress = Signal(str, int, str)
    jobFinished = Signal(str, dict)
    jobFailed = Signal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.jobs: Dict[str, Job] = {}
        self.workers: Dict[str, JobWorker] = {}
        self.threads: Dict[str, QThread] = {}
        self.running = False
    
    def enqueue(self, job_type: str, func: Callable, *args, 
                priority: int = 0, **kwargs) -> str:
        """Add a job to the queue."""
        job_id = str(uuid.uuid4())[:8]
        
        job = Job(
            id=job_id,
            job_type=job_type,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority
        )
        
        self.jobs[job_id] = job
        
        # Start if not running
        if not self.running:
            self._process_queue()
        
        return job_id
    
    def _process_queue(self):
        """Process pending jobs."""
        self.running = True
        
        # Find highest priority job
        pending = [j for j in self.jobs.values() if j.id not in self.workers]
        if not pending:
            self.running = False
            return
        
        # Sort by priority (higher first)
        pending.sort(key=lambda j: j.priority, reverse=True)
        job = pending[0]
        
        self._start_job(job)
    
    def _start_job(self, job: Job):
        """Start a job in a new thread."""
        thread = QThread()
        worker = JobWorker(job)
        worker.moveToThread(thread)
        
        # Connect signals
        thread.started.connect(worker.run)
        worker.finished.connect(lambda r: self._on_job_finished(job.id, r))
        worker.error.connect(lambda e: self._on_job_error(job.id, e))
        worker.progress.connect(lambda p, m: self.jobProgress.emit(job.id, p, m))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        
        self.workers[job.id] = worker
        self.threads[job.id] = thread
        
        thread.start()
        self.jobStarted.emit(job.id)
    
    def _on_job_finished(self, job_id: str, result: dict):
        """Handle job completion."""
        self._cleanup_job(job_id)
        self.jobFinished.emit(job_id, result)
        self._process_queue()
    
    def _on_job_error(self, job_id: str, error: str):
        """Handle job error."""
        self._cleanup_job(job_id)
        self.jobFailed.emit(job_id, error)
        self._process_queue()
    
    def _cleanup_job(self, job_id: str):
        """Clean up job resources."""
        if job_id in self.workers:
            del self.workers[job_id]
        if job_id in self.threads:
            del self.threads[job_id]
        if job_id in self.jobs:
            del self.jobs[job_id]
    
    def cancel_job(self, job_id: str):
        """Cancel a running job."""
        if job_id in self.workers:
            self.workers[job_id].cancel()
    
    def cancel_all(self):
        """Cancel all running jobs."""
        for job_id in list(self.workers.keys()):
            self.cancel_job(job_id)
    
    def get_job_status(self, job_id: str) -> Optional[str]:
        """Get job status."""
        if job_id in self.workers:
            return "running"
        elif job_id in self.jobs:
            return "pending"
        return "unknown"
    
    def shutdown(self):
        """Shutdown the job queue."""
        self.cancel_all()
        # Wait for threads to finish
        for thread in self.threads.values():
            thread.wait(5000)