import asyncio
from db.connect import connect
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def update_schema():
    """Updates the database schema to support futures trading."""
    conn = await connect()
    try:
        # Start a transaction
        async with conn.transaction():
            logger.info("Starting database schema update for futures trading support...")
            
            # Check if trading_type column exists in orders table
            trading_type_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'orders' AND column_name = 'trading_type'
                )
            """)
            
            # Check if leverage column exists in orders table
            leverage_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'orders' AND column_name = 'leverage'
                )
            """)
            
            # Check if side column exists in orders table
            side_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'orders' AND column_name = 'side'
                )
            """)
            
            # Add trading_type column if it doesn't exist
            if not trading_type_exists:
                logger.info("Adding trading_type column to orders table...")
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN trading_type TEXT DEFAULT 'spot'
                """)
                logger.info("Added trading_type column to orders table")
            else:
                logger.info("trading_type column already exists in orders table")
            
            # Add leverage column if it doesn't exist
            if not leverage_exists:
                logger.info("Adding leverage column to orders table...")
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN leverage INTEGER DEFAULT 1
                """)
                logger.info("Added leverage column to orders table")
            else:
                logger.info("leverage column already exists in orders table")
            
            # Add side column if it doesn't exist
            if not side_exists:
                logger.info("Adding side column to orders table...")
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN side TEXT DEFAULT 'LONG'
                """)
                # Update existing orders to have side = 'LONG'
                await conn.execute("""
                    UPDATE orders SET side = 'LONG'
                """)
                logger.info("Added side column to orders table")
            else:
                logger.info("side column already exists in orders table")
            
            # Add primary key if needed
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'orders' AND constraint_type = 'PRIMARY KEY'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;
                    END IF;
                END
                $$;
            """)
            
            # Add other missing columns if they don't exist
            await conn.execute("""
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS qty REAL;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS tp_price REAL;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS sl_price REAL;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'OPEN';
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS pnl_percent NUMERIC;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS pnl_usdt REAL;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS investment_amount_usdt REAL;
                ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_amount_usdt REAL;
            """)
            
            # Add default data directory for user settings if it doesn't exist
            await conn.execute("SELECT 1") # Dummy query to keep connection alive
            
            logger.info("Database schema update completed successfully")
            
    except Exception as e:
        logger.error(f"Error updating database schema: {e}")
        raise
    finally:
        await conn.close()

async def main():
    await update_schema()
    
if __name__ == "__main__":
    asyncio.run(main()) 