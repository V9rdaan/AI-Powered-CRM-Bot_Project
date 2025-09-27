"""
PostgreSQL connection and CRM data queries.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Establish connection using individual DB params
def get_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", ""),
        database=os.getenv("DB_NAME", ""),
        user=os.getenv("DB_USER", "p"),
        password=os.getenv("DB_PASSWORD", ""),
        port=os.getenv("DB_PORT", )
    )

def create_tables():
    """Create necessary tables if they don't exist"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Create lead_table for client-defined stages (matches actual schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lead_table (
                lead_stage VARCHAR(20) NOT NULL,
                description TEXT NOT NULL,
                client_id VARCHAR(20) NOT NULL,
                UNIQUE(client_id, lead_stage)
            )
        """)

        # Create unified crm_data table (user_interest removed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crm_data (
                user_id VARCHAR(255) PRIMARY KEY,
                profile_data JSONB NOT NULL DEFAULT '{}',
                lead_data JSONB DEFAULT '{}',
                lead_stage VARCHAR(50) DEFAULT 'Stage 1',
                conversations JSONB DEFAULT '[]',
                client_id VARCHAR(50) DEFAULT 'client_01',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Remove user_interest column if it exists
        try:
            cursor.execute("""
                ALTER TABLE crm_data DROP COLUMN IF EXISTS user_interest
            """)
        except Exception as e:
            print(f"Warning: Could not drop user_interest column: {e}")

        # Add other columns if they don't exist
        try:
            cursor.execute("""
                ALTER TABLE crm_data 
                ADD COLUMN IF NOT EXISTS client_id VARCHAR(50) DEFAULT 'client_01'
            """)
        except:
            pass
            
        try:
            cursor.execute("""
                ALTER TABLE crm_data 
                ADD COLUMN IF NOT EXISTS lead_stage VARCHAR(50) DEFAULT 'Stage 1'
            """)
        except:
            pass
            
        try:
            cursor.execute("""
                ALTER TABLE crm_data 
                ADD COLUMN IF NOT EXISTS conversations JSONB DEFAULT '[]'
            """)
        except:
            pass

        # Create index on updated_at for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crm_data_updated_at 
            ON crm_data(updated_at)
        """)

        conn.commit()
        print("✅ Database tables created successfully with JSONB user_interest")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# Insert or update profile + lead data into unified crm_data table
def upsert_crm_data(user_id, profile_data, lead_data):
    """Insert or update CRM data (profile + lead) for a user (user_interest is now inactive)"""
    try:
        print(f"UPSERT: user_id={user_id}")  # Debug print
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO crm_data (user_id, profile_data, lead_data, updated_at)
                    VALUES (%s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET profile_data = EXCLUDED.profile_data,
                        lead_data = EXCLUDED.lead_data,
                        updated_at = NOW()
                ''', (user_id, json.dumps(profile_data), json.dumps(lead_data)))
                conn.commit()
                print(f"Successfully upserted CRM data for user: {user_id}")
        return True
    except Exception as e:
        print(f"Error upserting CRM data: {e}")
        return False

# Fetch entire CRM record (profile + lead) for a given user_id
def fetch_crm_data(user_id):
    """Fetch complete CRM record for a user"""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM crm_data WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
                return dict(result) if result else None
    except Exception as e:
        print(f"Error fetching CRM data: {e}")
        return None

def get_user_from_postgres(user_id: str) -> dict:
    """Get user profile from PostgreSQL by user_id (no conversations)"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT profile_data FROM crm_data WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result['profile_data'] is not None:
            profile = dict(result['profile_data'])
            return profile
        return None
        
    except Exception as e:
        print(f"Error getting user from PostgreSQL: {e}")
        return None
    finally:
        if conn:
            conn.close()

def upsert_user_profile(user_id: str, profile_data: dict, lead_stage: str = "Stage 1", conversations: list = None):
    """Insert or update user profile in PostgreSQL (with conversations)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ensure user_id is in profile_data as string
        profile_data["user_id"] = str(user_id)

        # First, check if user exists and get existing lead_data and conversations
        cursor.execute("SELECT lead_data, conversations FROM crm_data WHERE user_id = %s", (str(user_id),))
        existing = cursor.fetchone()
        existing_lead_data = existing[0] if existing else {}
        existing_conversations = existing[1] if existing and len(existing) > 1 else []

        # Use passed conversations if provided, else keep existing
        if conversations is None:
            conversations = existing_conversations

        query = """
        INSERT INTO crm_data (user_id, profile_data, lead_stage, conversations)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET profile_data = EXCLUDED.profile_data,
            lead_stage = EXCLUDED.lead_stage,
            conversations = EXCLUDED.conversations;
        """
        cursor.execute(
            query,
            (user_id, json.dumps(profile_data), lead_stage, json.dumps(conversations))
        )

        conn.commit()
        print(f"Successfully upserted profile for user: {user_id}")

    except Exception as e:
        print(f"Error upserting user profile: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# Lead table operations
def insert_lead_stages(client_id: str, stages: list):
    """Insert predefined lead stages for a client"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for stage_data in stages:
                    cur.execute("""
                        INSERT INTO lead_table (client_id, lead_stage, description)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (client_id, lead_stage) DO UPDATE
                        SET description = EXCLUDED.description
                    """, (client_id, stage_data['stage'], stage_data['description']))
                
                conn.commit()
                print(f"Successfully inserted/updated lead stages for client: {client_id}")
        return True
    except Exception as e:
        print(f"Error inserting lead stages: {e}")
        return False

def get_stage_config(client_id: str, stage_number: int):
    """Fetch stage configuration from lead_table"""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT lead_stage, description 
                    FROM lead_table 
                    WHERE client_id = %s AND lead_stage = %s
                """, (client_id, f"Stage {stage_number}"))
                
                result = cur.fetchone()
                if result:
                    return {
                        'stage': result['lead_stage'],
                        'description': result['description']
                    }
        return None
    except Exception as e:
        print(f"Error fetching stage config: {e}")
        return None

def get_all_stages(client_id: str):
    """Get all lead stages for a client"""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT lead_stage, description 
                    FROM lead_table 
                    WHERE client_id = %s 
                    ORDER BY lead_stage
                """, (client_id,))
                
                results = cur.fetchall()
                return [dict(result) for result in results] if results else []
    except Exception as e:
        print(f"Error fetching all stages: {e}")
        return []

def update_user_stage(user_id: str, new_stage: str, client_id: str = "client_01"):
    """Update user's lead stage in CRM"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE crm_data 
                    SET lead_stage = %s, updated_at = NOW()
                    WHERE user_id = %s
                """, (new_stage, user_id))
                
                if cur.rowcount > 0:
                    conn.commit()
                    print(f"Updated user {user_id} to {new_stage}")
                    return True
                else:
                    print(f"User {user_id} not found for stage update")
                    return False
    except Exception as e:
        print(f"Error updating user stage: {e}")
        return False

# Initialize tables when module is imported

create_tables()
