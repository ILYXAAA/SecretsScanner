# Secrets Scanner SDK

A comprehensive Python SDK for integrating with the Secrets Scanner API. This SDK provides a simple interface for scanning repositories, managing projects, and retrieving scan results.

## Installation

1. Copy the SDK files to your project:
   ```bash
   # Copy these files to your project directory
   secrets_scanner_sdk.py
   examples.py
   .env.example
   ```

2. Install required dependencies:
   ```bash
   pip install requests python-dotenv
   ```

3. Configure your environment:
   ```bash
   cp .env.example .env
   # Edit .env with your actual configuration
   ```

## Configuration

Create a `.env` file in your project directory with the following variables:

```bash
# Base URL of the Secrets Scanner service
SECRETS_SCANNER_URL=http://localhost:8000/secret_scanner

# Your API token (obtain from admin panel)
SECRETS_SCANNER_TOKEN=ss_live_your_token_here

# Timeout for scan completion in seconds (optional, default: 600)
SECRETS_SCANNER_TIMEOUT=600
```

## Quick Start

### Basic Usage

```python
from secrets_scanner_sdk import SecretsScanner

# Initialize the client (uses environment variables)
scanner = SecretsScanner()

# Quick scan: add project + scan + wait for results
result = scanner.quick_scan(
    repository="https://github.com/user/repo",
    commit="abc123def456",
    save_results="scan_results.json"  # optional
)

print(f"Found {result.secret_count} secrets")
for secret in result.secrets:
    print(f"  - {secret}")  # prints "path:line"
```

### Manual Workflow

```python
from secrets_scanner_sdk import SecretsScanner

scanner = SecretsScanner()

# Check if project exists
project_info = scanner.check_project("https://github.com/user/repo")
if not project_info['exists']:
    # Add project if it doesn't exist
    scanner.add_project("https://github.com/user/repo")

# Start scan
scan_id = scanner.start_scan("https://github.com/user/repo", "abc123")

# Wait for completion
result = scanner.wait_for_completion(scan_id)

# Save results
result.save_to_file("results.json")
```

## API Reference

### SecretsScanner Class

#### Constructor
```python
SecretsScanner(base_url=None, api_token=None, timeout=None)
```
- `base_url`: Service URL (overrides env var)
- `api_token`: API token (overrides env var)  
- `timeout`: Scan timeout in seconds (overrides env var)

#### Methods

##### Project Management
```python
# Check if project exists
project_info = scanner.check_project(repository_url)
# Returns: {"exists": bool, "project_name": str}

# Add new project
success = scanner.add_project(repository_url)
# Returns: True if successful
```

##### Scanning
```python
# Start single scan
scan_id = scanner.start_scan(repository_url, commit_hash)
# Returns: scan ID string

# Start multi-scan (max 10 repositories)
scans = [
    {"repository": "https://github.com/user/repo1", "commit": "abc123"},
    {"repository": "https://github.com/user/repo2", "commit": "def456"}
]
multi_scan_id = scanner.start_multi_scan(scans)
# Returns: multi-scan ID string
```

##### Results
```python
# Get scan status
status = scanner.get_scan_status(scan_id)
# Returns: {"scan_id": str, "status": str, "message": str}

# Get scan results
result = scanner.get_scan_results(scan_id)
# Returns: ScanResult object

# Wait for scan completion
result = scanner.wait_for_completion(scan_id, timeout=600)
# Returns: ScanResult object when complete
```

##### Convenience Methods
```python
# All-in-one: create project + scan + wait + return results
result = scanner.quick_scan(repository_url, commit_hash, save_results=None)

# Batch process multiple repositories
repositories = [{"repository": "...", "commit": "..."}, ...]
results = scanner.batch_scan(repositories, save_results=None)
```

### ScanResult Class

Represents scan results with metadata:

```python
@dataclass
class ScanResult:
    scan_id: str
    status: str
    secrets: List[Secret]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    repository: Optional[str] = None
    commit: Optional[str] = None
```

#### Properties
- `is_completed`: Returns True if scan completed successfully
- `is_failed`: Returns True if scan failed
- `secret_count`: Number of secrets found

#### Methods
```python
# Save results to JSON file
result.save_to_file("results.json")
```

### Secret Class

Represents a detected secret:

```python
@dataclass  
class Secret:
    path: str  # File path
    line: int  # Line number
```

## Error Handling

The SDK defines specific exceptions for different error conditions:

```python
from secrets_scanner_sdk import (
    AuthenticationError,    # Invalid/expired token
    PermissionError,       # Insufficient permissions
    RateLimitError,        # Rate limit exceeded
    ValidationError,       # Invalid request data
    ServiceUnavailableError,  # Service down
    SecretscannerError     # Generic API error
)

try:
    result = scanner.quick_scan(repo, commit)
except AuthenticationError:
    print("Check your API token")
except PermissionError:
    print("Insufficient permissions")
except RateLimitError:
    print("Rate limit exceeded - wait and retry")
except ValidationError:
    print("Invalid repository URL or commit")
except SecretscannerError as e:
    print(f"Scan failed: {e}")
```

## Integration Examples

### CI/CD Pipeline

```python
# ci_scan.py
import sys
import os
from secrets_scanner_sdk import SecretsScanner, SecretscannerError

def main():
    try:
        scanner = SecretsScanner()
        
        # Get values from CI environment
        repo = os.getenv('CI_REPOSITORY_URL')
        commit = os.getenv('CI_COMMIT_SHA')
        
        result = scanner.quick_scan(repo, commit, save_results="scan-results.json")
        
        if result.secret_count > 0:
            print(f"FAILURE: {result.secret_count} secrets detected!")
            sys.exit(1)
        else:
            print("SUCCESS: No secrets detected")
            sys.exit(0)
            
    except SecretscannerError as e:
        print(f"SCAN ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Pre-commit Hook

```python
# pre_commit_scan.py
from secrets_scanner_sdk import SecretsScanner
import subprocess

def get_current_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()

def get_repo_url():
    return subprocess.check_output(['git', 'remote', 'get-url', 'origin']).decode().strip()

def main():
    scanner = SecretsScanner()
    
    repo = get_repo_url()
    commit = get_current_commit()
    
    print(f"Scanning {repo} @ {commit[:8]}...")
    
    result = scanner.quick_scan(repo, commit)
    
    if result.secret_count > 0:
        print(f"⚠️  {result.secret_count} potential secrets found:")
        for secret in result.secrets[:5]:  # Show first 5
            print(f"  - {secret}")
        print("\nReview before committing!")
    else:
        print("✅ No secrets detected")

if __name__ == "__main__":
    main()
```

### Scheduled Security Monitoring

```python
# security_monitor.py
from secrets_scanner_sdk import SecretsScanner
from datetime import datetime
import json

def monitor_repositories():
    scanner = SecretsScanner()
    
    # Repositories to monitor
    repos = [
        {"name": "frontend", "url": "https://github.com/company/frontend"},
        {"name": "backend", "url": "https://github.com/company/backend"},
        {"name": "mobile", "url": "https://github.com/company/mobile"}
    ]
    
    alerts = []
    
    for repo in repos:
        try:
            # Scan main branch
            result = scanner.quick_scan(repo["url"], "main")
            
            if result.secret_count > 0:
                alerts.append({
                    "repository": repo["name"],
                    "url": repo["url"], 
                    "secrets_count": result.secret_count,
                    "timestamp": datetime.now().isoformat()
                })
                
                print(f"🚨 {repo['name']}: {result.secret_count} secrets")
            else:
                print(f"✅ {repo['name']}: clean")
                
        except Exception as e:
            print(f"❌ {repo['name']}: {e}")
    
    # Save security report
    report = {
        "scan_date": datetime.now().isoformat(),
        "repositories_scanned": len(repos),
        "alerts": alerts
    }
    
    with open("security_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    # Send alerts if any (implement your notification method)
    if alerts:
        send_security_alert(alerts)

def send_security_alert(alerts):
    # Implement your notification method:
    # - Email
    # - Slack webhook
    # - Jira ticket creation
    # - etc.
    pass

if __name__ == "__main__":
    monitor_repositories()
```

## Best Practices

### 1. Environment Configuration
- Always use environment variables for sensitive configuration
- Keep `.env` file out of version control
- Use different tokens for different environments (dev/staging/prod)

### 2. Error Handling
- Implement comprehensive error handling for production use
- Log errors with appropriate detail level
- Provide actionable error messages to users

### 3. Rate Limiting
- Respect API rate limits
- Implement exponential backoff for retries
- Consider batching operations when possible

### 4. Result Storage
- Save scan results for audit trails
- Use structured formats (JSON) for easy processing
- Include metadata (timestamp, repository, commit) in results

### 5. Security
- Rotate API tokens regularly
- Use tokens with minimal required permissions
- Monitor token usage and detect anomalies

### 6. Performance
- Use `quick_scan()` for simple workflows
- Use manual workflow for complex integrations
- Cache project existence checks when scanning multiple commits

## Troubleshooting

### Authentication Issues
- Verify token is correct and active
- Check token hasn't expired
- Ensure token has required permissions for the operation

### Connection Issues
- Verify service URL is correct and accessible
- Check network connectivity
- Confirm service is running and healthy

### Scan Issues
- Verify repository URL format
- Ensure commit hash exists and is accessible
- Check if project needs to be created first

### Performance Issues
- Increase timeout for large repositories
- Use batch operations for multiple scans
- Monitor rate limits and adjust request frequency

## Support

For issues with the SDK:
1. Check this documentation
2. Review error messages and logs
3. Verify configuration and permissions
4. Contact your system administrator

For service-specific issues:
1. Check service health and status
2. Review API token permissions in admin panel
3. Contact service administrators