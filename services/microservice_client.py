import httpx
import logging
from config import MICROSERVICE_URL, get_auth_headers

logger = logging.getLogger("main")

async def check_microservice_health():
    """Check if microservice is available"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/health", timeout=5.0, headers=get_auth_headers())
            return response.status_code == 200
    except:
        return False

async def get_pat_token():
    """Get current PAT token from microservice"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-pat", headers=get_auth_headers(), timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return data.get("token", "Not set")
    except:
        return "Error: microservice unavailable"
    return "Not set"

async def set_pat_token(token: str):
    """Set PAT token in microservice"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{MICROSERVICE_URL}/set-pat", 
                                       json={"token": token}, headers=get_auth_headers(), timeout=10.0)
            return response.status_code == 200
    except:
        return False

async def get_rules_info():
    """Get rules file information"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/rules-info", headers=get_auth_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching rules info: {e}")
    return {"error": "microservice_unavailable"}

async def get_rules_content():
    """Get rules file content"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-rules", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                rules_data = response.json()
                if rules_data.get("status") == "success":
                    return rules_data.get("rules", "")
    except Exception as e:
        logger.error(f"Error fetching rules content: {e}")
    return ""

async def update_rules(content: str):
    """Update rules file content"""
    payload = {"content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MICROSERVICE_URL}/update-rules", headers=get_auth_headers(),
            json=payload
        )
        return response

async def get_fp_rules_info():
    """Get FP rules file information"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/rules-fp-info", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching FP rules info: {e}")
    return {"error": "microservice_unavailable"}

async def get_fp_rules_content():
    """Get FP rules file content"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-fp-rules", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                fp_rules_data = response.json()
                if fp_rules_data.get("status") == "success":
                    return fp_rules_data.get("fp_rules", "")
    except Exception as e:
        logger.error(f"Error fetching FP rules content: {e}")
    return ""

async def update_fp_rules(content: str):
    """Update FP rules file content"""
    payload = {"content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MICROSERVICE_URL}/update-fp-rules",
            json=payload, headers=get_auth_headers()
        )
        return response

async def get_excluded_extensions_info():
    """Get excluded extensions file information"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/excluded-extensions-info", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching excluded extensions info: {e}")
    return {"error": "microservice_unavailable"}

async def get_excluded_extensions_content():
    """Get excluded extensions file content"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-excluded-extensions", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                content_data = response.json()
                if content_data.get("status") == "success":
                    return content_data.get("excluded_extensions", "")
    except Exception as e:
        logger.error(f"Error fetching excluded extensions content: {e}")
    return ""

async def update_excluded_extensions(content: str):
    """Update excluded extensions file content"""
    payload = {"content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MICROSERVICE_URL}/update-excluded-extensions",
            json=payload, headers=get_auth_headers()
        )
        return response

async def get_excluded_files_info():
    """Get excluded files information"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/excluded-files-info", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching excluded files info: {e}")
    return {"error": "microservice_unavailable"}

async def get_excluded_files_content():
    """Get excluded files content"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MICROSERVICE_URL}/get-excluded-files", timeout=5.0, headers=get_auth_headers())
            if response.status_code == 200:
                content_data = response.json()
                if content_data.get("status") == "success":
                    return content_data.get("excluded_files", "")
    except Exception as e:
        logger.error(f"Error fetching excluded files content: {e}")
    return ""

async def update_excluded_files(content: str):
    """Update excluded files content"""
    payload = {"content": content}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MICROSERVICE_URL}/update-excluded-files",
            json=payload, headers=get_auth_headers()
        )
        return response