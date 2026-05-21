#!/usr/bin/env python3

import secrets
import string
import os
from pathlib import Path

def generate_secure_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_database_url(password: str, user: str, host: str, port: int, db: str) -> str:
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"

def main():
    secrets_dir = Path(__file__).parent.parent / "secrets"
    secrets_dir.mkdir(exist_ok=True)

    records_password = generate_secure_password(32)
    audit_password = generate_secure_password(32)
    grafana_password = generate_secure_password(32)

    records_url = generate_database_url(
        records_password, "records_user", "postgres-records", 5432, "records_db"
    )
    audit_url = generate_database_url(
        audit_password, "audit_user", "postgres-audit", 5432, "audit_db"
    )

    secrets_files = {
        "records_db_password.txt": records_password,
        "audit_db_password.txt": audit_password,
        "grafana_admin_password.txt": grafana_password,
        "records_db_password_url.txt": records_url,
        "audit_db_password_url.txt": audit_url,
    }

    for filename, content in secrets_files.items():
        filepath = secrets_dir / filename
        with open(filepath, 'w') as f:
            f.write(content)
        os.chmod(filepath, 0o600)


if __name__ == "__main__":
    main()