#!/usr/bin/env python3
"""
SecretsScanner API Client

A Python client for interacting with the SecretsScanner API service.
Supports Azure DevOps and Devzone repositories only.

Usage example:
    from SecretScannerClient import SecretsScanner
    
    API_KEY = "ss_live_..."
    SCANNER_URL = "http://127.0.0.1:8000/secret_scanner"
    TIMEOUT = 60
    
    scanner = SecretsScanner(api_token=API_KEY, base_url=SCANNER_URL, scans_timeout=TIMEOUT)
    
    # Check if project exists
    project_info = scanner.check_project("http://server/collection/project/_git/repo")
    
    # Add project
    success = scanner.add_project("http://server/collection/project/_git/repo")
    
    # Scan by branch (using URL with ref)
    result = scanner.quick_scan(
        "http://server/collection/project/_git/repo?version=GBmain",
        save_report=True,
        report_filename="my_scan.json"
    )
    
    # Scan by branch (using base URL with ref_type and ref)
    result = scanner.quick_scan(
        "http://server/collection/project/_git/repo",
        ref_type="Branch",
        ref="main",
        save_report=True
    )
    
    # Scan by tag
    result = scanner.quick_scan(
        "http://server/collection/project/_git/repo?version=GTv1.0.0"
    )
    
    # Scan by commit (deprecated, but still supported)
    result = scanner.quick_scan(
        "http://server/collection/project/_git/repo",
        commit="abc123def456"
    )
    
    # Export HTML report
    if result:
        scanner.export_html_report(result.scan_id, "my_report.html")
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
    
    def __init__(self, scan_id: str, status: str, results: Optional[List[Dict]] = None, commit: Optional[str] = None):
        self.scan_id = scan_id
        self.status = status
        self.results = results or []
        self.secret_count = len(self.results) if self.results else 0
        self.commit = commit  # Resolved commit hash from API (if available)


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
        self._last_scan_commit: Optional[str] = None
        self._last_multi_scan_commits: Optional[List[str]] = None
        
        if self.verbose:
            print(f"SecretsScanner client initialized for {self.base_url}")
    
    def _log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[SecretsScanner] {message}")
    
    def _validate_repository_url(self, repository: str, allow_ref: bool = False) -> bool:
        """
        Validate repository URL (Azure/Devzone only)
        
        Args:
            repository: Repository URL to validate
            allow_ref: If True, allow URLs with ref parameters/paths
            
        Returns:
            True if valid, False otherwise
        """
        if not repository or not isinstance(repository, str):
            return False
        
        repository = repository.strip()
        
        # Must be HTTP/HTTPS URL or git@ format for Devzone
        if not (repository.startswith(('http://', 'https://')) or 
                repository.startswith('git@git.devzone.local:')):
            return False
        
        # Check if it's Azure DevOps or Devzone
        is_azure = '_git' in repository
        is_devzone = 'devzone.local' in repository.lower()
        
        if not (is_azure or is_devzone):
            return False
        
        # If ref is not allowed, check for ref indicators
        if not allow_ref:
            if '/commit/' in repository or '?' in repository:
                return False
        
        return True
    
    def _parse_repository_url(self, repository: str) -> dict:
        """
        Parse repository URL to extract base URL and ref information
        
        Args:
            repository: Repository URL (may contain ref)
            
        Returns:
            Dict with 'base_repo_url', 'ref_type', and 'ref' keys
            
        Raises:
            ValueError: If URL format is invalid
        """
        try:
            # Try to import and use the API parser
            import sys
            import os
            # Add parent directory to path to import api.url_parser
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from api.url_parser import parse_repo_url_with_ref
            return parse_repo_url_with_ref(repository)
        except ImportError:
            # Fallback: simple parsing if API module not available
            # This is a simplified version - full parsing is in api.url_parser
            if not self._validate_repository_url(repository, allow_ref=True):
                raise ValueError("Invalid repository URL format. Only Azure DevOps and Devzone URLs are supported.")
            
            # For now, return base URL and default ref
            # Full parsing should use api.url_parser module
            base_url = repository.split('?')[0].split('/commit/')[0]
            if base_url.endswith('.git'):
                base_url = base_url[:-4]
            
            return {
                "base_repo_url": base_url,
                "ref_type": "Branch",
                "ref": "main"
            }
    
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
            repository: Repository URL to check (base URL, ref will be ignored)
            
        Returns:
            Dict with 'exists' (bool) and 'project_name' (str) keys
            or None if error occurred
        """
        # Extract base URL if repository contains ref
        try:
            parsed = self._parse_repository_url(repository)
            repository = parsed['base_repo_url']
        except ValueError:
            pass  # If parsing fails, use repository as-is
        
        if not self._validate_repository_url(repository, allow_ref=False):
            self.last_error = "Invalid repository URL format. Only Azure DevOps and Devzone URLs are supported."
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
            repository: Repository URL to add (base URL, ref will be ignored)
            
        Returns:
            True if project was created successfully, False otherwise
        """
        # Extract base URL if repository contains ref
        try:
            parsed = self._parse_repository_url(repository)
            repository = parsed['base_repo_url']
        except ValueError:
            pass  # If parsing fails, use repository as-is
        
        if not self._validate_repository_url(repository, allow_ref=False):
            self.last_error = "Invalid repository URL format. Only Azure DevOps and Devzone URLs are supported."
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
    
    def start_scan(self, repository: str, commit: Optional[str] = None, 
                   ref_type: Optional[str] = None, ref: Optional[str] = None) -> Optional[str]:
        """
        Start a single repository scan
        
        Args:
            repository: Repository URL to scan (can contain ref, e.g., ?version=GBbranch)
            commit: [DEPRECATED] Git commit hash to scan. Use repository URL with ref or ref_type+ref instead.
            ref_type: Reference type: 'Commit', 'Branch', or 'Tag'. Required if repository is base URL.
            ref: Reference value (commit hash, branch name, or tag name). Required if repository is base URL.
            
        Returns:
            Scan ID string if successful, None if error occurred
        """
        # Parse repository URL to extract ref if present
        try:
            parsed = self._parse_repository_url(repository)
            base_repo_url = parsed['base_repo_url']
            parsed_ref_type = parsed['ref_type']
            parsed_ref = parsed['ref']
            
            # If repository contains explicit ref (not default), use it
            if parsed_ref_type != 'Branch' or parsed_ref != 'main':
                ref_type = parsed_ref_type
                ref = parsed_ref
                repository = base_repo_url
        except ValueError as e:
            self.last_error = f"Invalid repository URL: {str(e)}"
            self._log(f"Error: {self.last_error}")
            return None
        
        # Validate base repository URL
        if not self._validate_repository_url(repository, allow_ref=False):
            self.last_error = "Invalid repository URL format. Only Azure DevOps and Devzone URLs are supported."
            self._log(f"Error: {self.last_error}")
            return None
        
        # Determine ref_type and ref
        if ref_type and ref:
            # Use provided ref_type and ref
            pass
        elif commit:
            # Backward compatibility: use commit
            ref_type = "Commit"
            ref = commit
        else:
            self.last_error = "Either provide repository URL with ref, or provide ref_type and ref, or provide commit (deprecated)"
            self._log(f"Error: {self.last_error}")
            return None
        
        # Validate ref_type
        if ref_type not in ['Commit', 'Branch', 'Tag']:
            self.last_error = "ref_type must be one of: 'Commit', 'Branch', 'Tag'"
            self._log(f"Error: {self.last_error}")
            return None
        
        # Validate commit hash if ref_type is Commit
        if ref_type == 'Commit' and not self._validate_commit_hash(ref):
            self.last_error = "Invalid commit hash format (7-40 alphanumeric characters)"
            self._log(f"Error: {self.last_error}")
            return None
        
        self._log(f"Starting scan: {repository} ({ref_type}: {ref})")
        
        data = {
            "repository": repository,
            "ref_type": ref_type,
            "ref": ref
        }
        
        # Include commit for backward compatibility if provided
        if commit:
            data["commit"] = commit
        
        response = self._make_request('POST', '/scan', data)
        
        if response is None:
            return None
        
        if response.get('success', False):
            scan_id = response.get('scan_id')
            self._last_scan_commit = response.get('commit')
            self._log(f"Scan started with ID: {scan_id}" + (f", commit: {self._last_scan_commit}" if self._last_scan_commit else ""))
            return scan_id
        else:
            self._last_scan_commit = None
            self.last_error = response.get('message', 'Unknown error')
            self._log(f"Failed to start scan: {self.last_error}")
            return None
    
    def get_last_scan_commit(self) -> Optional[str]:
        """Return resolved commit hash from last successful start_scan, or None."""
        return self._last_scan_commit
    
    def start_multi_scan(self, repositories: List[Dict[str, str]]) -> Optional[List[str]]:
        """
        Start scanning multiple repositories
        
        Args:
            repositories: List of dicts with:
                - 'repository': Repository URL (can contain ref, e.g., ?version=GBbranch)
                - 'commit': [DEPRECATED] Git commit hash. Use repository URL with ref or ref_type+ref instead.
                - 'ref_type': Reference type: 'Commit', 'Branch', or 'Tag' (optional)
                - 'ref': Reference value (optional)
            
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
        
        # Validate and normalize all repositories
        normalized_repos = []
        for i, repo_data in enumerate(repositories):
            if not isinstance(repo_data, dict):
                self.last_error = f"Repository {i+1}: Invalid format, expected dict"
                self._log(f"Error: {self.last_error}")
                return None
            
            repository = repo_data.get('repository', '')
            commit = repo_data.get('commit')
            ref_type = repo_data.get('ref_type')
            ref = repo_data.get('ref')
            
            # Parse repository URL to extract ref if present
            try:
                parsed = self._parse_repository_url(repository)
                base_repo_url = parsed['base_repo_url']
                parsed_ref_type = parsed['ref_type']
                parsed_ref = parsed['ref']
                
                # If repository contains explicit ref (not default), use it
                if parsed_ref_type != 'Branch' or parsed_ref != 'main':
                    ref_type = parsed_ref_type
                    ref = parsed_ref
                    repository = base_repo_url
            except ValueError as e:
                self.last_error = f"Repository {i+1}: Invalid URL format - {str(e)}"
                self._log(f"Error: {self.last_error}")
                return None
            
            # Validate base repository URL
            if not self._validate_repository_url(repository, allow_ref=False):
                self.last_error = f"Repository {i+1}: Invalid URL format. Only Azure DevOps and Devzone URLs are supported."
                self._log(f"Error: {self.last_error}")
                return None
            
            # Determine ref_type and ref
            if ref_type and ref:
                # Use provided ref_type and ref
                pass
            elif commit:
                # Backward compatibility: use commit
                ref_type = "Commit"
                ref = commit
            else:
                self.last_error = f"Repository {i+1}: Either provide repository URL with ref, or provide ref_type and ref, or provide commit (deprecated)"
                self._log(f"Error: {self.last_error}")
                return None
            
            # Validate ref_type
            if ref_type not in ['Commit', 'Branch', 'Tag']:
                self.last_error = f"Repository {i+1}: ref_type must be one of: 'Commit', 'Branch', 'Tag'"
                self._log(f"Error: {self.last_error}")
                return None
            
            # Validate commit hash if ref_type is Commit
            if ref_type == 'Commit' and not self._validate_commit_hash(ref):
                self.last_error = f"Repository {i+1}: Invalid commit hash format (7-40 alphanumeric characters)"
                self._log(f"Error: {self.last_error}")
                return None
            
            # Build normalized request item
            normalized_item = {
                "repository": repository,
                "ref_type": ref_type,
                "ref": ref
            }
            
            # Include commit for backward compatibility if provided
            if commit:
                normalized_item["commit"] = commit
            
            normalized_repos.append(normalized_item)
        
        self._log(f"Starting multi-scan with {len(normalized_repos)} repositories")
        
        response = self._make_request('POST', '/multi_scan', normalized_repos)
        
        if response is None:
            return None
        
        if response.get('success', False):
            # Parse JSON array of scan IDs
            scan_ids_json = response.get('scan_id', '[]')
            commits_json = response.get('commits', '[]')
            try:
                scan_ids = json.loads(scan_ids_json) if isinstance(scan_ids_json, str) else scan_ids_json
                try:
                    self._last_multi_scan_commits = json.loads(commits_json) if isinstance(commits_json, str) else (commits_json or [])
                except (TypeError, json.JSONDecodeError):
                    self._last_multi_scan_commits = []
                self._log(f"Multi-scan started with {len(scan_ids)} scan IDs")
                return scan_ids
            except json.JSONDecodeError:
                self.last_error = "Invalid scan IDs format in response"
                self._log(f"Error: {self.last_error}")
                return None
        else:
            self._last_multi_scan_commits = None
            self.last_error = response.get('message', 'Unknown error')
            self._log(f"Failed to start multi-scan: {self.last_error}")
            return None
    
    def get_last_multi_scan_commits(self) -> Optional[List[str]]:
        """Return list of resolved commit hashes from last successful start_multi_scan (same order as scan IDs), or None."""
        return self._last_multi_scan_commits
    
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
    
    def quick_scan(self, repository: str, commit: Optional[str] = None, 
                   ref_type: Optional[str] = None, ref: Optional[str] = None,
                   save_report: bool = True, 
                   report_filename: Optional[str] = None) -> Optional[ScanResult]:
        """
        Perform a complete scan with automatic waiting and optional report saving
        
        Args:
            repository: Repository URL to scan (can contain ref, e.g., ?version=GBbranch)
            commit: [DEPRECATED] Git commit hash to scan. Use repository URL with ref or ref_type+ref instead.
            ref_type: Reference type: 'Commit', 'Branch', or 'Tag'. Required if repository is base URL.
            ref: Reference value (commit hash, branch name, or tag name). Required if repository is base URL.
            save_report: Whether to save results to JSON file
            report_filename: Custom filename for report (default: {project_name}_{short_ref}.json)
            
        Returns:
            ScanResult object if successful, None if error or timeout
        """
        # Start the scan
        scan_id = self.start_scan(repository, commit, ref_type, ref)
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
                result.commit = result.commit or self.get_last_scan_commit()
                
                # Save report if requested
                if save_report:
                    if not report_filename:
                        # Generate default filename
                        project_info = self.check_project(repository)
                        project_name = project_info.get('project_name', 'unknown') if project_info else 'unknown'
                        short_ref = (result.commit or ref or commit or 'unknown')[:8]
                        report_filename = f"{project_name}_{short_ref}.json"
                    
                    ref_value = result.commit or ref or commit
                    self._save_report(result, repository, ref_value, report_filename)
                
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
    
    def _save_report(self, scan_result: ScanResult, repository: str, ref: str, filename: str):
        """Save scan results to JSON file"""
        report_data = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "repository": repository,
                "ref": ref,
                "commit": getattr(scan_result, 'commit', None),
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
    
    def export_html_report(self, scan_id: str, filename: Optional[str] = None) -> bool:
        """
        Export scan results as HTML report
        
        Args:
            scan_id: Scan identifier
            filename: Optional filename to save the report (default: {project_name}_{ref}.html)
            
        Returns:
            True if report was saved successfully, False otherwise
        """
        if not scan_id:
            self.last_error = "Empty scan ID"
            self._log(f"Error: {self.last_error}")
            return False
        
        self._log(f"Exporting HTML report for scan: {scan_id}")
        
        url = f"{self.api_base}/scan/{scan_id}/export-html"
        
        try:
            headers = {
                'X-API-TOKEN': f'Bearer {self.api_token}',
                'User-Agent': 'SecretsScanner-Python-Client/1.0'
            }
            
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status != 200:
                    try:
                        error_data = json.loads(response.read().decode('utf-8'))
                        self.last_error = error_data.get('message', f'HTTP {response.status}')
                    except:
                        self.last_error = f'HTTP {response.status}: {response.reason}'
                    self._log(f"HTTP Error: {self.last_error}")
                    return False
                
                # Get filename from Content-Disposition header if not provided
                if not filename:
                    content_disposition = response.headers.get('Content-Disposition', '')
                    if 'filename=' in content_disposition:
                        filename = content_disposition.split('filename=')[1].strip('"\'')
                    else:
                        filename = f"scan_{scan_id}.html"
                
                # Save HTML content
                html_content = response.read().decode('utf-8')
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                self._log(f"HTML report saved to: {filename}")
                return True
                
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode('utf-8'))
                self.last_error = error_data.get('message', f'HTTP {e.code}')
            except:
                self.last_error = f'HTTP {e.code}: {e.reason}'
            
            self._log(f"HTTP Error: {self.last_error}")
            return False
            
        except urllib.error.URLError as e:
            self.last_error = f"Connection error: {e.reason}"
            self._log(f"Connection Error: {self.last_error}")
            return False
            
        except Exception as e:
            self.last_error = f"Unexpected error: {e}"
            self._log(f"Error: {self.last_error}")
            return False
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message"""
        return self.last_error