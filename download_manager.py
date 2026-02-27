"""
Download Manager Module
Handles actual file downloads with progress tracking, pause/resume, and queue management.
"""

import os
import threading
import time
import urllib.request
import urllib.parse
from queue import Queue
from datetime import datetime
from enum import Enum


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadTask:
    def __init__(self, url, filename, save_path):
        self.id = f"{int(time.time() * 1000)}_{hash(url)}"
        self.url = url
        self.filename = filename
        self.save_path = save_path
        self.full_path = os.path.join(save_path, filename)
        self.status = DownloadStatus.PENDING
        self.progress = 0.0
        self.total_size = 0
        self.downloaded_size = 0
        self.speed = 0.0
        self.error_message = ""
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self._stop_flag = False
        self._pause_flag = False
        
    def should_stop(self):
        return self._stop_flag
    
    def should_pause(self):
        return self._pause_flag
    
    def cancel(self):
        self._stop_flag = True
        self.status = DownloadStatus.CANCELLED
    
    def pause(self):
        self._pause_flag = True
        self.status = DownloadStatus.PAUSED
    
    def resume(self):
        self._pause_flag = False
        self.status = DownloadStatus.PENDING


class DownloadManager:
    def __init__(self, max_concurrent=3):
        self.max_concurrent = max_concurrent
        self.tasks = {}
        self.queue = Queue()
        self.active_downloads = []
        self.lock = threading.Lock()
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
    def add_task(self, url, filename, save_path, callback=None):
        """Add a download task to the queue."""
        task = DownloadTask(url, filename, save_path)
        with self.lock:
            self.tasks[task.id] = task
        
        # Add to queue with callback
        self.queue.put((task, callback))
        return task.id
    
    def get_task(self, task_id):
        """Get task by ID."""
        with self.lock:
            return self.tasks.get(task_id)
    
    def get_all_tasks(self):
        """Get all tasks."""
        with self.lock:
            return list(self.tasks.values())
    
    def cancel_task(self, task_id):
        """Cancel a download task."""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.cancel()
    
    def pause_task(self, task_id):
        """Pause a download task."""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.DOWNLOADING:
                task.pause()
    
    def resume_task(self, task_id):
        """Resume a paused task."""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.PAUSED:
                task.resume()
                # Re-add to queue
                self.queue.put((task, None))
    
    def clear_completed(self):
        """Remove completed/failed/cancelled tasks."""
        with self.lock:
            to_remove = [
                tid for tid, task in self.tasks.items()
                if task.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)
            ]
            for tid in to_remove:
                del self.tasks[tid]
    
    def _worker(self):
        """Background worker to process download queue."""
        while self._running:
            try:
                # Wait for task with timeout
                if not self.queue.empty():
                    task, callback = self.queue.get(timeout=0.5)
                    
                    # Check if we can start a new download
                    while len(self.active_downloads) >= self.max_concurrent:
                        time.sleep(0.5)
                    
                    # Start download in separate thread
                    download_thread = threading.Thread(
                        target=self._download_file,
                        args=(task, callback),
                        daemon=True
                    )
                    with self.lock:
                        self.active_downloads.append(task.id)
                    download_thread.start()
                else:
                    time.sleep(0.5)
            except:
                time.sleep(0.5)
    
    def _download_file(self, task, callback):
        """Download a single file."""
        try:
            # Create directory if it doesn't exist
            os.makedirs(task.save_path, exist_ok=True)
            
            # Check if file already exists
            if os.path.exists(task.full_path):
                task.filename = self._get_unique_filename(task.save_path, task.filename)
                task.full_path = os.path.join(task.save_path, task.filename)
            
            task.status = DownloadStatus.DOWNLOADING
            task.started_at = datetime.now()
            
            # Create request with headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = urllib.request.Request(task.url, headers=headers)
            
            # Open connection
            with urllib.request.urlopen(req, timeout=30) as response:
                # Get file size
                task.total_size = int(response.headers.get('Content-Length', 0))
                
                # Download file in chunks
                chunk_size = 8192
                downloaded = 0
                start_time = time.time()
                
                with open(task.full_path, 'wb') as f:
                    while True:
                        # Check for pause/cancel
                        if task.should_stop():
                            break
                        
                        while task.should_pause():
                            time.sleep(0.5)
                            if task.should_stop():
                                break
                        
                        if task.should_stop():
                            break
                        
                        # Read chunk
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        
                        # Write to file
                        f.write(chunk)
                        downloaded += len(chunk)
                        task.downloaded_size = downloaded
                        
                        # Calculate progress and speed
                        if task.total_size > 0:
                            task.progress = (downloaded / task.total_size) * 100
                        else:
                            task.progress = 0
                        
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            task.speed = downloaded / elapsed
                        
                        # Call callback if provided
                        if callback:
                            callback(task)
            
            # Check if download was cancelled
            if task.should_stop():
                # Delete partial file
                if os.path.exists(task.full_path):
                    os.remove(task.full_path)
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.COMPLETED
                task.completed_at = datetime.now()
                task.progress = 100.0
                
        except Exception as e:
            task.status = DownloadStatus.FAILED
            task.error_message = str(e)
        finally:
            # Remove from active downloads
            with self.lock:
                if task.id in self.active_downloads:
                    self.active_downloads.remove(task.id)
            
            # Final callback
            if callback:
                callback(task)
    
    def _get_unique_filename(self, directory, filename):
        """Generate unique filename if file already exists."""
        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        
        while os.path.exists(os.path.join(directory, new_filename)):
            new_filename = f"{base}_{counter}{ext}"
            counter += 1
        
        return new_filename
    
    def shutdown(self):
        """Shutdown the download manager."""
        self._running = False
        # Cancel all active downloads
        with self.lock:
            for task in self.tasks.values():
                if task.status == DownloadStatus.DOWNLOADING:
                    task.cancel()


def format_size(bytes_size):
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def format_speed(bytes_per_second):
    """Format speed to human-readable format."""
    return format_size(bytes_per_second) + "/s"
