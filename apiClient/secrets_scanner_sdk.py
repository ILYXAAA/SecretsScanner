#!/usr/bin/env python3
"""
Secrets Scanner SDK - Production API Client

A comprehensive client library for interacting with the Secrets Scanner API.
Designed for use by development teams to integrate secret scanning into their workflows.

Usage:
    from secrets_scanner_sdk import SecretsScanner, ScanResult
    
    scanner = SecretsScanner()
    result = scanner.quick_scan("https://github.com/user/repo", "abc123")
    print(f"Found {len(result.secrets)} secrets")

Configuration via .env file:
    SECRETS_SCANNER_URL=http://localhost:8000/secret_scanner
    SECRETS_SCANNER_TOKEN=ss_live_your_token_here
    SECRETS_SCANNER_TIMEOUT=600
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import requests
from urllib.parse import urljoin

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Secret:
    """Represents a detected secret"""
    path: str
    line: int
    
    def __str__(self):
        return f"{self.path}:{self.line}"
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ScanResult:
    """Represents scan results with metadata"""
    scan_id: str
    status: str
    secrets: List[Secret]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    repository: Optional[str] = None
    commit: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        return self.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        return self.status == "failed"
    
    @property
    def secret_count(self) -> int:
        return len(self.secrets)
    
    def save_to_file(self, filepath: Union[str, Path]) -> None:
        """Save results to JSON file"""
        filepath = Path(filepath)
        
        data = {
            "scan_id": self.scan_id,
            "status": self.status,
            "repository": self.repository,
            "commit": self.commit,
            "started_at": self.started_at,
            "completed_at": self.completed_at or datetime.now().isoformat(),
            "secret_count": self.secret_count,
            "secrets": [secret.to_dict() for secret in self.secrets]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filepath}")
    
    def __str__(self):
        return f"ScanResult(scan_id={self.scan_id}, status={self.status}, secrets={self.secret_count})"


class SecretscannerError(Exception):
    """Base exception for Secrets Scanner API errors"""
    pass


class AuthenticationError(SecretscannerError):
    """Authentication failed - invalid or missing API token"""
    pass


class PermissionError(SecretscannerError):
    """Insufficient permissions for the requested operation"""
    pass


class RateLimitError(SecretscannerError):
    """API rate limit exceeded"""
    pass


class ValidationError(SecretscannerError):
    """Request validation failed"""
    pass


class ServiceUnavailableError(SecretscannerError):
    """Service is temporarily unavailable"""
    pass


class SecretsScanner:
    """
    Main client for interacting with the Secrets Scanner API
    
    Configuration is loaded from environment variables:
    - SECRETS_SCANNER_URL: Base URL of the service
    - SECRETS_SCANNER_TOKEN: API authentication token  
    - SECRETS_SCANNER_TIMEOUT: Timeout for scan completion (default: 600s)
    """
    
    def __init__(self, 
                 base_url: Optional[str] = None,
                 api_token: Optional[str] = None,
                 timeout: Optional[int] = None):
        """
        Initialize the Secrets Scanner client
        
        Args:
            base_url: Service base URL (overrides env var)
            api_token: API token (overrides env var)
            timeout: Scan timeout in seconds (overrides env var)
        """
        self.base_url = base_url or os.getenv('SECRETS_SCANNER_URL')
        self.api_token = api_token or os.getenv('SECRETS_SCANNER_TOKEN')
        self.timeout = timeout or int(os.getenv('SECRETS_SCANNER_TIMEOUT', '600'))
        
        if not self.base_url:
            raise ValueError("SECRETS_SCANNER_URL must be set in environment or passed as parameter")
        
        if not self.api_token:
            raise ValueError("SECRETS_SCANNER_TOKEN must be set in environment or passed as parameter")
        
        self.base_url = self.base_url.rstrip('/')
        self.api_url = urljoin(self.base_url + '/', 'api/v1/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'SecretsScanner-SDK/1.0'
        })
        
        logger.info(f"Initialized Secrets Scanner client for {self.base_url}")
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> requests.Response:
        """Make HTTP request with error handling"""
        url = urljoin(self.api_url, endpoint)
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Handle common HTTP errors
            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired API token")
            elif response.status_code == 403:
                try:
                    error_data = response.json()
                    message = error_data.get('message', 'Insufficient permissions')
                except:
                    message = 'Insufficient permissions'
                raise PermissionError(message)
            elif response.status_code == 429:
                try:
                    error_data = response.json()
                    message = error_data.get('message', 'Rate limit exceeded')
                except:
                    message = 'Rate limit exceeded'
                raise RateLimitError(message)
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    message = error_data.get('message', 'Request validation failed')
                except:
                    message = 'Request validation failed'
                raise ValidationError(message)
            elif response.status_code == 503:
                raise ServiceUnavailableError("Service temporarily unavailable")
            elif response.status_code >= 500:
                raise SecretscannerError(f"Server error: HTTP {response.status_code}")
            
            return response
            
        except requests.exceptions.Timeout:
            raise SecretscannerError("Request timeout")
        except requests.exceptions.ConnectionError:
            raise SecretscannerError("Connection error - check service URL")
        except requests.exceptions.RequestException as e:
            raise SecretscannerError(f"Request failed: {e}")
    
    def check_project(self, repository: str) -> Dict[str, Any]:
        """
        Check if a project exists
        
        Args:
            repository: Repository URL to check
            
        Returns:
            Dict with 'exists' and 'project_name' keys
            
        Raises:
            SecretscannerError: If request fails
        """
        data = {"repository": repository}
        response = self._make_request('POST', 'project/check', data)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def add_project(self, repository: str) -> bool:
        """
        Add a new project
        
        Args:
            repository: Repository URL to add
            
        Returns:
            True if project was created successfully
            
        Raises:
            SecretscannerError: If project creation fails
        """
        data = {"repository": repository}
        response = self._make_request('POST', 'project/add', data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                logger.info(f"Project created: {result.get('message')}")
                return True
            else:
                raise SecretscannerError(result.get('message', 'Unknown error'))
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def start_scan(self, repository: str, commit: str) -> str:
        """
        Start a single repository scan
        
        Args:
            repository: Repository URL to scan
            commit: Commit hash to scan
            
        Returns:
            Scan ID for tracking
            
        Raises:
            SecretscannerError: If scan cannot be started
        """
        data = {"repository": repository, "commit": commit}
        response = self._make_request('POST', 'scan', data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                scan_id = result.get('scan_id')
                logger.info(f"Scan started: {scan_id}")
                return scan_id
            else:
                raise SecretscannerError(result.get('message', 'Unknown error'))
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def start_multi_scan(self, scans: List[Dict[str, str]]) -> str:
        """
        Start multiple repository scans
        
        Args:
            scans: List of dicts with 'repository' and 'commit' keys
            
        Returns:
            Multi-scan ID for tracking
            
        Raises:
            SecretscannerError: If multi-scan cannot be started
        """
        response = self._make_request('POST', 'multi_scan', scans)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                scan_id = result.get('scan_id')
                logger.info(f"Multi-scan started: {scan_id} ({len(scans)} repositories)")
                return scan_id
            else:
                raise SecretscannerError(result.get('message', 'Unknown error'))
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def get_scan_status(self, scan_id: str) -> Dict[str, Any]:
        """
        Get current scan status
        
        Args:
            scan_id: Scan ID to check
            
        Returns:
            Dict with status information
            
        Raises:
            SecretscannerError: If status cannot be retrieved
        """
        response = self._make_request('GET', f'scan/{scan_id}/status')
        
        if response.status_code == 200:
            return response.json()
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def get_scan_results(self, scan_id: str) -> ScanResult:
        """
        Get scan results
        
        Args:
            scan_id: Scan ID to get results for
            
        Returns:
            ScanResult object with secrets and metadata
            
        Raises:
            SecretscannerError: If results cannot be retrieved
        """
        response = self._make_request('GET', f'scan/{scan_id}/results')
        
        if response.status_code == 200:
            result = response.json()
            
            secrets = []
            if result.get('status') == 'completed' and result.get('results'):
                secrets = [Secret(path=s['path'], line=s['line']) for s in result['results']]
            
            return ScanResult(
                scan_id=scan_id,
                status=result.get('status', 'unknown'),
                secrets=secrets
            )
        else:
            raise SecretscannerError(f"Unexpected response: {response.status_code}")
    
    def wait_for_completion(self, scan_id: str, timeout: Optional[int] = None) -> ScanResult:
        """
        Wait for scan to complete and return results
        
        Args:
            scan_id: Scan ID to wait for
            timeout: Maximum time to wait in seconds (uses instance default if None)
            
        Returns:
            ScanResult when scan completes
            
        Raises:
            SecretscannerError: If scan fails or times out
        """
        timeout = timeout or self.timeout
        start_time = time.time()
        
        logger.info(f"Waiting for scan {scan_id} to complete (timeout: {timeout}s)")
        
        while time.time() - start_time < timeout:
            try:
                status_info = self.get_scan_status(scan_id)
                status = status_info.get('status', 'unknown')
                
                if status == 'completed':
                    logger.info(f"Scan {scan_id} completed successfully")
                    return self.get_scan_results(scan_id)
                elif status == 'failed':
                    message = status_info.get('message', 'Scan failed')
                    raise SecretscannerError(f"Scan failed: {message}")
                elif status == 'not_found':
                    raise SecretscannerError("Scan not found")
                else:
                    # Still running, wait and check again
                    logger.debug(f"Scan {scan_id} status: {status}")
                    time.sleep(10)
                    
            except SecretscannerError:
                raise
            except Exception as e:
                logger.warning(f"Error checking scan status: {e}")
                time.sleep(10)
        
        raise SecretscannerError(f"Scan timeout after {timeout} seconds")
    
    def quick_scan(self, repository: str, commit: str, 
                   save_results: Optional[Union[str, Path]] = None) -> ScanResult:
        """
        Convenience method: add project (if needed), scan, wait for completion
        
        Args:
            repository: Repository URL to scan
            commit: Commit hash to scan
            save_results: Optional file path to save results as JSON
            
        Returns:
            ScanResult with complete results
            
        Raises:
            SecretscannerError: If any step fails
        """
        logger.info(f"Starting quick scan: {repository} @ {commit}")
        
        # Check if project exists, create if needed
        try:
            project_info = self.check_project(repository)
            if not project_info.get('exists'):
                logger.info("Project not found, creating...")
                self.add_project(repository)
            else:
                logger.info(f"Using existing project: {project_info.get('project_name')}")
        except PermissionError:
            logger.warning("No permission to create projects, assuming project exists")
        
        # Start scan
        scan_id = self.start_scan(repository, commit)
        
        # Wait for completion
        result = self.wait_for_completion(scan_id)
        result.repository = repository
        result.commit = commit
        result.completed_at = datetime.now().isoformat()
        
        # Save results if requested
        if save_results:
            result.save_to_file(save_results)
        
        logger.info(f"Quick scan completed: {result.secret_count} secrets found")
        return result
    
    def batch_scan(self, repositories: List[Dict[str, str]], 
                   save_results: Optional[Union[str, Path]] = None) -> List[ScanResult]:
        """
        Scan multiple repositories and return all results
        
        Args:
            repositories: List of dicts with 'repository' and 'commit' keys
            save_results: Optional directory path to save individual result files
            
        Returns:
            List of ScanResult objects
            
        Raises:
            SecretscannerError: If batch scan fails
        """
        if len(repositories) > 10:
            raise ValidationError("Maximum 10 repositories per batch scan")
        
        logger.info(f"Starting batch scan of {len(repositories)} repositories")
        
        # Start multi-scan
        multi_scan_id = self.start_multi_scan(repositories)
        
        # Wait for completion - multi-scans may take longer
        extended_timeout = self.timeout * len(repositories)
        result = self.wait_for_completion(multi_scan_id, extended_timeout)
        
        # For multi-scans, we get a single result - in practice you might want to
        # implement separate tracking for individual scans within the multi-scan
        results = [result]
        
        # Save results if requested
        if save_results:
            save_dir = Path(save_results)
            save_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"batch_scan_{timestamp}.json"
            result.save_to_file(save_dir / filename)
        
        logger.info(f"Batch scan completed: {len(results)} scans processed")
        return results


def main():
    """Example usage and testing"""
    try:
        # Initialize client
        scanner = SecretsScanner()
        
        # Example 1: Quick scan
        print("Example 1: Quick scan")
        result = scanner.quick_scan(
            repository="https://github.com/user/repo", 
            commit="abc123",
            save_results="scan_results.json"
        )
        print(f"Found {result.secret_count} secrets")
        
        # Example 2: Manual workflow
        print("\nExample 2: Manual workflow")
        
        # Check project
        project_info = scanner.check_project("https://github.com/user/repo")
        print(f"Project exists: {project_info['exists']}")
        
        # Start scan
        scan_id = scanner.start_scan("https://github.com/user/repo", "def456")
        
        # Monitor progress
        while True:
            status = scanner.get_scan_status(scan_id)
            print(f"Status: {status['status']}")
            
            if status['status'] in ['completed', 'failed']:
                break
                
            time.sleep(5)
        
        # Get results
        if status['status'] == 'completed':
            result = scanner.get_scan_results(scan_id)
            print(f"Scan completed: {result.secret_count} secrets")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()