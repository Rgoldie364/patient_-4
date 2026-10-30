"""Command-line setup and local web server for PRS Version 1."""

import argparse
from datetime import date
from getpass import getpass
from pathlib import Path
import secrets

from prs.errors import PRSError
from prs.ui.web import create_app


def main():
    parser = argparse.ArgumentParser(description="PRS Version 1 — synthetic data only")
    parser.add_argument("--db", help="SQLite file (default: data/prs_v1.sqlite3)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Initialize persistent storage")
    create = commands.add_parser("create-staff", help="Provision a clinic-approved staff account locally")
    create.add_argument("username")
    create.add_argument("--role", choices=["nurse", "doctor", "viewer"], required=True)
    commands.add_parser("seed-demo", help="Create synthetic records and three demo staff accounts")
    serve = commands.add_parser("serve", help="Run the local demonstration UI")
    serve.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    app = create_app(args.db)
    services = app.extensions["prs"]
    try:
        if args.command == "init-db":
            print("Initialized:", services.database.path)
        elif args.command == "create-staff":
            password = getpass("New password (at least 12 characters): ")
            if password != getpass("Confirm password: "):
                raise ValueError("Passwords do not match.")
            services.auth.provision_staff(args.username, password, args.role)
            print("Staff account created:", args.username)
        elif args.command == "seed-demo":
            demo_password = None
            for role in ("nurse", "doctor", "viewer"):
                username = "demo." + role
                if services.auth.repository.by_username(username):
                    print(username, "already exists; its password was not changed.")
                    continue
                password = secrets.token_urlsafe(15)
                services.auth.provision_staff(username, password, role)
                print(f"Username: {username}  Password: {password}")
                if role == "nurse":
                    demo_password = password
            if demo_password:
                token = services.auth.login("demo.nurse", demo_password)
                patient = services.patients.create(token, name="Taylor Example", date_of_birth="1994-03-12",
                                                  email="taylor@example.com", phone="202-555-0142",
                                                  address="123 Fictional Lane")
                services.visits.add(token, patient.patient_id, date.today().isoformat(),
                                    "Synthetic example: cough and chest congestion for three days.")
                print("Synthetic Patient ID:", patient.patient_id)
                services.auth.logout(token)
            else:
                print("Existing demo data was preserved. Use an existing Patient ID or create a patient in the UI.")
            print("Save the generated passwords locally; they will not be displayed again.")
        else:
            print("PRS Version 1: http://127.0.0.1:" + str(args.port))
            app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True, use_reloader=False)
    except (PRSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
