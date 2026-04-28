#!/usr/bin/env python3
"""
User Management Script for Secrets Scanner
Interactive console-based user management
"""

import os
import sys
from pathlib import Path
from getpass import getpass
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from dotenv import load_dotenv
from passlib.context import CryptContext

# Load environment variables
load_dotenv()

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models
try:
    from models import UserBase, User
except ImportError:
    print("Error: Cannot import UserBase model. Make sure models.py is in the project root.")
    sys.exit(1)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

class UserManager:
    def __init__(self):
        # Create Auth directory
        auth_dir = Path("Auth")
        auth_dir.mkdir(exist_ok=True)
        
        # Get user database URL from environment
        USERS_DATABASE_URL = os.getenv("USERS_DATABASE_URL", "sqlite:///./Auth/users.db")
        
        self.engine = create_engine(USERS_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in USERS_DATABASE_URL else {})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = SessionLocal()
        
        # Ensure tables exist
        UserBase.metadata.create_all(bind=self.engine)
        with self.engine.begin() as conn:
            columns = {column["name"] for column in inspect(self.engine).get_columns("users")}
            if "role" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user' NOT NULL"))
            conn.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
            conn.execute(text("UPDATE users SET role = 'admin' WHERE username = 'admin'"))

    def add_user(self):
        """Add a new user"""
        print("\n📝 Add New User")
        print("-" * 30)
        
        username = input("Username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            return
        
        password = getpass("Password: ")
        if len(password) < 4:
            print("❌ Password must be at least 4 characters long")
            return
        
        role = input("Role (user/admin) [user]: ").strip().lower() or "user"
        if username == "admin":
            role = "admin"
        elif role not in {"user", "admin"}:
            print("❌ Role must be 'user' or 'admin'")
            return
            
        confirm_password = getpass("Confirm password: ")
        if password != confirm_password:
            print("❌ Passwords do not match")
            return
        
        try:
            hashed_password = get_password_hash(password)
            user = User(username=username, password_hash=hashed_password, role=role)
            self.db.add(user)
            self.db.commit()
            print(f"✅ User '{username}' created successfully")
        except IntegrityError:
            self.db.rollback()
            print(f"❌ Error: User '{username}' already exists")
        except Exception as e:
            self.db.rollback()
            print(f"❌ Error creating user: {e}")

    def list_users(self):
        """List all users"""
        print("\n📋 Users List")
        print("-" * 60)
        
        try:
            users = self.db.query(User).all()
            if not users:
                print("No users found")
                return
            
            for user in users:
                role = getattr(user, "role", "user") or "user"
                print(f"ID: {user.id:3} | Username: {user.username:20} | Role: {role:5} | Created: {user.created_at.strftime('%Y-%m-%d %H:%M')}")
            print("-" * 60)
            print(f"Total users: {len(users)}")
        except Exception as e:
            print(f"❌ Error listing users: {e}")

    def update_password(self):
        """Update user password"""
        print("\n🔑 Update Password")
        print("-" * 30)
        
        username = input("Username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            return
        
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User '{username}' not found")
            return
        
        new_password = getpass("New password: ")
        if len(new_password) < 4:
            print("❌ Password must be at least 4 characters long")
            return
            
        confirm_password = getpass("Confirm new password: ")
        if new_password != confirm_password:
            print("❌ Passwords do not match")
            return
        
        try:
            user.password_hash = get_password_hash(new_password)
            self.db.commit()
            print(f"✅ Password updated for user '{username}'")
        except Exception as e:
            self.db.rollback()
            print(f"❌ Error updating password: {e}")

    def delete_user(self):
        """Delete a user"""
        print("\n🗑️  Delete User")
        print("-" * 30)
        
        username = input("Username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            return
        
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User '{username}' not found")
            return
        
        # Prevent deleting the last user
        user_count = self.db.query(User).count()
        if user_count <= 1:
            print("❌ Cannot delete the last user")
            return
        
        confirm = input(f"Are you sure you want to delete user '{username}'? (y/N): ")
        if confirm.lower() != 'y':
            print("Operation cancelled")
            return
        
        try:
            self.db.delete(user)
            self.db.commit()
            print(f"✅ User '{username}' deleted successfully")
        except Exception as e:
            self.db.rollback()
            print(f"❌ Error deleting user: {e}")

    def verify_user(self):
        """Verify user credentials"""
        print("\n🔍 Verify User")
        print("-" * 30)
        
        username = input("Username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            return
        
        password = getpass("Password: ")
        
        try:
            user = self.db.query(User).filter(User.username == username).first()
            if user and verify_password(password, user.password_hash):
                print(f"✅ Credentials valid for user '{username}'")
            else:
                print(f"❌ Invalid credentials for user '{username}'")
        except Exception as e:
            print(f"❌ Error verifying user: {e}")

    def show_menu(self):
        """Display main menu"""
        print("\n" + "="*50)
        print("🔐 Secrets Scanner - User Management")
        print("="*50)
        print("1. Add User")
        print("2. List Users")
        print("3. Update Password")
        print("4. Delete User")
        print("5. Verify User")
        print("6. Exit")
        print("-" * 50)

    def run(self):
        """Main interactive loop"""
        while True:
            self.show_menu()
            choice = input("Select option (1-6): ").strip()
            
            if choice == "1":
                self.add_user()
            elif choice == "2":
                self.list_users()
            elif choice == "3":
                self.update_password()
            elif choice == "4":
                self.delete_user()
            elif choice == "5":
                self.verify_user()
            elif choice == "6":
                print("\n👋 Goodbye!")
                break
            else:
                print("❌ Invalid option. Please select 1-6.")
            
            input("\nPress Enter to continue...")

    def close(self):
        """Close database connection"""
        self.db.close()

def main():
    manager = UserManager()
    try:
        manager.run()
    finally:
        manager.close()

if __name__ == "__main__":
    main()