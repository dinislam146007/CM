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
            query = self._replace_placeholders(query)
            
            # Replace SERIAL PRIMARY KEY with INTEGER PRIMARY KEY
            query = query.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY')
            
            # Replace BIGINT with INTEGER for SQLite
            query = query.replace('BIGINT', 'INTEGER')
            
            # Execute the query
            return self.cursor.execute(query, args)
        
        async def fetch(self, query, *args):
            await self.execute(query, *args)
            rows = self.cursor.fetchall()
            if rows:
                columns = [description[0] for description in self.cursor.description]
                return [dict(zip(columns, row)) for row in rows]
            return []
        
        async def fetchrow(self, query, *args):
            await self.execute(query, *args)
            row = self.cursor.fetchone()
            if row:
                columns = [description[0] for description in self.cursor.description]
                return dict(zip(columns, row))
            return None
        
        async def fetchval(self, query, *args):
            """Fetch a single value from the first row of the result"""
            await self.execute(query, *args)
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        
        def _replace_placeholders(self, query):
            """Replace PostgreSQL-style placeholders with SQLite-style"""
            # Replace $1, $2, etc. with ? for SQLite
            import re
            # Find all $n placeholders and replace them with ?
            placeholders = re.findall(r'\$\d+', query)
            for placeholder in sorted(set(placeholders), key=lambda x: int(x[1:]), reverse=True):
                query = query.replace(placeholder, '?')
            return query
        
        async def close(self):
            self.conn.commit()
            # Don't actually close to reuse the connection
    
    return AsyncpgSQLiteWrapper(conn)
