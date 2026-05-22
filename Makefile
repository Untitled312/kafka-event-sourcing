.PHONY: init secrets up down restart logs health test verify clean setup check

check:
	@command -v docker >/dev/null 2>&1 || { echo "❌ docker required"; exit 1; }
	@command -v openssl >/dev/null 2>&1 || { echo "❌ openssl required"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "❌ curl required"; exit 1; }
	@command -v python3 >/dev/null 2>&1 || { echo "❌ python3 required"; exit 1; }
	@echo "✅ All dependencies found."

init: check
	@mkdir -p secrets prometheus loki postgres/init
	@$(MAKE) secrets FORCE=0
	@$(MAKE) _gen_env
	@echo "✅ Project initialized. Run 'make up' to start services."

secrets:
	@mkdir -p secrets
	@if [ "$(FORCE)" != "1" ] && [ -f secrets/db_pass.txt ]; then \
		exit 0; \
	fi
	@echo "🔑 Generating cryptographically secure secrets..."
	@openssl rand -base64 32 | tr -d '\n' > secrets/db_pass.txt
	@openssl rand -base64 48 | tr -d '\n' > secrets/jwt_secret.txt
	@openssl rand -base64 32 | tr -d '\n' > secrets/kafka_sasl_pass.txt
	@chmod 600 secrets/*.txt
	@echo "✅ Secrets stored in secrets/ (DEV ONLY - replace in prod)"

kafka-topics:
	@echo "🔧 Creating Kafka topics..."
	@docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
		--bootstrap-server localhost:9092 \
		--create --topic audit_events --partitions 3 --replication-factor 1 \
		--if-not-exists >/dev/null 2>&1 || true
	@docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
		--bootstrap-server localhost:9092 \
		--create --topic audit_dlq --partitions 1 --replication-factor 1 \
		--if-not-exists >/dev/null 2>&1 || true

_gen_env:
	@echo "📝 Generating .env from secrets..."
	@DB_PASS=$$(cat secrets/db_pass.txt); \
	echo "DB_PASS=$$DB_PASS" > .env; \
	echo "DATABASE_URL=postgresql+asyncpg://audit_rw:$$DB_PASS@postgres:5432/audit_db" >> .env; \
	echo "KAFKA_BOOTSTRAP_SERVERS=kafka:9092" >> .env; \
	echo "JWT_SECRET=$$(cat secrets/jwt_secret.txt)" >> .env
	@chmod 600 .env

up: check
	@echo "🚀 Starting Cyberimmune Audit System..."
	@docker compose up -d --build --wait
	@echo "✅ All services are healthy and ready!"

down:
	@docker compose down

restart: down up 

logs:
	@docker compose logs -f

health:
	@curl -sf http://localhost:8000/health > /dev/null && echo "✅ API: Healthy" || echo "❌ API: Unhealthy"
	@curl -sf http://localhost:9090/-/healthy > /dev/null && echo "✅ Prometheus: Healthy" || echo "❌ Prometheus: Unhealthy"
	@curl -sf http://localhost:3100/ready > /dev/null && echo "✅ Loki: Healthy" || echo "❌ Loki: Unhealthy"

test:
	@TRACE=$$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())"); \
	curl -sf -X POST http://localhost:8000/audit \
		-H "X-Trace-ID: $$TRACE" \
		-H "Content-Type: application/json" \
		-d '{"entity_type":"user","action":"LOGIN","payload":{"user_id":42,"ip":"192.168.1.10"}}' | python3 -m json.tool || echo "❌ Request failed"
	@echo ""

verify:
	@echo "🔍 Checking system state..."
	@curl -sf http://localhost:8000/health | python3 -m json.tool
	@echo "💡 Background verifier runs every 5m. Monitor Grafana for 'chain_integrity_breach' alerts."

clean:
	@read -p "⚠️  This will destroy ALL data, volumes, and secrets. Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker compose down -v --remove-orphans
	@rm -rf secrets .env
	@echo "🧹 Project cleaned."

setup: init up kafka-topics