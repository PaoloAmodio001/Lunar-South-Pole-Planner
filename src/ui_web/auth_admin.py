# Last updated: 2026-11-15
"""Gestione degli utenti della sezione MISSION PLANNERS (da terminale).

Uso:
    python src/ui_web/auth_admin.py add-user <nome>      # aggiunge un utente (solo se esiste già un account)
    python src/ui_web/auth_admin.py passwd <nome>        # cambia password e revoca le sessioni
    python src/ui_web/auth_admin.py remove-user <nome>   # elimina l'utente e le sue sessioni
    python src/ui_web/auth_admin.py list                 # elenca i nomi utente
    python src/ui_web/auth_admin.py revoke <nome>        # chiude tutte le sessioni dell'utente
    python src/ui_web/auth_admin.py where                # mostra dove sono salvati utenti e sessioni

La password non si passa mai come argomento (resterebbe nella cronologia della
shell): viene letta con getpass. Per installazioni non interattive si può usare
``--password-stdin`` (una riga su standard input).
Il primo account (amministratore) si crea esclusivamente dalla pagina web
MISSION PLANNERS, che lo propone finché l'archivio utenti è vuoto.
Archivio: $LUNAR_AUTH_DIR oppure ~/.config/lunar-mission-control/ (fuori dal repository).
"""
import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ui_web.auth import AuthManager, UserStore, MIN_PASSWORD_LENGTH  # noqa: E402


def _read_password(args, username):
    if args.password_stdin:
        line = sys.stdin.readline()
        return line.rstrip("\r\n")
    first = getpass.getpass(f"Nuova password per {username} (min. {MIN_PASSWORD_LENGTH} caratteri): ")
    second = getpass.getpass("Ripeti la password: ")
    if first != second:
        raise ValueError("Le due password non coincidono.")
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description="Utenti della sezione MISSION PLANNERS.")
    parser.add_argument("command", choices=["add-user", "passwd", "remove-user", "list",
                                            "revoke", "where"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--password-stdin", action="store_true",
                        help="Legge la password da standard input invece che dal terminale.")
    args = parser.parse_args(argv)

    store = UserStore()
    try:
        if args.command == "where":
            print(f"Utenti:   {store.path}")
            print(f"Sessioni: {store.directory / 'sessions.json'}")
            return 0
        if args.command == "list":
            users = store.list_users()
            print("\n".join(users) if users else "Nessun utente configurato.")
            return 0
        if not args.username:
            parser.error("Specificare il nome utente.")
        if args.command == "add-user":
            if not store.has_users():
                print("[ERRORE] Nessun account configurato: il primo account amministratore si crea "
                      "dalla pagina MISSION PLANNERS nel browser (avvia ./start.sh).", file=sys.stderr)
                return 1
            store.set_password(args.username, _read_password(args, args.username), create=True)
            print(f"Utente {args.username!r} creato in {store.path} (hash scrypt).")
        elif args.command == "passwd":
            store.set_password(args.username, _read_password(args, args.username), create=False)
            revoked = AuthManager(store.directory).revoke_user(args.username)
            print(f"Password aggiornata. Sessioni revocate: {revoked} "
                  "(anche un server già avviato le considera scadute alla richiesta successiva).")
        elif args.command == "remove-user":
            if not store.remove(args.username):
                print(f"L'utente {args.username!r} non esiste.", file=sys.stderr)
                return 1
            AuthManager(store.directory).revoke_user(args.username)
            print(f"Utente {args.username!r} rimosso; le sue sessioni non sono più valide.")
        elif args.command == "revoke":
            revoked = AuthManager(store.directory).revoke_user(args.username)
            print(f"Sessioni revocate: {revoked} (un server già avviato ricarica l'archivio "
                  "delle sessioni alla richiesta successiva).")
        return 0
    except ValueError as exc:
        print(f"[ERRORE] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
