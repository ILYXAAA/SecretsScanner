#!/usr/bin/env python3
"""
SecretsScanner API Client

A Python client for interacting with the SecretsScanner API service.

Usage example:
    from SecretScannerClient import SecretsScanner
    
    API_KEY = "ss_live_..."
    SCANNER_URL = "http://127.0.0.1:8000/secret_Scanner"
    TIMEOUT = 60
    
    scanner = SecretsScanner(api_token=API_KEY, base_url=SCANNER_URL, scans_timeout=TIMEOUT)
    
    # Check if project exists
    project_info = scanner.check_project("https://github.com/user/repo")
    
    # Add project
    success = scanner.add_project("https://github.com/user/repo")
    
    # Quick scan with automatic waiting and report saving
    result = scanner.quick_scan(
        "https://github.com/user/repo", 
        "abc123def456",
        save_report=True,
        report_filename="my_scan.json"
    )
"""

import json
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
try:
    import urllib.request
    import urllib.parse
    import urllib.error
except ImportError:
    raise ImportError("This module requires Python's built-in urllib")


class ScanResult:
    """Container for scan results"""
    
    def __init__(self, scan_id: str, status: str, results: Optional[List[Dict]] = None):
        self.scan_id = scan_id
        self.status = status
        self.results = results or []
        self.secret_count = len(self.results) if self.results else 0


class SecretsScanner:
    """Client for SecretsScanner API"""
    
    def __init__(self, api_token: str, base_url: str = "http://127.0.0.1:8000", 
                 scans_timeout: int = 300, verbose: bool = True):
        """
        Initialize SecretsScanner client
        
        Args:
            api_token: API token for authentication (e.g. "ss_live_...")
            base_url: Base URL of the scanner service
            scans_timeout: Timeout in seconds for quick_scan operations
            verbose: Enable verbose logging with print statements
        """
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/api/v1"
        self.scans_timeout = scans_timeout
        self.verbose = verbose
        self.last_error = None
        
        if self.verbose:
            print(f"SecretsScanner client initialized for {self.base_url}")
    
    def _log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[SecretsScanner] {message}")
    
    def _validate_repository_url(self, repository: str) -> bool:
        """Simple validation of repository URL"""
        if not repository or not isinstance(repository, str):
            return False
        
        repository = repository.strip()
        
        # Must be HTTPS URL
        if not repository.startswith(('http://', 'https://')):
            return False
        
        # Should not contain commit paths or parameters
        if '/commit/' in repository or '?' in repository:
            return False
        
        return True
    
    def _validate_commit_hash(self, commit: str) -> bool:
        """Simple validation of commit hash"""
        if not commit or not isinstance(commit, str):
            return False
        
        commit = commit.strip()
        
        # Should be 7-40 alphanumeric characters
        if not re.match(r'^[a-fA-F0-9]{7,40}$', commit):
            return False
        
        return True
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make HTTP request to the API
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (without base URL)
            data: Request data for POST requests
            
        Returns:
            Response data as dict or None if error
        """
        url = f"{self.api_base}{endpoint}"
        
        try:
            # Prepare request
            headers = {
                'X-API-TOKEN': f'Bearer {self.api_token}',
                'Content-Type': 'application/json',
                'User-Agent': 'SecretsScanner-Python-Client/1.0'
            }
            
            if method == 'GET':
                req = urllib.request.Request(url, headers=headers)
            else:  # POST
                json_data = json.dumps(data).encode('utf-8') if data else b'{}'
                req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')
            
            # Make request
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                return response_data
                
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode('utf-8'))
                self.last_error = error_data.get('message', f'HTTP {e.code}')
            except:
                self.last_error = f'HTTP {e.code}: {e.reason}'
            
            self._log(f"HTTP Error: {self.last_error}")
            return None
            
        except urllib.error.URLError as e:
            self.last_error = f"Connection error: {e.reason}"
            self._log(f"Connection Error: {self.last_error}")
            return None
            
        except json.JSONDecodeError as e:
            self.last_error = f"Invalid JSON response: {e}"
            self._log(f"JSON Error: {self.last_error}")
            return None
            
        except Exception as e:
            self.last_error = f"Unexpected error: {e}"
            self._log(f"Error: {self.last_error}")
            return None
    
    def check_project(self, repository: str) -> Optional[Dict[str, Any]]:
        """
        Check if project exists in the system
        
        Args:
            repository: Repository URL to check
            
        Returns:
            Dict with 'exists' (bool) and 'project_name' (str) keys
            or None if error occurred
        """
        if not self._validate_repository_url(repository):
            self.last_error = "Invalid repository URL format"
            self._log(f"Error: {self.last_error}")
            return None
        
        self._log(f"Checking project: {repository}")
        
        data = {"repository": repository}
        response = self._make_request('POST', '/project/check', data)
        
        if response is None:
            return None
        
        result = {
            'exists': response.get('exists', False),
            'project_name': response.get('project_name', '')
        }
        
        if result['exists']:
            self._log(f"Project found: {result['project_name']}")
        else:
            self._log("Project not found")
        
        return result
    
    def add_project(self, repository: str) -> bool:
        """
        Add new project to the system
        
        Args:
            repository: Repository URL to add
            
        Returns:
            True if project was created successfully, False otherwise
        """
        if not self._validate_repository_url(repository):
            self.last_error = "Invalid repository URL format"
            self._log(f"Error: {self.last_error}")
            return False
        
        self._log(f"Adding project: {repository}")
        
        data = {"repository": repository}
        response = self._make_request('POST', '/project/add', data)
        
        if response is None:
            return False
        
        success = response.get('success', False)
        message = response.get('message', '')
        
        if success:
            self._log(f"Project added successfully: {message}")
        else:
            self.last_error = message
            self._log(f"Failed to add project: {message}")
        
        return success
    
    def start_scan(self, repository: str, commit: str) -> Optional[str]:
        """
        Start a single repository scan
        
        Args:
            repository: Repository URL to scan
            commit: Git commit hash to scan
            
        Returns:
            Scan ID string if successful, None if error occurred
        """
        if not self._validate_repository_url(repository):
            self.last_error = "Invalid repository URL format"
            self._log(f"Error: {self.last_error}")
            return None
        
        if not self._validate_commit_hash(commit):
            self.last_error = "Invalid commit hash format"
            self._log(f"Error: {self.last_error}")
            return None
        
        self._log(f"Starting scan: {repository} @ {commit}")
        
        data = {
            "repository": repository,
            "commit": commit
        }
        
        response = self._make_request('POST', '/scan', data)
        
        if response is None:
            return None
        
        if response.get('success', False):
            scan_id = response.get('scan_id')
            self._log(f"Scan started with ID: {scan_id}")
            return scan_id
        else:
            self.last_error = response.get('message', 'Unknown error')
            self._log(f"Failed to start scan: {self.last_error}")
            return None
    
    def start_multi_scan(self, repositories: List[Dict[str, str]]) -> Optional[List[str]]:
        """
        Start scanning multiple repositories
        
        Args:
            repositories: List of dicts with 'repository' and 'commit' keys
            
        Returns:
            List of scan IDs if successful, None if error occurred
        """
        if not repositories or len(repositories) == 0:
            self.last_error = "Empty repositories list"
            self._log(f"Error: {self.last_error}")
            return None
        
        if len(repositories) > 10:
            self.last_error = "Too many repositories (max 10 allowed)"
            self._log(f"Error: {self.last_error}")
            return None
        
        # Validate all repositories and commits
        for i, repo_data in enumerate(repositories):
            if not isinstance(repo_data, dict):
                self.last_error = f"Repository {i+1}: Invalid format, expected dict"
                self._log(f"Error: {self.last_error}")
                return None
            
            repository = repo_data.get('repository', '')
            commit = repo_data.get('commit', '')
            
            if not self._validate_repository_url(repository):
                self.last_error = f"Repository {i+1}: Invalid URL format"
                self._log(f"Error: {self.last_error}")
                return None
            
            if not self._validate_commit_hash(commit):
                self.last_error = f"Repository {i+1}: Invalid commit hash format"
                self._log(f"Error: {self.last_error}")
                return None
        
        self._log(f"Starting multi-scan with {len(repositories)} repositories")
        
        response = self._make_request('POST', '/multi_scan', repositories)
        
        if response is None:
            return None
        
        if response.get('success', False):
            # Parse JSON array of scan IDs
            scan_ids_json = response.get('scan_id', '[]')
            try:
                scan_ids = json.loads(scan_ids_json)
                self._log(f"Multi-scan started with {len(scan_ids)} scan IDs")
                return scan_ids
            except json.JSONDecodeError:
                self.last_error = "Invalid scan IDs format in response"
                self._log(f"Error: {self.last_error}")
                return None
        else:
            self.last_error = response.get('message', 'Unknown error')
            self._log(f"Failed to start multi-scan: {self.last_error}")
            return None
    
    def get_scan_status(self, scan_id: str) -> Optional[str]:
        """
        Get current status of a scan
        
        Args:
            scan_id: Scan identifier
            
        Returns:
            Status string ('pending', 'running', 'completed', 'failed', 'not_found')
            or None if error occurred
        """
        if not scan_id:
            self.last_error = "Empty scan ID"
            return None
        
        response = self._make_request('GET', f'/scan/{scan_id}/status')
        
        if response is None:
            return None
        
        status = response.get('status', 'unknown')
        message = response.get('message', '')
        
        self._log(f"Scan {scan_id}: {status} - {message}")
        
        return status
    
    def get_scan_results(self, scan_id: str) -> Optional[ScanResult]:
        """
        Get results of a completed scan
        
        Args:
            scan_id: Scan identifier
            
        Returns:
            ScanResult object with scan data or None if error/not completed
        """
        if not scan_id:
            self.last_error = "Empty scan ID"
            return None
        
        response = self._make_request('GET', f'/scan/{scan_id}/results')
        
        if response is None:
            return None
        
        status = response.get('status')
        
        if status == 'completed':
            results = response.get('results', [])
            scan_result = ScanResult(scan_id, status, results)
            self._log(f"Scan {scan_id}: Retrieved {scan_result.secret_count} secrets")
            return scan_result
        else:
            self.last_error = f"Scan not completed (status: {status})"
            self._log(f"Scan {scan_id}: {self.last_error}")
            return None
    
    def quick_scan(self, repository: str, commit: str, save_report: bool = True, 
                  report_filename: Optional[str] = None) -> Optional[ScanResult]:
        """
        Perform a complete scan with automatic waiting and optional report saving
        
        Args:
            repository: Repository URL to scan
            commit: Git commit hash to scan
            save_report: Whether to save results to JSON file
            report_filename: Custom filename for report (default: {project_name}_{short_commit}.json)
            
        Returns:
            ScanResult object if successful, None if error or timeout
        """
        # Start the scan
        scan_id = self.start_scan(repository, commit)
        if not scan_id:
            return None
        
        self._log(f"Quick scan started, waiting for completion (timeout: {self.scans_timeout}s)")
        
        start_time = time.time()
        
        # Poll for completion
        while time.time() - start_time < self.scans_timeout:
            status = self.get_scan_status(scan_id)
            
            if status is None:
                return None
            
            if status == 'completed':
                # Get results
                result = self.get_scan_results(scan_id)
                if result is None:
                    return None
                
                # Save report if requested
                if save_report:
                    if not report_filename:
                        # Generate default filename
                        project_info = self.check_project(repository)
                        project_name = project_info.get('project_name', 'unknown') if project_info else 'unknown'
                        short_commit = commit[:8]
                        report_filename = f"{project_name}_{short_commit}.json"
                    
                    self._save_report(result, repository, commit, report_filename)
                
                return result
            
            elif status == 'failed':
                self.last_error = "Scan failed"
                self._log(f"Scan failed: {scan_id}")
                return None
            
            elif status == 'not_found':
                self.last_error = "Scan not found"
                self._log(f"Scan not found: {scan_id}")
                return None
            
            # Wait before next poll
            time.sleep(5)
        
        # Timeout reached
        self.last_error = f"Scan timeout after {self.scans_timeout} seconds"
        self._log(f"Timeout waiting for scan completion: {scan_id}")
        return None
    
    def _save_report(self, scan_result: ScanResult, repository: str, commit: str, filename: str):
        """Save scan results to JSON file"""
        report_data = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "repository": repository,
                "commit": commit,
                "scan_id": scan_result.scan_id
            },
            "scan_summary": {
                "status": scan_result.status,
                "secrets_found": scan_result.secret_count
            },
            "results": scan_result.results
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            self._log(f"Report saved to: {filename}")
            
        except Exception as e:
            self._log(f"Failed to save report: {e}")
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message"""
        return self.last_error