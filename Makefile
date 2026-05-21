 .PHONY: init clean-init start stop clean logs build restart help

init:
	@echo "Generating Docker secrets with secure random passwords..."
	@python3 scripts/generate_secrets.py
	@echo "Docker secrets generated successfully!"	
clean-init:
	rm -rf secrets/
	@$(MAKE) init
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

