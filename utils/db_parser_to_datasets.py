#!/usr/bin/env python3
"""
Export secrets from database to text files
Creates TrueSecrets.txt, FalseSecrets.txt, and AllSecrets.txt
"""

import os
import re
import math
from collections import Counter
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from tqdm import tqdm
from difflib import SequenceMatcher

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
        query = text("SELECT secret, status, is_exception, context FROM secrets")
        rows = conn.execute(query).fetchall()
    
    print(f"📊 Found {len(rows)} total records")
    
    # Process secrets with optimized batching
    confirmed_secrets = set()
    refuted_secrets = set()
    all_secrets = set()
    
    excluded_count = 0
    batch_size = 10000
    
    print("🔄 Processing secrets...")
    
    # Process in batches for better memory usage and progress tracking
    for i in tqdm(range(0, len(rows), batch_size), desc="Processing batches"):
        batch = rows[i:i + batch_size]
        
        # Pre-filter batch for quick exclusions
        valid_batch = []
        for row in batch:
            secret = row[0]
            if secret and len(str(secret).strip()) >= 3:  # Quick length check
                valid_batch.append(row)
            else:
                excluded_count += 1
        
        # Process valid entries
        for row in valid_batch:
            secret = row[0]
            status = row[1] 
            is_exception = row[2]
            context = row[3] if len(row) > 3 else None
            
            # Fast pre-check for common exclusion patterns
            if quick_should_exclude(secret):
                excluded_count += 1
                continue
            
            # Process context if file wasn't fully exported
            if "**ФАЙЛ НЕ ВЫВЕДЕН ПОЛНОСТЬЮ**" in secret and context:
                context_secrets = extract_secrets_from_context(context)
                for ctx_secret in context_secrets:
                    processed_secret = process_secret_fast(ctx_secret, context)
                    if processed_secret:
                        all_secrets.add(processed_secret)
                        if status == 'Confirmed' and not is_exception:
                            confirmed_secrets.add(processed_secret)
                        elif status == 'Refuted' or is_exception:
                            refuted_secrets.add(processed_secret)
                continue
                
            # Process regular secret
            processed_secret = process_secret_fast(secret, context)
            
            # Check if should exclude (full check)
            if not processed_secret or should_exclude_fast(processed_secret):
                excluded_count += 1
                continue
                
            # Add to all secrets
            all_secrets.add(processed_secret)
            
            # Categorize
            if status == 'Confirmed' and not is_exception:
                confirmed_secrets.add(processed_secret)
            elif status == 'Refuted' or is_exception:
                refuted_secrets.add(processed_secret)
    
    print(f"🚫 Excluded {excluded_count} invalid entries")
    
    # Convert sets to sorted lists (no similarity removal for performance)
    print("📋 Finalizing unique secrets...")
    confirmed_secrets = sorted(list(confirmed_secrets))
    refuted_secrets = sorted(list(refuted_secrets))
    all_secrets = sorted(list(all_secrets))
    
    # Write files
    print("📝 Writing output files...")
    write_file("utils/TrueSecrets.txt", sorted(confirmed_secrets))
    write_file("utils/FalseSecrets.txt", sorted(refuted_secrets))
    write_file("utils/AllSecrets.txt", sorted(all_secrets))
    
    # Print results
    print(f"\n✅ Export completed!")
    print(f"📄 TrueSecrets.txt: {len(confirmed_secrets)} secrets")
    print(f"📄 FalseSecrets.txt: {len(refuted_secrets)} secrets")
    print(f"📄 AllSecrets.txt: {len(all_secrets)} secrets")

def extract_secrets_from_context(context):
    """Extract secrets from context field when file wasn't fully exported"""
    if not context:
        return []
    
    secrets = []
    
    # Look for pattern: "Найдено секретов: X Список найденных секретов ниже:"
    lines = context.split('\n')
    collecting = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Start collecting after finding the header
        if "Список найденных секретов" in line:
            collecting = True
            continue
            
        if collecting and line:
            # Skip lines that look like headers or system messages
            if not line.startswith("Найдено") and not line.startswith("Список"):
                secrets.append(line)
    
    return secrets

def process_secret(secret, context=None):
    """Process a single secret, potentially replacing with context"""
    if not secret:
        return None
    
    # Clean the secret first
    cleaned_secret = clean_secret(secret)
    if not cleaned_secret:
        return None
    
    # Check if we should use context instead
    if context and len(context.strip()) > 0:
        context_clean = clean_secret(context)
        if (context_clean and 
            len(context_clean) <= len(cleaned_secret) * 4 and 
            len(context_clean) < 300 and
            len(context_clean) > len(cleaned_secret)):
            return context_clean
    
    return cleaned_secret

def clean_secret(secret):
    """Clean secret by removing control characters and validating"""
    if not secret:
        return None
    
    # Remove control characters except newlines, tabs, carriage returns
    cleaned = ''.join(char for char in secret if char.isprintable() or char in ['\n', '\r', '\t'])
    
    # Replace control characters with spaces and normalize whitespace
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    if not cleaned:
        return None
    
    return cleaned

def has_foreign_characters(text):
    """Check if text contains non-Latin characters like Arabic, Chinese, etc."""
    if not text:
        return False
    
    # Define ranges for foreign scripts
    foreign_ranges = [
        (0x0590, 0x05FF),  # Hebrew
        (0x0600, 0x06FF),  # Arabic
        (0x0750, 0x077F),  # Arabic Supplement
        (0x4E00, 0x9FFF),  # CJK Unified Ideographs (Chinese, Japanese, Korean)
        (0x3400, 0x4DBF),  # CJK Extension A
        (0xAC00, 0xD7AF),  # Hangul Syllables (Korean)
        (0x0400, 0x04FF),  # Cyrillic (Russian, etc.) - commented out as it might be needed
        (0x0370, 0x03FF),  # Greek
        (0x0900, 0x097F),  # Devanagari (Hindi)
        (0x0980, 0x09FF),  # Bengali
        (0x0A00, 0x0A7F),  # Gurmukhi
        (0x0A80, 0x0AFF),  # Gujarati
        (0x0B00, 0x0B7F),  # Oriya
        (0x0B80, 0x0BFF),  # Tamil
        (0x0C00, 0x0C7F),  # Telugu
        (0x0C80, 0x0CFF),  # Kannada
        (0x0D00, 0x0D7F),  # Malayalam
        (0x0E00, 0x0E7F),  # Thai
        (0x1000, 0x109F),  # Myanmar
        (0x10A0, 0x10FF),  # Georgian
    ]
    
    for char in text:
        char_code = ord(char)
        for start, end in foreign_ranges:
            if start <= char_code <= end:
                return True
    
    return False

def similarity(a, b):
    """Calculate similarity between two strings"""
    return SequenceMatcher(None, a, b).ratio()

def remove_similar_secrets(secrets_list):
    """Remove secrets that are too similar to each other"""
    if not secrets_list:
        return []
    
    unique_secrets = []
    
    print(f"🔄 Checking {len(secrets_list)} secrets for similarity...")
    
    for secret in tqdm(secrets_list, desc="Removing similar"):
        is_unique = True
        
        for existing in unique_secrets:
            # Calculate similarity
            sim_ratio = similarity(secret.lower(), existing.lower())
            
            # If similarity is too high (less than 3 character difference proportionally)
            if sim_ratio > 0.9:  # Roughly equivalent to less than 3 char difference for short strings
                is_unique = False
                break
            
            # Also check edit distance for short strings
            if len(secret) < 50 and len(existing) < 50:
                # Calculate approximate edit distance
                max_len = max(len(secret), len(existing))
                edit_distance = (1 - sim_ratio) * max_len
                if edit_distance < 3:
                    is_unique = False
                    break
        
        if is_unique:
            unique_secrets.append(secret)
    
    print(f"🔄 Removed {len(secrets_list) - len(unique_secrets)} similar secrets")
    return unique_secrets

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
        
        # Check for foreign characters
        if has_foreign_characters(secret):
            return False
            
        # Check for too many non-printable characters
        printable_count = sum(1 for c in secret if c.isprintable())
        total_length = len(secret)
        
        # If less than 70% of characters are printable, reject
        if total_length > 0 and printable_count / total_length < 0.7:
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

def quick_should_exclude(secret):
    """Quick exclusion check for obvious cases"""
    if not secret:
        return True
    
    secret_str = str(secret)
    
    # Quick length check
    if len(secret_str) < 3 or len(secret_str) > 10000:
        return True
    
    # Quick check for exclude phrases
    if ("СТРОКА НЕ СКАНИРОВАЛАСЬ" in secret_str or 
        "ФАЙЛ НЕ ВЫВЕДЕН ПОЛНОСТЬЮ" in secret_str):
        return True
    
    return False

def should_exclude_fast(secret):
    """Fast version of should_exclude with minimal regex"""
    if not secret:
        return True
    
    # Use the optimized validity check
    if not is_valid_secret_fast(secret):
        return True
    
    # Check for common non-secret patterns (simplified)
    if len(secret) < 50:
        secret_lower = secret.lower()
        non_secret_words = ["test", "example", "placeholder", "dummy", "fake"]
        if any(word in secret_lower for word in non_secret_words):
            return True
    
    return False

def process_secret_fast(secret, context=None):
    """Fast version of process_secret"""
    if not secret:
        return None
    
    # Quick clean
    cleaned_secret = clean_secret_fast(secret)
    if not cleaned_secret:
        return None
    
    # Context check (simplified)
    if (context and 
        len(context.strip()) > len(cleaned_secret) and
        len(context.strip()) <= len(cleaned_secret) * 4 and 
        len(context.strip()) < 300):
        context_clean = clean_secret_fast(context)
        if context_clean:
            return context_clean
    
    return cleaned_secret

def clean_secret_fast(secret):
    """Fast version of clean_secret"""
    if not secret:
        return None
    
    # Quick printable filter and whitespace normalization
    cleaned = ''.join(char if char.isprintable() else ' ' for char in str(secret))
    
    # Simple whitespace normalization
    cleaned = ' '.join(cleaned.split())
    
    return cleaned if cleaned and len(cleaned) >= 3 else None

def is_valid_secret_fast(secret):
    """Fast version of is_valid_secret with essential checks only"""
    if not secret:
        return False
    
    try:
        secret_str = str(secret)
        
        # Length check
        if len(secret_str) < 3 or len(secret_str) > 10000:
            return False
        
        # Null bytes check
        if '\x00' in secret_str:
            return False
        
        # Foreign characters check (simplified)
        if has_foreign_characters_fast(secret_str):
            return False
        
        # Basic printable ratio check
        if len(secret_str) > 20:  # Only for longer strings to save time
            printable_count = sum(1 for c in secret_str if c.isprintable())
            if printable_count / len(secret_str) < 0.7:
                return False
        
        return True
        
    except Exception:
        return False

def has_foreign_characters_fast(text):
    """Fast foreign character detection - checks all characters"""
    if not text:
        return False
    
    # Check all characters for foreign scripts
    for char in text:
        char_code = ord(char)
        
        # Extended ranges for foreign scripts
        if (0x0590 <= char_code <= 0x05FF or    # Hebrew
            0x0600 <= char_code <= 0x06FF or    # Arabic
            0x0750 <= char_code <= 0x077F or    # Arabic Supplement
            0x4E00 <= char_code <= 0x9FFF or    # CJK Unified Ideographs
            0x3400 <= char_code <= 0x4DBF or    # CJK Extension A
            0xAC00 <= char_code <= 0xD7AF or    # Hangul Syllables (Korean)
            0x3130 <= char_code <= 0x318F or    # Hangul Compatibility Jamo
            0xA960 <= char_code <= 0xA97F or    # Hangul Jamo Extended-A
            0xD7B0 <= char_code <= 0xD7FF or    # Hangul Jamo Extended-B
            0x0900 <= char_code <= 0x097F or    # Devanagari (Hindi)
            0x0980 <= char_code <= 0x09FF or    # Bengali
            0x0A00 <= char_code <= 0x0A7F or    # Gurmukhi
            0x0A80 <= char_code <= 0x0AFF or    # Gujarati
            0x0B00 <= char_code <= 0x0B7F or    # Oriya
            0x0B80 <= char_code <= 0x0BFF or    # Tamil
            0x0C00 <= char_code <= 0x0C7F or    # Telugu
            0x0C80 <= char_code <= 0x0CFF or    # Kannada
            0x0D00 <= char_code <= 0x0D7F or    # Malayalam
            0x0E00 <= char_code <= 0x0E7F or    # Thai
            0x0E80 <= char_code <= 0x0EFF or    # Lao
            0x1000 <= char_code <= 0x109F or    # Myanmar
            0x10A0 <= char_code <= 0x10FF or    # Georgian
            0x1200 <= char_code <= 0x137F or    # Ethiopic
            0x13A0 <= char_code <= 0x13FF or    # Cherokee
            0x1700 <= char_code <= 0x171F or    # Tagalog
            0x1780 <= char_code <= 0x17FF or    # Khmer
            0x1800 <= char_code <= 0x18AF):     # Mongolian
            return True
    
    return False

def write_file(filename, secrets):
    """Write secrets to file, ensuring no empty lines"""
    try:
        # Filter out any empty or whitespace-only secrets
        valid_secrets = [secret.strip() for secret in secrets if secret and secret.strip()]
        
        with open(filename, 'w', encoding='utf-8') as f:
            for secret in valid_secrets:
                # Ensure no empty lines by double-checking
                if secret:
                    f.write(f"{secret}\n")
        
        print(f"✅ Created {filename}")
    except Exception as e:
        print(f"❌ Error creating {filename}: {e}")

if __name__ == "__main__":
    main()