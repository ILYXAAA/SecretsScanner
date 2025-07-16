#!/usr/bin/env python3
"""
Export secrets from database to text files
Creates TrueSecrets.txt, FalseSecrets.txt, and AllSecrets.txt
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Main function to export secrets"""
    
    # Get database URL
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
    
    # Connect to database
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    
    print("🔍 Fetching secrets from database...")
    
    # Get all secrets from database
    with engine.connect() as conn:
        query = text("SELECT secret, status, is_exception FROM secrets")
        rows = conn.execute(query).fetchall()
    
    print(f"📊 Found {len(rows)} total records")
    
    # Filter secrets
    confirmed_secrets = set()
    refuted_secrets = set()
    all_secrets = set()
    
    excluded_count = 0
    
    for row in rows:
        secret = row[0]
        status = row[1] 
        is_exception = row[2]
        
        # Skip empty/null secrets
        if not secret:
            continue
            
        # Check if should exclude
        if should_exclude(secret):
            excluded_count += 1
            continue
            
        # Add to all secrets
        all_secrets.add(secret)
        
        # Categorize
        if status == 'Confirmed' and not is_exception:
            confirmed_secrets.add(secret)
        elif status == 'Refuted' or is_exception:
            refuted_secrets.add(secret)
    
    print(f"🚫 Excluded {excluded_count} system messages")
    
    # Write files
    write_file("utils/TrueSecrets.txt", sorted(confirmed_secrets))
    write_file("utils/FalseSecrets.txt", sorted(refuted_secrets))
    write_file("utils/AllSecrets.txt", sorted(all_secrets))
    
    # Print results
    print(f"\n✅ Export completed!")
    print(f"📄 TrueSecrets.txt: {len(confirmed_secrets)} secrets")
    print(f"📄 FalseSecrets.txt: {len(refuted_secrets)} secrets")
    print(f"📄 AllSecrets.txt: {len(all_secrets)} secrets")

def is_valid_secret(secret):
    """Validate if secret is printable and safe to write"""
    if not secret:
        return False
    
    try:
        # Check if string is too short or too long
        if len(secret) < 3 or len(secret) > 10000:
            return False
        
        # Check for null bytes and other problematic characters
        if '\x00' in secret:
            return False
            
        # Check for too many non-printable characters
        printable_count = sum(1 for c in secret if c.isprintable())
        total_length = len(secret)
        
        # If less than 70% of characters are printable, reject
        if printable_count / total_length < 0.7:
            return False
        
        # Check for excessive binary-like content
        control_chars = sum(1 for c in secret if ord(c) < 32 and c not in ['\n', '\r', '\t'])
        if control_chars > 10:  # Too many control characters
            return False
        
        # Check entropy - if too random, might be binary data
        if calculate_entropy(secret) > 7.5:  # Very high entropy
            return False
            
        # Try to encode as UTF-8 to ensure it's valid
        secret.encode('utf-8')
        
        return True
        
    except (UnicodeError, UnicodeDecodeError, UnicodeEncodeError):
        return False
    except Exception:
        return False

def calculate_entropy(text):
    """Calculate Shannon entropy of text"""
    import math
    from collections import Counter
    
    if not text:
        return 0
    
    # Count character frequencies
    counts = Counter(text)
    length = len(text)
    
    # Calculate entropy
    entropy = 0
    for count in counts.values():
        probability = count / length
        if probability > 0:
            entropy -= probability * math.log2(probability)
    
    return entropy

def should_exclude(secret):
    """Check if secret should be excluded"""
    if not secret:
        return True
        
    # First check validity
    if not is_valid_secret(secret):
        return True
        
    # List of phrases to exclude
    exclude_phrases = [
        "СТРОКА НЕ СКАНИРОВАЛАСЬ",
        "ФАЙЛ НЕ ВЫВЕДЕН ПОЛНОСТЬЮ"
    ]
    
    # Check each phrase
    for phrase in exclude_phrases:
        if phrase in secret:
            return True
    
    # Check for common non-secret patterns
    non_secret_patterns = [
        "test",
        "example", 
        "placeholder",
        "dummy",
        "fake",
        "lorem ipsum"
    ]
    
    secret_lower = secret.lower()
    for pattern in non_secret_patterns:
        if pattern in secret_lower and len(secret) < 50:
            return True
            
    return False

def write_file(filename, secrets):
    """Write secrets to file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for secret in secrets:
                f.write(f"{secret}\n")
        print(f"✅ Created {filename}")
    except Exception as e:
        print(f"❌ Error creating {filename}: {e}")

if __name__ == "__main__":
    main()