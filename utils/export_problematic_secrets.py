#!/usr/bin/env python3
"""
Export problematic refuted secrets by type with highest confidence
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Main function to export problematic secrets"""
    
    # Configuration
    N_SECRETS_PER_TYPE = 20  # Number of secrets per type to export
    
    # Get database URL
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
    
    # Connect to database
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    
    print("🔍 Fetching refuted secrets from database...")
    
    # Get refuted secrets excluding specific types
    with engine.connect() as conn:
        query = text("""
            SELECT secret, confidence, type, context
            FROM secrets 
            WHERE status = 'Refuted' 
            AND type NOT IN ('Too Long Line', 'Too Many Secrets')
            ORDER BY type, confidence DESC
        """)
        rows = conn.execute(query).fetchall()
    
    print(f"📊 Found {len(rows)} refuted records")
    
    # Group by type and select top N by confidence
    type_groups = {}
    
    for row in rows:
        secret = row[0]
        confidence = row[1] or 0  # Handle None confidence
        secret_type = row[2] or "Unknown"
        context = row[3] or ""
        
        # Skip empty secrets
        if not secret or not secret.strip():
            continue
            
        if secret_type not in type_groups:
            type_groups[secret_type] = []
        
        type_groups[secret_type].append({
            'secret': secret.strip(),
            'confidence': confidence,
            'context': context.strip() if context else ""
        })
    
    # Select top N unique secrets per type
    selected_secrets = []
    
    for secret_type, secrets in type_groups.items():
        # Sort by confidence descending
        secrets.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Select unique secrets (by secret text)
        unique_secrets = []
        seen_secrets = set()
        
        for secret_data in secrets:
            secret_text = secret_data['secret']
            if secret_text not in seen_secrets:
                seen_secrets.add(secret_text)
                unique_secrets.append(secret_data)
                
                if len(unique_secrets) >= N_SECRETS_PER_TYPE:
                    break
        
        # Add to selected with type info
        for secret_data in unique_secrets:
            selected_secrets.append({
                'type': secret_type,
                'confidence': secret_data['confidence'],
                'secret': secret_data['secret'],
                'context': secret_data['context']
            })
    
    # Write to file
    output_file = "utils/problematic_secrets.txt"
    write_secrets_file(output_file, selected_secrets)
    
    # Print summary
    print(f"\n✅ Export completed!")
    print(f"📄 File: {output_file}")
    print(f"📊 Total secrets: {len(selected_secrets)}")
    print(f"📋 Types found: {len(type_groups)}")
    
    # Print type summary
    type_counts = {}
    for secret in selected_secrets:
        secret_type = secret['type']
        type_counts[secret_type] = type_counts.get(secret_type, 0) + 1
    
    print("\n📊 Secrets per type:")
    for secret_type, count in sorted(type_counts.items()):
        print(f"   {secret_type}: {count} secrets")

def write_secrets_file(filename, secrets):
    """Write secrets to formatted text file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            # Write header
            f.write("PROBLEMATIC REFUTED SECRETS\n")
            f.write("=" * 80 + "\n\n")
            
            # Calculate column widths for alignment
            max_type_len = max(len(s['type']) for s in secrets) if secrets else 10
            type_width = max(max_type_len, 15)
            
            # Write column headers
            header = f"{'Type':<{type_width}} | {'Conf':<4} | {'Secret':<50} | Context"
            f.write(header + "\n")
            f.write("-" * len(header) + "\n")
            
            # Group by type for better readability
            current_type = None
            
            for secret in sorted(secrets, key=lambda x: (x['type'], -x['confidence'])):
                secret_type = secret['type']
                confidence = secret['confidence']
                secret_text = secret['secret']
                context = secret['context']
                
                # Add separator between types
                if current_type != secret_type:
                    if current_type is not None:
                        f.write("\n")
                    current_type = secret_type
                
                # Truncate long secrets for display
                display_secret = secret_text[:47] + "..." if len(secret_text) > 50 else secret_text
                
                # Truncate long context for display
                display_context = context[:100] + "..." if len(context) > 100 else context
                
                # Write formatted line
                line = f"{secret_type:<{type_width}} | {confidence:<4.1f} | {display_secret:<50} | {display_context}"
                f.write(line + "\n")
        
        print(f"✅ Created {filename}")
        
    except Exception as e:
        print(f"❌ Error creating {filename}: {e}")

if __name__ == "__main__":
    main()