@echo off
echo "Listing PostgreSQL users..."
docker exec -i ai-girlfriend-postgres psql -U ai_bot -d ai_bot -c "SELECT id, username FROM users;"