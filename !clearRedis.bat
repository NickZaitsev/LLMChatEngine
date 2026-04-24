@echo off
echo Clearing all Redis databases in container: llm-chat-engine-redis
docker exec -it llm-chat-engine-redis redis-cli FLUSHALL
echo Done!
pause
