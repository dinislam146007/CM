import asyncpg
from config import config
import logging


async def connect() -> asyncpg.Connection:
    """Establish a connection to the PostgreSQL database, creating it if it doesn't exist."""
    try:
        # First try to connect to the specified database
        return await asyncpg.connect(
            host="localhost",
            port=5432,
            user=config.db_user,
            password=config.db_password,
            database="trading_db"
        )
    except asyncpg.InvalidCatalogNameError:
        # If the database doesn't exist, connect to the default postgres database and create it
        try:
            # Connect to default postgres database
            system_conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                user=config.db_user,
                password=config.db_password,
                database="postgres"  # Default database that always exists
            )
            
            # Set autocommit mode to create database
            await system_conn.execute('CREATE DATABASE trading_db;')
            await system_conn.close()
            
            # Now connect to the newly created database
            return await asyncpg.connect(
                host="localhost",
                port=5432,
                user=config.db_user,
                password=config.db_password,
                database="trading_db"
            )
        except Exception as e:
            logging.error(f"Error creating database: {e}")
            # As a fallback, use SQLite
            return await _connect_sqlite()
    except Exception as e:
        logging.error(f"Failed to connect to PostgreSQL: {e}")
        # Use SQLite as a fallback
        return await _connect_sqlite()

async def _connect_sqlite():
    """Fallback to SQLite database if PostgreSQL is not available."""
    import sqlite3
    import os
    
    # Create directory for database if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Create SQLite database file
    conn = sqlite3.connect('data/trading_data.db')
    logging.info("Connected to SQLite database as fallback")
    
    # Create a wrapper for the SQLite connection that mimics asyncpg's interface
    class AsyncpgSQLiteWrapper:
        def __init__(self, conn):
            self.conn = conn
            self.cursor = conn.cursor()
        
        async def execute(self, query, *args):
            # Replace $1, $2, etc. with ? for SQLite
            query = query.replace('$1', '?').replace('$2', '?').replace('$3', '?')
            query = query.replace('$4', '?').replace('$5', '?').replace('$6', '?')
            
            # Replace SERIAL PRIMARY KEY with INTEGER PRIMARY KEY
            query = query.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY')
            
            # Replace BIGINT with INTEGER for SQLite
            query = query.replace('BIGINT', 'INTEGER')
            
            # Execute the query
            return self.cursor.execute(query, args)
        
        async def fetch(self, query, *args):
            await self.execute(query, *args)
            return self.cursor.fetchall()
        
        async def fetchrow(self, query, *args):
            await self.execute(query, *args)
            row = self.cursor.fetchone()
            if row:
                columns = [description[0] for description in self.cursor.description]
                return dict(zip(columns, row))
            return None
        
        async def close(self):
            self.conn.commit()
            # Don't actually close to reuse the connection
    
    return AsyncpgSQLiteWrapper(conn)
