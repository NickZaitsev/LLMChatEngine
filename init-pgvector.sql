-- Initialize pgvector extension for PostgreSQL
-- This script runs when the PostgreSQL container starts for the first time

-- Create the pgvector extension if available
-- Note: This will fail silently if pgvector is not installed, but the app will still work
DO $$
BEGIN
    -- Try to create pgvector extension
    BEGIN
        CREATE EXTENSION IF NOT EXISTS vector;
        RAISE NOTICE 'pgvector extension created successfully';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'pgvector extension not available, using fallback storage';
    END;
END $$;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE ai_bot TO ai_bot;