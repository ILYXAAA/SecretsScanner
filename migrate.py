#!/usr/bin/env python3
"""
CLI tool for managing database migrations
Usage:
    python migrate.py status              # Show migration status
    python migrate.py migrate             # Apply all pending migrations  
    python migrate.py migrate 003         # Apply migrations up to version 003
    python migrate.py rollback 002        # Rollback to version 002
    python migrate.py create              # Interactive migration creator
    python migrate.py create "description" # Create migration with description only
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import inspect

# Load environment variables
load_dotenv()

from config import DATABASE_URL
from services.migrations import MigrationSystem

def get_existing_tables(migration_system):
    """Get list of existing tables"""
    try:
        inspector = inspect(migration_system.engine)
        return inspector.get_table_names()
    except Exception as e:
        print(f"Error getting tables: {e}")
        return []

def get_table_columns(migration_system, table_name):
    """Get columns for a specific table"""
    try:
        inspector = inspect(migration_system.engine)
        columns = inspector.get_columns(table_name)
        return [(col['name'], str(col['type']), col.get('default')) for col in columns]
    except Exception as e:
        print(f"Error getting columns for {table_name}: {e}")
        return []

def interactive_migration_creator():
    """Interactive migration creator"""
    print("\n🔧 Interactive Migration Creator")
    print("=" * 40)
    
    # Initialize migration system
    migration_system = MigrationSystem(DATABASE_URL)
    
    # Get migration description
    description = input("📝 Enter migration description: ").strip()
    if not description:
        print("❌ Description is required")
        return None
    
    # Migration data
    migration_data = {
        'description': description,
        'tables': {},
        'indexes': [],
        'custom_sql': []
    }
    
    while True:
        print("\n📋 What would you like to do?")
        print("1. Add/modify table")
        print("2. Add index")
        print("3. Add custom SQL")
        print("4. Generate migration")
        print("5. Cancel")
        
        choice = input("Choose option (1-5): ").strip()
        
        if choice == '1':
            handle_table_operations(migration_system, migration_data)
        elif choice == '2':
            handle_index_operations(migration_data)
        elif choice == '3':
            handle_custom_sql(migration_data)
        elif choice == '4':
            return generate_migration_file_from_data(migration_data)
        elif choice == '5':
            print("❌ Migration creation cancelled")
            return None
        else:
            print("❌ Invalid choice")

def handle_table_operations(migration_system, migration_data):
    """Handle table creation/modification"""
    existing_tables = get_existing_tables(migration_system)
    
    print("\n📊 Table Operations")
    print("1. Create new table")
    print("2. Modify existing table")
    
    choice = input("Choose option (1-2): ").strip()
    
    if choice == '1':
        create_new_table(migration_data)
    elif choice == '2':
        modify_existing_table(migration_system, migration_data, existing_tables)
    else:
        print("❌ Invalid choice")

def create_new_table(migration_data):
    """Create new table configuration"""
    table_name = input("📊 Enter new table name: ").strip()
    if not table_name:
        print("❌ Table name is required")
        return
    
    if table_name in migration_data['tables']:
        print(f"⚠️ Table {table_name} already configured in this migration")
        return
    
    print(f"\n➕ Adding columns to table '{table_name}'")
    print("Enter column details (press Enter with empty name to finish):")
    
    columns = []
    primary_key_set = False
    
    while True:
        column_name = input("  Column name: ").strip()
        if not column_name:
            break
        
        # Column type
        print("  Available types:")
        print("    1. INTEGER    2. TEXT       3. REAL       4. BOOLEAN")
        print("    5. TIMESTAMP  6. VARCHAR()  7. Custom")
        
        type_choice = input("  Select type (1-7): ").strip()
        
        type_map = {
            '1': 'INTEGER',
            '2': 'TEXT', 
            '3': 'REAL',
            '4': 'BOOLEAN',
            '5': 'TIMESTAMP',
            '6': 'VARCHAR',
            '7': 'CUSTOM'
        }
        
        if type_choice in type_map:
            col_type = type_map[type_choice]
            if col_type == 'VARCHAR':
                length = input("  VARCHAR length (default 255): ").strip() or "255"
                col_type = f"VARCHAR({length})"
            elif col_type == 'CUSTOM':
                col_type = input("  Enter custom type: ").strip()
        else:
            col_type = 'TEXT'  # default
        
        # Constraints
        constraints = []
        
        if not primary_key_set and input("  Primary key? (y/N): ").strip().lower() == 'y':
            constraints.append("PRIMARY KEY")
            primary_key_set = True
        
        if input("  Not null? (y/N): ").strip().lower() == 'y':
            constraints.append("NOT NULL")
        
        if input("  Unique? (y/N): ").strip().lower() == 'y':
            constraints.append("UNIQUE")
        
        # Default value
        default = input("  Default value (optional): ").strip()
        if default:
            # Handle special SQL values without quotes
            if default.upper() in ['CURRENT_TIMESTAMP', 'NOW()', 'NULL']:
                constraints.append(f"DEFAULT {default}")
            # Handle boolean values
            elif default.lower() in ['true', 'false', '1', '0'] and col_type.upper() == 'BOOLEAN':
                # Convert to database-appropriate format
                if default.lower() in ['true', '1']:
                    constraints.append("DEFAULT true")
                else:
                    constraints.append("DEFAULT false")
            # Handle numeric values
            elif default.replace('.', '').replace('-', '').isdigit():
                constraints.append(f"DEFAULT {default}")
            # Handle string values
            else:
                constraints.append(f"DEFAULT '{default}'")
        
        # Build column definition
        column_def = f"{column_name} {col_type}"
        if constraints:
            column_def += " " + " ".join(constraints)
        
        columns.append(column_def)
        print(f"  ✅ Added: {column_def}")
    
    if not columns:
        print("❌ No columns defined for table")
        return
    
    migration_data['tables'][table_name] = {
        'action': 'create',
        'columns': columns
    }
    
    print(f"✅ Table '{table_name}' configured for creation")

def modify_existing_table(migration_system, migration_data, existing_tables):
    """Modify existing table"""
    if not existing_tables:
        print("❌ No existing tables found")
        return
    
    print("\n📊 Select table to modify:")
    for i, table in enumerate(existing_tables, 1):
        print(f"  {i}. {table}")
    
    try:
        choice = int(input("Enter table number: ")) - 1
        table_name = existing_tables[choice]
    except (ValueError, IndexError):
        print("❌ Invalid selection")
        return
    
    # Show current columns
    current_columns = get_table_columns(migration_system, table_name)
    print(f"\n📋 Current columns in '{table_name}':")
    for col_name, col_type, default in current_columns:
        default_str = f" DEFAULT {default}" if default else ""
        print(f"  - {col_name}: {col_type}{default_str}")
    
    print(f"\n➕ Adding new columns to '{table_name}'")
    print("Enter new column details (press Enter with empty name to finish):")
    
    new_columns = []
    
    while True:
        column_name = input("  Column name: ").strip()
        if not column_name:
            break
        
        # Check if column already exists
        if any(col[0] == column_name for col in current_columns):
            print(f"  ⚠️ Column '{column_name}' already exists")
            continue
        
        # Column type selection (same as create_new_table)
        print("  Available types:")
        print("    1. INTEGER    2. TEXT       3. REAL       4. BOOLEAN")
        print("    5. TIMESTAMP  6. VARCHAR()  7. Custom")
        
        type_choice = input("  Select type (1-7): ").strip()
        
        type_map = {
            '1': 'INTEGER',
            '2': 'TEXT', 
            '3': 'REAL',
            '4': 'BOOLEAN',
            '5': 'TIMESTAMP',
            '6': 'VARCHAR',
            '7': 'CUSTOM'
        }
        
        if type_choice in type_map:
            col_type = type_map[type_choice]
            if col_type == 'VARCHAR':
                length = input("  VARCHAR length (default 255): ").strip() or "255"
                col_type = f"VARCHAR({length})"
            elif col_type == 'CUSTOM':
                col_type = input("  Enter custom type: ").strip()
        else:
            col_type = 'TEXT'
        
        # Default value for new columns (recommended for existing tables)
        default = input("  Default value (recommended for existing tables): ").strip()
        
        column_def = f"{column_name} {col_type}"
        if default:
            # Handle special SQL values without quotes
            if default.upper() in ['CURRENT_TIMESTAMP', 'NOW()', 'NULL']:
                column_def += f" DEFAULT {default}"
            # Handle boolean values
            elif default.lower() in ['true', 'false', '1', '0'] and col_type.upper() == 'BOOLEAN':
                if default.lower() in ['true', '1']:
                    column_def += " DEFAULT true"
                else:
                    column_def += " DEFAULT false"
            # Handle numeric values
            elif default.replace('.', '').replace('-', '').isdigit():
                column_def += f" DEFAULT {default}"
            # Handle string values  
            else:
                column_def += f" DEFAULT '{default}'"
        
        new_columns.append(column_def)
        print(f"  ✅ Added: {column_def}")
    
    if not new_columns:
        print("❌ No new columns defined")
        return
    
    if table_name not in migration_data['tables']:
        migration_data['tables'][table_name] = {'action': 'modify', 'columns': []}
    
    migration_data['tables'][table_name]['columns'].extend(new_columns)
    print(f"✅ New columns configured for '{table_name}'")

def handle_index_operations(migration_data):
    """Handle index creation"""
    print("\n🔍 Add Index")
    
    index_name = input("Index name: ").strip()
    if not index_name:
        print("❌ Index name is required")
        return
    
    table_name = input("Table name: ").strip()
    if not table_name:
        print("❌ Table name is required")
        return
    
    columns = input("Columns (comma-separated): ").strip()
    if not columns:
        print("❌ Columns are required")
        return
    
    unique = input("Unique index? (y/N): ").strip().lower() == 'y'
    
    index_type = "UNIQUE INDEX" if unique else "INDEX"
    index_sql = f"CREATE {index_type} IF NOT EXISTS {index_name} ON {table_name} ({columns})"
    
    migration_data['indexes'].append({
        'name': index_name,
        'sql': index_sql
    })
    
    print(f"✅ Index '{index_name}' configured")

def handle_custom_sql(migration_data):
    """Handle custom SQL operations"""
    print("\n⚙️ Add Custom SQL")
    print("Enter SQL statement (or multiple lines, end with empty line):")
    
    sql_lines = []
    while True:
        line = input("SQL> ").strip()
        if not line:
            break
        sql_lines.append(line)
    
    if not sql_lines:
        print("❌ No SQL entered")
        return
    
    sql = " ".join(sql_lines)
    description = input("Description for this SQL: ").strip() or "Custom SQL operation"
    
    migration_data['custom_sql'].append({
        'sql': sql,
        'description': description
    })
    
    print("✅ Custom SQL configured")

def generate_migration_file_from_data(migration_data):
    """Generate migration file from collected data"""
    migrations_dir = Path("migrations")
    migrations_dir.mkdir(exist_ok=True)
    
    # Find next version number
    existing_migrations = sorted([f for f in migrations_dir.glob("*.py") if not f.name.startswith("__")])
    
    if existing_migrations:
        last_file = existing_migrations[-1]
        last_version = int(last_file.stem.split("_")[0])
        next_version = str(last_version + 1).zfill(3)
    else:
        next_version = "001"
    
    # Create filename
    safe_description = migration_data['description'].lower().replace(" ", "_").replace("-", "_")
    filename = f"{next_version}_{safe_description}.py"
    file_path = migrations_dir / filename
    
    # Generate migration content
    upgrade_code = []
    downgrade_code = []
    
    # Tables
    for table_name, table_config in migration_data['tables'].items():
        if table_config['action'] == 'create':
            # Create table
            columns_sql = ",\n        ".join(table_config['columns'])
            upgrade_code.append(f"""
    # Create table {table_name}
    migration_system.safe_create_table('''
        CREATE TABLE {table_name} (
        {columns_sql}
        )
    ''', "{table_name}")""")
            
            downgrade_code.append(f"""
    # Drop table {table_name}
    migration_system.safe_drop_table("{table_name}")""")
            
        elif table_config['action'] == 'modify':
            # Add columns
            for column_def in table_config['columns']:
                upgrade_code.append(f"""
    # Add column to {table_name}
    migration_system.safe_add_column("{table_name}", "{column_def}")""")
                
                column_name = column_def.split()[0]
                downgrade_code.append(f"""
    # Drop column {column_name} from {table_name}
    migration_system.safe_drop_column("{table_name}", "{column_name}")""")
    
    # Indexes
    for index_config in migration_data['indexes']:
        upgrade_code.append(f"""
    # Create index {index_config['name']}
    migration_system.safe_create_index(
        "{index_config['sql']}",
        "{index_config['name']}"
    )""")
        
        downgrade_code.append(f"""
    # Drop index {index_config['name']}
    with migration_system.engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS {index_config['name']}"))
        conn.commit()""")
    
    # Custom SQL
    for sql_config in migration_data['custom_sql']:
        upgrade_code.append(f"""
    # {sql_config['description']}
    migration_system.execute_sql(
        "{sql_config['sql']}",
        "{sql_config['description']}"
    )""")
    
    # Build final migration file
    upgrade_content = "".join(upgrade_code) if upgrade_code else "\n    pass  # No operations defined"
    downgrade_content = "".join(downgrade_code) if downgrade_code else "\n    pass  # No rollback operations defined"
    
    migration_content = f'''"""
{migration_data['description']}
"""

def upgrade(migration_system):
    """Apply migration changes"""
    from sqlalchemy import text{upgrade_content}

def downgrade(migration_system):
    """Rollback migration changes"""
    from sqlalchemy import text{downgrade_content}
'''
    
    # Write migration file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(migration_content)
    
    print(f"\n✅ Created migration file: {file_path}")
    print("\n📋 Migration Summary:")
    print(f"   Tables: {len(migration_data['tables'])}")
    print(f"   Indexes: {len(migration_data['indexes'])}")
    print(f"   Custom SQL: {len(migration_data['custom_sql'])}")
    
    return file_path

def create_migration_file(description: str):
    """Create a simple migration file with template"""
    migrations_dir = Path("migrations")
    migrations_dir.mkdir(exist_ok=True)
    
    # Find next version number
    existing_migrations = sorted([f for f in migrations_dir.glob("*.py") if not f.name.startswith("__")])
    
    if existing_migrations:
        last_file = existing_migrations[-1]
        last_version = int(last_file.stem.split("_")[0])
        next_version = str(last_version + 1).zfill(3)
    else:
        next_version = "001"
    
    # Create filename
    safe_description = description.lower().replace(" ", "_").replace("-", "_")
    filename = f"{next_version}_{safe_description}.py"
    file_path = migrations_dir / filename
    
    # Create migration template
    template = f'''"""
{description}
"""

def upgrade(migration_system):
    """Apply migration changes"""
    from sqlalchemy import text
    
    # Example: Add a new column
    # migration_system.safe_add_column("table_name", "column_name TYPE DEFAULT value")
    
    # Example: Create an index
    # migration_system.safe_create_index(
    #     "CREATE INDEX IF NOT EXISTS idx_name ON table_name (column)",
    #     "idx_name"
    # )
    
    # Example: Create a table using safe method
    # migration_system.safe_create_table("""
    #     CREATE TABLE new_table (
    #         id INTEGER PRIMARY KEY,
    #         name TEXT NOT NULL,
    #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    #     )
    # """, "new_table")
    
    # Example: Execute custom SQL
    # migration_system.execute_sql(
    #     "UPDATE table_name SET column = 'value' WHERE condition",
    #     "Update existing records with new values"
    # )
    
    pass  # Remove this line when implementing

def downgrade(migration_system):
    """Rollback migration changes"""
    from sqlalchemy import text
    
    # Example: Drop a column safely (handles SQLite limitations)
    # migration_system.safe_drop_column("table_name", "column_name")
    
    # Example: Drop an index
    # with migration_system.engine.connect() as conn:
    #     conn.execute(text("DROP INDEX IF EXISTS idx_name"))
    #     conn.commit()
    
    # Example: Drop a table safely
    # migration_system.safe_drop_table("new_table")
    
    pass  # Remove this line when implementing
'''
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(template)
    
    print(f"Created migration file: {file_path}")
    return file_path

def manual_mark_applied(migration_system, version, description="Manually marked"):
    """Manually mark migration as applied"""
    try:
        migration_system._mark_migration_applied(version, description)
        print(f"✅ Marked migration {version} as applied")
    except Exception as e:
        print(f"❌ Error marking migration {version}: {e}")

def manual_unmark_applied(migration_system, version):
    """Manually remove migration from applied list"""
    try:
        migration_system._unmark_migration_applied(version)
        print(f"✅ Removed migration {version} from applied list")
    except Exception as e:
        print(f"❌ Error removing migration {version}: {e}")

def check_consistency(migration_system):
    """Check consistency between files and database records"""
    applied_migrations = set(migration_system._get_applied_migrations())
    available_migrations = {m["version"]: m for m in migration_system._get_available_migrations()}
    
    print("\n🔍 Migration Consistency Check")
    print("=" * 40)
    
    # Check for applied migrations without files
    orphaned = applied_migrations - set(available_migrations.keys())
    if orphaned:
        print(f"\n⚠️ Applied migrations without files ({len(orphaned)}):")
        for version in sorted(orphaned):
            print(f"   {version} - файл удален, но запись в БД осталась")
    
    # Check for files without applied records
    pending = set(available_migrations.keys()) - applied_migrations
    if pending:
        print(f"\n📋 Available migrations not applied ({len(pending)}):")
        for version in sorted(pending):
            migration = available_migrations[version]
            print(f"   {version}: {migration['description']}")
    
    if not orphaned and not pending:
        print("\n✅ All migrations are consistent")
    
    # Recommendations
    if orphaned:
        print(f"\n💡 Рекомендации для orphaned миграций:")
        print(f"   - Удалить записи: python migrate.py unmark <version>")
        print(f"   - Или восстановить файлы миграций")
    
    return orphaned, pending

def main():
    parser = argparse.ArgumentParser(description='Database migration management')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    subparsers.add_parser('status', help='Show migration status')
    
    # Check command
    subparsers.add_parser('check', help='Check consistency between files and database')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Apply migrations')
    migrate_parser.add_argument('version', nargs='?', help='Target version (optional)')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback to version')
    rollback_parser.add_argument('version', help='Target version')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create new migration')
    create_parser.add_argument('description', nargs='?', help='Migration description (optional - triggers interactive mode if not provided)')
    
    # Mark command
    mark_parser = subparsers.add_parser('mark', help='Mark migration as applied')
    mark_parser.add_argument('version', help='Migration version')
    mark_parser.add_argument('--description', help='Migration description', default='Manually marked')
    
    # Unmark command
    unmark_parser = subparsers.add_parser('unmark', help='Remove migration from applied list')
    unmark_parser.add_argument('version', help='Migration version')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        # Initialize migration system
        migration_system = MigrationSystem(DATABASE_URL)
        
        if args.command == 'status':
            migration_system.status()
            
        elif args.command == 'check':
            check_consistency(migration_system)
            
        elif args.command == 'migrate':
            if args.version:
                migration_system.migrate(args.version)
            else:
                migration_system.migrate()
                
        elif args.command == 'rollback':
            migration_system.rollback(args.version)
            
        elif args.command == 'create':
            if args.description:
                # Simple template-based creation
                create_migration_file(args.description)
            else:
                # Interactive creation
                interactive_migration_creator()
        
        elif args.command == 'mark':
            manual_mark_applied(migration_system, args.version, args.description)
            
        elif args.command == 'unmark':
            manual_unmark_applied(migration_system, args.version)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()