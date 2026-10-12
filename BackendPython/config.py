import os
from dotenv import load_dotenv

# Load .env file from BackendPython directory or root
load_dotenv()

API_KEY = os.getenv("API_KEY", "12345")

# Check for unified database connection string (Supabase / Neon / Render / Railway)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required. Only Supabase connection is supported.")

# asyncpg expects 'postgresql://', replace 'postgres://' if present
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATABASE_URI = DATABASE_URL

