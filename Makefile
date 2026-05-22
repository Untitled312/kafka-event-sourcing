 .PHONY: start stop clean logs build restart help

start:
	docker compose up -d
	@echo "All services started!"
stop:
	docker compose down
	@echo "All services stopped!"
clean:
	docker compose down -v --remove-orphans
	rm -rf secrets/
	@echo "Cleanup completed!"
status:
	docker compose ps

