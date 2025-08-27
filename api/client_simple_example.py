#!/usr/bin/env python3
"""
Simple console client for Secrets Scanner API
Usage: python secrets_scanner_client.py
"""

import requests
import json
import time
import sys
from urllib.parse import urljoin

class SecretscannerClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url.rstrip('/')
        self.api_url = urljoin(self.base_url + '/', 'api/v1/')
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method, endpoint, data=None):
        """Make HTTP request to API"""
        url = urljoin(self.api_url, endpoint)
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None
    
    def add_project(self, repository_url):
        """Add new project"""
        data = {"repository": repository_url}
        response = self._make_request('POST', 'project/add', data)
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def check_project(self, repository_url=None, project_name=None):
        """Check if project exists"""
        data = {}
        if repository_url:
            data["repository"] = repository_url
        if project_name:
            data["project_name"] = project_name
        
        if not data:
            return {"success": False, "message": "Repository URL or project name required"}
        
        response = self._make_request('POST', 'project/check', data)
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def start_scan(self, repository_url, commit):
        """Start single scan"""
        data = {
            "repository": repository_url,
            "commit": commit
        }
        response = self._make_request('POST', 'scan', data)
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def start_multi_scan(self, scans):
        """Start multiple scans"""
        # scans should be list of {"repository": "url", "commit": "hash"}
        response = self._make_request('POST', 'multi_scan', scans)
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def get_scan_status(self, scan_id):
        """Get scan status"""
        response = self._make_request('GET', f'scan/{scan_id}/status')
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def get_scan_results(self, scan_id):
        """Get scan results"""
        response = self._make_request('GET', f'scan/{scan_id}/results')
        
        if response is None:
            return {"success": False, "message": "Connection error"}
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                error_data = response.json()
                return {"success": False, "message": error_data.get("message", f"HTTP {response.status_code}")}
            except:
                return {"success": False, "message": f"HTTP {response.status_code}"}
    
    def wait_for_scan_completion(self, scan_id, timeout=600):
        """Wait for scan to complete with timeout"""
        print(f"Waiting for scan {scan_id} to complete...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status_result = self.get_scan_status(scan_id)
            
            if not status_result:
                print("Error getting scan status")
                return False
            
            status = status_result.get("status", "unknown")
            print(f"Status: {status} - {status_result.get('message', '')}")
            
            if status == "completed":
                return True
            elif status == "failed":
                print("Scan failed")
                return False
            elif status == "not_found":
                print("Scan not found")
                return False
            
            time.sleep(10)  # Wait 10 seconds before next check
        
        print("Timeout waiting for scan completion")
        return False

def main():
    print("=== Secrets Scanner API Client ===")
    
    # Configuration
    BASE_URL = input("Enter base URL (e.g., http://localhost:8000/secret_scanner): ").strip()
    if not BASE_URL:
        BASE_URL = "http://localhost:8000/secret_scanner"
    
    API_TOKEN = input("Enter API token: ").strip()
    if not API_TOKEN:
        print("API token is required")
        sys.exit(1)
    
    client = SecretscannerClient(BASE_URL, API_TOKEN)
    
    while True:
        print("\n=== Available Actions ===")
        print("1. Check project")
        print("2. Add project")
        print("3. Start single scan")
        print("4. Start multi-scan")
        print("5. Get scan status")
        print("6. Get scan results")
        print("7. Quick scan (add project + scan + wait + results)")
        print("0. Exit")
        
        choice = input("\nSelect action (0-7): ").strip()
        
        if choice == "0":
            print("Goodbye!")
            break
        
        elif choice == "1":
            # Check project
            repo_url = input("Repository URL: ").strip()
            if repo_url:
                result = client.check_project(repository_url=repo_url)
                if result.get("exists"):
                    print(f"Project exists: {result.get('project_name')}")
                else:
                    print("Project not found")
        
        elif choice == "2":
            # Add project
            repo_url = input("Repository URL: ").strip()
            if repo_url:
                result = client.add_project(repo_url)
                if result.get("success"):
                    print(f"Success: {result.get('message')}")
                else:
                    print(f"Error: {result.get('message')}")
        
        elif choice == "3":
            # Single scan
            repo_url = input("Repository URL: ").strip()
            commit = input("Commit hash: ").strip()
            if repo_url and commit:
                result = client.start_scan(repo_url, commit)
                if result.get("success"):
                    print(f"Scan started: {result.get('scan_id')}")
                    print(f"Message: {result.get('message')}")
                else:
                    print(f"Error: {result.get('message')}")
        
        elif choice == "4":
            # Multi-scan
            scans = []
            print("Enter scans (empty repository URL to finish):")
            while True:
                repo_url = input(f"Repository URL #{len(scans)+1}: ").strip()
                if not repo_url:
                    break
                commit = input(f"Commit hash #{len(scans)+1}: ").strip()
                if commit:
                    scans.append({"repository": repo_url, "commit": commit})
            
            if scans:
                result = client.start_multi_scan(scans)
                if result.get("success"):
                    print(f"Multi-scan started: {result.get('scan_id')}")
                    print(f"Message: {result.get('message')}")
                else:
                    print(f"Error: {result.get('message')}")
        
        elif choice == "5":
            # Scan status
            scan_id = input("Scan ID: ").strip()
            if scan_id:
                result = client.get_scan_status(scan_id)
                print(f"Status: {result.get('status')}")
                print(f"Message: {result.get('message')}")
        
        elif choice == "6":
            # Scan results
            scan_id = input("Scan ID: ").strip()
            if scan_id:
                result = client.get_scan_results(scan_id)
                if result.get("status") == "completed":
                    results = result.get("results", [])
                    print(f"Found {len(results)} secrets:")
                    for i, secret in enumerate(results[:10], 1):  # Show first 10
                        print(f"  {i}. {secret.get('path')}:{secret.get('line')}")
                    if len(results) > 10:
                        print(f"  ... and {len(results) - 10} more")
                else:
                    print(f"Status: {result.get('status')}")
        
        elif choice == "7":
            # Quick scan workflow
            repo_url = input("Repository URL: ").strip()
            commit = input("Commit hash: ").strip()
            
            if not repo_url or not commit:
                print("Both repository URL and commit are required")
                continue
            
            print("Step 1: Checking if project exists...")
            check_result = client.check_project(repository_url=repo_url)
            
            if not check_result.get("exists"):
                print("Step 2: Adding project...")
                add_result = client.add_project(repo_url)
                if not add_result.get("success"):
                    print(f"Failed to add project: {add_result.get('message')}")
                    continue
                print(f"Project added: {add_result.get('message')}")
            else:
                print(f"Project already exists: {check_result.get('project_name')}")
            
            print("Step 3: Starting scan...")
            scan_result = client.start_scan(repo_url, commit)
            if not scan_result.get("success"):
                print(f"Failed to start scan: {scan_result.get('message')}")
                continue
            
            scan_id = scan_result.get("scan_id")
            print(f"Scan started: {scan_id}")
            
            print("Step 4: Waiting for completion...")
            if client.wait_for_scan_completion(scan_id):
                print("Step 5: Getting results...")
                results = client.get_scan_results(scan_id)
                if results.get("status") == "completed":
                    secrets = results.get("results", [])
                    print(f"\nScan completed! Found {len(secrets)} secrets:")
                    for i, secret in enumerate(secrets[:20], 1):  # Show first 20
                        print(f"  {i}. {secret.get('path')}:{secret.get('line')}")
                    if len(secrets) > 20:
                        print(f"  ... and {len(secrets) - 20} more")
                else:
                    print(f"Results status: {results.get('status')}")
            else:
                print("Scan did not complete successfully")
        
        else:
            print("Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)