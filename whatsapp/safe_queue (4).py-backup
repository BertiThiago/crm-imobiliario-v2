import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "crm.db"

_lock = threading.RLock()


def connect():
    c = sqlite3.connect(str(DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def _ensure_column(c, table, column, definition):
    columns = {
        row["name"]
        for row in c.execute(f"PRAGMA table_info({table})").fetchall()
    }

    if column not in columns:
        c.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db():
    with _lock:
        c = connect()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts(
                phone TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                opt_in INTEGER NOT NULL DEFAULT 0,
                conversation_active INTEGER NOT NULL DEFAULT 0,
                last_incoming_at TEXT,
                last_outgoing_at TEXT,
                total_incoming INTEGER NOT NULL DEFAULT 0,
                total_outgoing INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                opt_in_source TEXT NOT NULL DEFAULT '',
                opt_in_at TEXT,
                opt_out INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS queue(
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                started_at TEXT,
                sent_at TEXT,
                error TEXT DEFAULT '',
                evolution_message_id TEXT,
                delivery_status TEXT,
                delivered_at TEXT,
                read_at TEXT,
                send_mode TEXT NOT NULL DEFAULT 'service',
                media_path TEXT,
                media_name TEXT,
                media_type TEXT,
                media_mimetype TEXT,
                media_caption TEXT
            )
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                type TEXT NOT NULL,
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )

        # Existing databases may predate some of these columns.
        _ensure_column(c, "contacts", "opt_in_source", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(c, "contacts", "opt_in_at", "TEXT")
        _ensure_column(c, "contacts", "opt_out", "INTEGER NOT NULL DEFAULT 0")

        _ensure_column(c, "queue", "evolution_message_id", "TEXT")
        _ensure_column(c, "queue", "delivery_status", "TEXT")
        _ensure_column(c, "queue", "delivered_at", "TEXT")
        _ensure_column(c, "queue", "read_at", "TEXT")
        _ensure_column(c, "queue", "send_mode", "TEXT NOT NULL DEFAULT 'service'")
        _ensure_column(c, "queue", "media_path", "TEXT")
        _ensure_column(c, "queue", "media_name", "TEXT")
        _ensure_column(c, "queue", "media_type", "TEXT")
        _ensure_column(c, "queue", "media_mimetype", "TEXT")
        _ensure_column(c, "queue", "media_caption", "TEXT")

        c.commit()
        c.close()


def event(c, phone, typ, detail=""):
    c.execute(
        """
        INSERT INTO events(
            id,
            phone,
            type,
            detail,
            created_at
        )
        VALUES(?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            str(phone),
            str(typ),
            str(detail or ""),
            iso(now()),
        ),
    )


def expire_inactive():
    """
    Encerra automaticamente conversas de serviço que ultrapassaram
    a janela de 24 horas desde a última mensagem recebida.
    """
    with _lock:
        c = connect()

        cutoff = now() - timedelta(hours=24)

        rows = c.execute(
            """
            SELECT phone, last_incoming_at
            FROM contacts
            WHERE conversation_active=1
              AND last_incoming_at IS NOT NULL
            """
        ).fetchall()

        for row in rows:
            try:
                last_incoming = datetime.fromisoformat(
                    row["last_incoming_at"]
                )

                if last_incoming.tzinfo is None:
                    last_incoming = last_incoming.replace(
                        tzinfo=timezone.utc
                    )

                if last_incoming < cutoff:
                    c.execute(
                        """
                        UPDATE contacts
                        SET
                            conversation_active=0,
                            updated_at=?
                        WHERE phone=?
                        """,
                        (
                            iso(now()),
                            row["phone"],
                        ),
                    )

                    event(
                        c,
                        row["phone"],
                        "conversation_expired",
                        "Janela de 24h expirada",
                    )

            except Exception:
                # Uma data inválida não deve derrubar o worker inteiro.
                continue

        c.commit()
        c.close()


def upsert_contact(
    phone,
    name="",
    opt_in=False,
    opt_in_source="",
    opt_in_at=None,
    opt_out=None,
):
    """
    Cria ou atualiza um contato.

    Permite registrar opt-in manual, por exemplo quando o
    consentimento foi obtido por ligação, presencialmente ou
    por outro canal externo ao WhatsApp.

    Retorna o contato atualizado.
    """

    phone = str(phone).strip()
    name = str(name or "").strip()
    opt_in_source = str(opt_in_source or "").strip()

    if not phone:
        raise ValueError("phone obrigatório")

    if opt_in_at is None and bool(opt_in):
        opt_in_at = iso(now())

    with _lock:
        c = connect()
        t = iso(now())

        c.execute(
            """
            INSERT INTO contacts(
                phone,
                name,
                opt_in,
                opt_in_source,
                opt_in_at,
                opt_out,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?)

            ON CONFLICT(phone)
            DO UPDATE SET

                name=CASE
                    WHEN excluded.name <> ''
                    THEN excluded.name
                    ELSE contacts.name
                END,

                opt_in=excluded.opt_in,

                opt_in_source=CASE
                    WHEN excluded.opt_in_source <> ''
                    THEN excluded.opt_in_source
                    ELSE contacts.opt_in_source
                END,

                opt_in_at=CASE
                    WHEN excluded.opt_in = 1
                    THEN COALESCE(
                        excluded.opt_in_at,
                        contacts.opt_in_at,
                        excluded.updated_at
                    )
                    ELSE contacts.opt_in_at
                END,

                opt_out=CASE
                    WHEN ? IS NOT NULL
                    THEN ?
                    ELSE contacts.opt_out
                END,

                updated_at=excluded.updated_at
            """,
            (
                phone,
                name,
                int(bool(opt_in)),
                opt_in_source,
                opt_in_at,
                0 if opt_out is None else int(bool(opt_out)),
                t,
                opt_out,
                0 if opt_out is None else int(bool(opt_out)),
            ),
        )

        if bool(opt_in):
            event(
                c,
                phone,
                "opt_in",
                (
                    f"Opt-in registrado. "
                    f"Origem: {opt_in_source or 'não informada'}"
                ),
            )

        if opt_out is True:
            event(
                c,
                phone,
                "opt_out",
                "Opt-out registrado manualmente",
            )

        c.commit()

        row = c.execute(
            """
            SELECT *
            FROM contacts
            WHERE phone=?
            """,
            (phone,),
        ).fetchone()

        result = dict(row) if row else None

        c.close()

        return result


def register_incoming(phone, name="", detail=""):
    """
    Registra uma mensagem recebida e abre/renova a conversa de serviço.
    """

    phone = str(phone).strip()

    if not phone:
        raise ValueError("phone obrigatório")

    t = iso(now())

    with _lock:
        c = connect()

        c.execute(
            """
            INSERT INTO contacts(
                phone,
                name,
                conversation_active,
                last_incoming_at,
                total_incoming,
                updated_at
            )
            VALUES(?,?,?,?,?,?)

            ON CONFLICT(phone)
            DO UPDATE SET

                name=CASE
                    WHEN excluded.name <> ''
                    THEN excluded.name
                    ELSE contacts.name
                END,

                conversation_active=1,
                last_incoming_at=excluded.last_incoming_at,
                total_incoming=contacts.total_incoming + 1,
                updated_at=excluded.updated_at
            """,
            (
                phone,
                str(name or ""),
                1,
                t,
                1,
                t,
            ),
        )

        event(
            c,
            phone,
            "incoming",
            detail or "Mensagem recebida",
        )

        c.commit()
        c.close()


def enqueue(
    phone,
    message,
    require_active=True,
    send_mode="service",
    media_path=None,
    media_name=None,
    media_type=None,
    media_mimetype=None,
    media_caption=None,
):
    """
    Coloca uma mensagem na fila somente se as regras de segurança
    forem atendidas.

    service:
        exige opt-in, não estar em opt-out e conversa ativa quando
        require_active=True.

    campaign:
        exige opt-in e não estar em opt-out, mas não exige
        conversation_active.
    """

    phone = str(phone).strip()
    message = str(message or "").strip()
    send_mode = str(send_mode or "").strip().lower()

    if send_mode not in ("service", "campaign"):
        raise ValueError(
            "send_mode deve ser 'service' ou 'campaign'"
        )

    if not phone:
        raise ValueError("Telefone não informado.")

    if not message and not media_path:
        raise ValueError(
            "Mensagem vazia e nenhuma mídia informada."
        )

    expire_inactive()

    with _lock:
        c = connect()

        r = c.execute(
            """
            SELECT *
            FROM contacts
            WHERE phone=?
            """,
            (phone,),
        ).fetchone()

        if not r:
            c.close()

            return {
                "accepted": False,
                "reason": "contato_nao_cadastrado",
            }

        if not r["opt_in"]:
            event(
                c,
                phone,
                "blocked",
                "Sem opt-in explícito",
            )

            c.commit()
            c.close()

            return {
                "accepted": False,
                "reason": "sem_opt_in",
            }

        if r["opt_out"]:
            event(
                c,
                phone,
                "blocked",
                "Opt-out explícito",
            )

            c.commit()
            c.close()

            return {
                "accepted": False,
                "reason": "opt_out",
            }

        if (
            send_mode == "service"
            and require_active
            and not r["conversation_active"]
        ):
            event(
                c,
                phone,
                "blocked",
                "Conversa inativa",
            )

            c.commit()
            c.close()

            return {
                "accepted": False,
                "reason": "conversa_inativa",
            }

        q = str(uuid.uuid4())

        c.execute(
            """
            INSERT INTO queue(
                id,
                phone,
                message,
                status,
                reason,
                send_mode,
                media_path,
                media_name,
                media_type,
                media_mimetype,
                media_caption,
                created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                q,
                phone,
                message,
                "pending",
                "",
                send_mode,
                media_path,
                media_name,
                media_type,
                media_mimetype,
                media_caption,
                iso(now()),
            ),
        )

        event(
            c,
            phone,
            "queued",
            q,
        )

        c.commit()
        c.close()

        return {
            "accepted": True,
            "queue_id": q,
            "send_mode": send_mode,
        }


def claim_next():
    """
    Retira da fila o próximo item elegível.

    Regras:
      - opt_in obrigatoriamente 1
      - opt_out obrigatoriamente 0
      - service exige conversation_active=1
      - campaign não exige conversation_active
    """

    expire_inactive()

    with _lock:
        c = connect()

        r = c.execute(
            """
            SELECT
                q.*,
                c.opt_in,
                c.opt_out,
                c.conversation_active
            FROM queue q
            JOIN contacts c
              ON c.phone=q.phone
            WHERE q.status='pending'
            ORDER BY q.created_at
            LIMIT 1
            """
        ).fetchone()

        if not r:
            c.close()
            return None

        if not r["opt_in"]:
            c.execute(
                """
                UPDATE queue
                SET
                    status=?,
                    reason=?
                WHERE id=?
                """,
                (
                    "blocked",
                    "Sem opt-in explícito",
                    r["id"],
                ),
            )

            event(
                c,
                r["phone"],
                "blocked",
                "Fila bloqueada: sem opt-in",
            )

            c.commit()
            c.close()

            return None

        if r["opt_out"]:
            c.execute(
                """
                UPDATE queue
                SET
                    status=?,
                    reason=?
                WHERE id=?
                """,
                (
                    "blocked",
                    "Opt-out explícito",
                    r["id"],
                ),
            )

            event(
                c,
                r["phone"],
                "blocked",
                "Fila bloqueada: opt-out",
            )

            c.commit()
            c.close()

            return None

        if (
            r["send_mode"] == "service"
            and not r["conversation_active"]
        ):
            c.execute(
                """
                UPDATE queue
                SET
                    status=?,
                    reason=?
                WHERE id=?
                """,
                (
                    "blocked",
                    "Conversa inativa",
                    r["id"],
                ),
            )

            event(
                c,
                r["phone"],
                "blocked",
                "Fila bloqueada: conversa inativa",
            )

            c.commit()
            c.close()

            return None

        c.execute(
            """
            UPDATE queue
            SET
                status=?,
                started_at=?
            WHERE id=?
            """,
            (
                "processing",
                iso(now()),
                r["id"],
            ),
        )

        c.commit()
        c.close()

        return dict(r)


def mark_pending(queue_id, evolution_message_id):
    with _lock:
        c = connect()

        c.execute(
            """
            UPDATE queue
            SET
                status=?,
                evolution_message_id=?,
                sent_at=?,
                delivery_status=?
            WHERE id=?
            """,
            (
                "sent",
                evolution_message_id,
                iso(now()),
                "PENDING",
                queue_id,
            ),
        )

        row = c.execute(
            """
            SELECT phone
            FROM queue
            WHERE id=?
            """,
            (queue_id,),
        ).fetchone()

        if row:
            c.execute(
                """
                UPDATE contacts
                SET
                    last_outgoing_at=?,
                    total_outgoing=total_outgoing + 1,
                    updated_at=?
                WHERE phone=?
                """,
                (
                    iso(now()),
                    iso(now()),
                    row["phone"],
                ),
            )

            event(
                c,
                row["phone"],
                "sent",
                evolution_message_id or "",
            )

        c.commit()
        c.close()


def mark_failed(queue_id, error):
    with _lock:
        c = connect()

        row = c.execute(
            """
            SELECT phone
            FROM queue
            WHERE id=?
            """,
            (queue_id,),
        ).fetchone()

        c.execute(
            """
            UPDATE queue
            SET
                status=?,
                error=?
            WHERE id=?
            """,
            (
                "failed",
                str(error or ""),
                queue_id,
            ),
        )

        if row:
            event(
                c,
                row["phone"],
                "failed",
                str(error or ""),
            )

        c.commit()
        c.close()


def update_message_status(evolution_message_id, status):
    """
    Atualiza o status de entrega/leitura recebido da Evolution API.
    """

    evolution_message_id = str(
        evolution_message_id or ""
    ).strip()

    status = str(status or "").strip().upper()

    if not evolution_message_id:
        return False

    if not status:
        return False

    with _lock:
        c = connect()

        row = c.execute(
            """
            SELECT id, phone
            FROM queue
            WHERE evolution_message_id=?
            LIMIT 1
            """,
            (evolution_message_id,),
        ).fetchone()

        if not row:
            c.close()
            return False

        t = iso(now())

        if status in ("DELIVERY_ACK", "DELIVERED"):
            c.execute(
                """
                UPDATE queue
                SET
                    delivery_status=?,
                    delivered_at=COALESCE(
                        delivered_at,
                        ?
                    )
                WHERE evolution_message_id=?
                """,
                (
                    status,
                    t,
                    evolution_message_id,
                ),
            )

        elif status in ("READ", "PLAYED"):
            c.execute(
                """
                UPDATE queue
                SET
                    delivery_status=?,
                    read_at=COALESCE(
                        read_at,
                        ?
                    )
                WHERE evolution_message_id=?
                """,
                (
                    status,
                    t,
                    evolution_message_id,
                ),
            )

        else:
            c.execute(
                """
                UPDATE queue
                SET
                    delivery_status=?
                WHERE evolution_message_id=?
                """,
                (
                    status,
                    evolution_message_id,
                ),
            )

        event(
            c,
            row["phone"],
            "message_status",
            f"{evolution_message_id}: {status}",
        )

        c.commit()
        c.close()

        return True


def list_queue(limit=100):
    c = connect()

    rows = c.execute(
        """
        SELECT *
        FROM queue
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    result = [dict(row) for row in rows]

    c.close()

    return result


def dashboard():
    c = connect()

    result = {}

    for status in (
        "pending",
        "processing",
        "sent",
        "failed",
        "blocked",
    ):
        row = c.execute(
            """
            SELECT COUNT(*) AS total
            FROM queue
            WHERE status=?
            """,
            (status,),
        ).fetchone()

        result[status] = int(row["total"])

    row = c.execute(
        """
        SELECT COUNT(*) AS total
        FROM contacts
        """
    ).fetchone()

    result["contacts"] = int(row["total"])

    row = c.execute(
        """
        SELECT COUNT(*) AS total
        FROM contacts
        WHERE opt_in=1
        """
    ).fetchone()

    result["opted_in"] = int(row["total"])

    row = c.execute(
        """
        SELECT COUNT(*) AS total
        FROM contacts
        WHERE conversation_active=1
        """
    ).fetchone()

    result["active_conversations"] = int(row["total"])

    c.close()

    return result


# Inicializa o banco quando o módulo é carregado.
init_db()
