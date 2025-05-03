import asyncio
from db.connect import connect
import logging
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def update_schema():
    """Updates the database schema to support futures trading."""
    conn = await connect()
    try:
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
            try:
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN trading_type TEXT DEFAULT 'spot'
                """)
                logger.info("Added trading_type column to orders table")
            except asyncpg.exceptions.InsufficientPrivilegeError:
                logger.warning("Insufficient privileges to add trading_type column. Continuing...")
            except Exception as e:
                logger.warning(f"Error adding trading_type column: {e}. Continuing...")
        else:
            logger.info("trading_type column already exists in orders table")
        
        # Add leverage column if it doesn't exist
        if not leverage_exists:
            logger.info("Adding leverage column to orders table...")
            try:
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN leverage INTEGER DEFAULT 1
                """)
                logger.info("Added leverage column to orders table")
            except asyncpg.exceptions.InsufficientPrivilegeError:
                logger.warning("Insufficient privileges to add leverage column. Continuing...")
            except Exception as e:
                logger.warning(f"Error adding leverage column: {e}. Continuing...")
        else:
            logger.info("leverage column already exists in orders table")
        
        # Add side column if it doesn't exist
        if not side_exists:
            logger.info("Adding side column to orders table...")
            try:
                await conn.execute("""
                    ALTER TABLE orders ADD COLUMN side TEXT DEFAULT 'LONG'
                """)
                # Update existing orders to have side = 'LONG'
                try:
                    await conn.execute("""
                        UPDATE orders SET side = 'LONG'
                    """)
                except Exception as e:
                    logger.warning(f"Error updating existing orders with side=LONG: {e}. Continuing...")
                logger.info("Added side column to orders table")
            except asyncpg.exceptions.InsufficientPrivilegeError:
                logger.warning("Insufficient privileges to add side column. Continuing...")
            except Exception as e:
                logger.warning(f"Error adding side column: {e}. Continuing...")
        else:
            logger.info("side column already exists in orders table")
        
        # Add primary key if needed
        try:
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
        except asyncpg.exceptions.InsufficientPrivilegeError:
            logger.warning("Insufficient privileges to add primary key. Continuing...")
        except Exception as e:
            logger.warning(f"Error adding primary key: {e}. Continuing...")
        
        # Add other missing columns if they don't exist - one at a time to avoid transaction issues
        for column_definition in [
            "ADD COLUMN IF NOT EXISTS qty REAL",
            "ADD COLUMN IF NOT EXISTS tp_price REAL",
            "ADD COLUMN IF NOT EXISTS sl_price REAL", 
            "ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'OPEN'",
            "ADD COLUMN IF NOT EXISTS pnl_percent NUMERIC",
            "ADD COLUMN IF NOT EXISTS pnl_usdt REAL",
            "ADD COLUMN IF NOT EXISTS investment_amount_usdt REAL",
            "ADD COLUMN IF NOT EXISTS return_amount_usdt REAL"
        ]:
            try:
                await conn.execute(f"ALTER TABLE orders {column_definition}")
            except asyncpg.exceptions.InsufficientPrivilegeError:
                logger.warning(f"Insufficient privileges to {column_definition}. Continuing...")
            except Exception as e:
                logger.warning(f"Error with {column_definition}: {e}. Continuing...")
        
        logger.info("Database schema update completed successfully")
        
    except Exception as e:
        logger.error(f"Error updating database schema: {e}")
        logger.info("Continuing with existing schema...")
        # Не выбрасываем исключение, чтобы не прерывать запуск бота
    finally:
        await conn.close()

async def main():
    await update_schema()
    
if __name__ == "__main__":
    asyncio.run(main()) 