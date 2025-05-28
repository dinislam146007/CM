#!/usr/bin/env python3
"""
Script to run database migration for strategy fields
"""

import asyncio
import sys
import os
import sqlite3

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def run_migration():
    """Run the database migration to add strategy fields"""
    
    try:
        print("=== Running Database Migration ===\n")
        
        # Check if we're using SQLite (fallback database)
        db_path = 'data/trading_data.db'
        if os.path.exists(db_path):
            print("🔍 Detected SQLite database, running SQLite migration...")
            await migrate_sqlite_strategy_fields(db_path)
        else:
            print("🔍 Attempting PostgreSQL migration...")
            from db.orders import migrate_strategy_fields, init_db
            from db.connect import connect
            
            # First, initialize the database
            print("🔄 Initializing database...")
            await init_db()
            print("✅ Database initialization completed\n")
            
            # Run the migration for strategy fields
            print("🔄 Running migration for strategy fields...")
            await migrate_strategy_fields()
            print("✅ Migration completed successfully\n")
            
            # Verify the migration worked
            print("🔍 Verifying migration...")
            conn = await connect()
            try:
                # Test if we can select the new columns
                await conn.fetchval("SELECT price_action_active FROM orders LIMIT 1")
                print("✅ Strategy fields are now available in the database")
                
                # Check if table has any records
                count = await conn.fetchval("SELECT COUNT(*) FROM orders")
                print(f"📊 Orders table contains {count} records")
                
            except Exception as e:
                print(f"❌ Verification failed: {e}")
            finally:
                await conn.close()
        
        print("\n=== Migration Complete ===")
        print("You can now restart your bot. New orders will include strategy information.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("Please check your database connection and try again.")

async def migrate_sqlite_strategy_fields(db_path):
    """Add strategy fields to SQLite database"""
    
    # Connect to SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if strategy fields already exist
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        
        strategy_fields = [
            ("price_action_active", "BOOLEAN DEFAULT 0"),
            ("price_action_pattern", "TEXT DEFAULT ''"),
            ("cm_active", "BOOLEAN DEFAULT 0"),
            ("moonbot_active", "BOOLEAN DEFAULT 0"),
            ("rsi_active", "BOOLEAN DEFAULT 0"),
            ("divergence_active", "BOOLEAN DEFAULT 0"),
            ("divergence_type", "TEXT DEFAULT ''")
        ]
        
        # Add missing strategy fields
        for field_name, field_definition in strategy_fields:
            if field_name not in columns:
                try:
                    sql = f"ALTER TABLE orders ADD COLUMN {field_name} {field_definition}"
                    cursor.execute(sql)
                    print(f"✅ Added column: {field_name}")
                except Exception as e:
                    print(f"❌ Error adding column {field_name}: {e}")
            else:
                print(f"ℹ️  Column {field_name} already exists")
        
        # Commit changes
        conn.commit()
        
        # Verify the migration
        print("\n🔍 Verifying SQLite migration...")
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        
        missing_fields = []
        for field_name, _ in strategy_fields:
            if field_name not in columns:
                missing_fields.append(field_name)
        
        if missing_fields:
            print(f"❌ Still missing fields: {missing_fields}")
        else:
            print("✅ All strategy fields are now available in the SQLite database")
            
        # Check if table has any records
        cursor.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        print(f"📊 Orders table contains {count} records")
        
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration()) 