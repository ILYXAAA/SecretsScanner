import os
import shutil
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from config import DATABASE_URL, BACKUP_DIR, BACKUP_RETENTION_DAYS, BACKUP_INTERVAL_HOURS

# Setup logging for backups
backup_logger = logging.getLogger("backup")

def create_database_backup():
    """Create a database backup with timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"secrets_scanner_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Get the database file path
        if "sqlite" in DATABASE_URL:
            db_file = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            if os.path.exists(db_file):
                shutil.copy2(db_file, backup_path)
                backup_logger.info(f"Database backup created: {backup_path}")
                return backup_path
            else:
                backup_logger.error(f"Database file not found: {db_file}")
                return None
        else:
            # For non-SQLite databases needs implement pg_dump, mysqldump, etc.
            backup_logger.warning("Backup only implemented for SQLite databases")
            return None
            
    except Exception as e:
        backup_logger.error(f"Backup failed: {str(e)}")
        return None

def cleanup_old_backups():
    """Remove backups older than retention period"""
    try:
        cutoff_date = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        backup_dir = Path(BACKUP_DIR)
        
        removed_count = 0
        for backup_file in backup_dir.glob("secrets_scanner_backup_*.db"):
            if backup_file.stat().st_mtime < cutoff_date.timestamp():
                backup_file.unlink()
                removed_count += 1
                backup_logger.info(f"Removed old backup: {backup_file.name}")
        
        if removed_count > 0:
            backup_logger.info(f"Cleaned up {removed_count} old backups")
            
    except Exception as e:
        backup_logger.error(f"Backup cleanup failed: {str(e)}")

async def backup_scheduler():
   """Background task to handle regular backups"""
   # Create initial backup only if none exist
   backup_dir = Path(BACKUP_DIR)
   existing_backups = list(backup_dir.glob("secrets_scanner_backup_*.db"))
   
   if not existing_backups:
       backup_logger.info("No existing backups found, creating initial backup")
       backup_path = create_database_backup()
       if backup_path:
           cleanup_old_backups()
   else:
       backup_logger.info(f"Found {len(existing_backups)} existing backups, skipping initial backup")
   
   while True:
       try:
           # Wait for backup interval
           await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
           
           # Create backup after waiting
           backup_path = create_database_backup()
           
           if backup_path:
               cleanup_old_backups()
           
       except Exception as e:
           backup_logger.error(f"Backup scheduler error: {str(e)}")
           # Wait 1 hour before retrying on error
           await asyncio.sleep(3600)

def get_backup_status():
    """Get backup configuration and status"""
    try:
        backup_dir = Path(BACKUP_DIR)
        all_backups = []
        
        if backup_dir.exists():
            for backup_file in sorted(backup_dir.glob("secrets_scanner_backup_*.db"), 
                                    key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                all_backups.append({
                    "filename": backup_file.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        return {
            "status": "success",
            "config": {
                "backup_dir": str(BACKUP_DIR),
                "retention_days": BACKUP_RETENTION_DAYS,
                "interval_hours": BACKUP_INTERVAL_HOURS
            },
            "backups": all_backups[:20],  # Show only first 20
            "total_backups": len(all_backups),  # Total count
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e),
            "config": {
                "backup_dir": str(BACKUP_DIR),
                "retention_days": BACKUP_RETENTION_DAYS,
                "interval_hours": BACKUP_INTERVAL_HOURS
            },
            "backups": [],
            "total_backups": 0,
            "timestamp": datetime.now().isoformat()
        }

def list_backups():
    """List available backups"""
    try:
        backup_dir = Path(BACKUP_DIR)
        backups = []
        
        for backup_file in sorted(backup_dir.glob("secrets_scanner_backup_*.db"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return {"status": "success", "backups": backups}
    except Exception as e:
        return {"status": "error", "message": str(e)}