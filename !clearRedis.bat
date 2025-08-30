@echo off
echo Clearing all Redis databases in container: ai-girlfriend-redis
docker exec -it ai-girlfriend-redis redis-cli FLUSHALL
echo Done!
pause