import socket
import os
import time
import requests

HOST = "0.0.0.0"
PORT = 1337
FLAG = "flag{a70526764755d9fd890c030d71a1c559}"

ORCH_URL = os.getenv("ORCH_URL")
SESSION_ID = os.getenv("SESSION_ID")
USER_ID = os.getenv("USER_ID")
CHALLENGE_ID = os.getenv("CHALLENGE_ID")


def send_event(event_type, payload=None):
    if not ORCH_URL:
        return

    params = {
        "event_type": event_type,
        "user_key": USER_ID,
        "challenge_id": CHALLENGE_ID,
        "session_id": SESSION_ID
    }

    if payload:
        for k, v in payload.items():
            params[k] = str(v)

    try:
        requests.post(ORCH_URL, params=params, timeout=0.3)
    except Exception:
        pass


def send(conn, text: str):
    conn.sendall(text.encode())


def send_slow(conn, text: str, delay: float = 0.0025):
    for ch in text:
        conn.sendall(ch.encode())
        time.sleep(delay)


def recv_line(conn):
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(1024)
        if not chunk:
            return None
        data += chunk
        if len(data) > 4096:
            break
    return data.decode(errors="ignore").strip()


def prompt(conn):
    send(conn, "\nproto> ")


def show_banner(conn):
    send(
        conn,
        "\n"
        "┌──────────────────────────────────────┐\n"
        "│       GHOST PROTOCOL INTERFACE       │\n"
        "│             PROTO/1.0                │\n"
        "└──────────────────────────────────────┘\n\n"
    )
    send_slow(conn, "[+] Establishing link .......... OK\n")
    send_slow(conn, "[+] Loading protocol profile ... OK\n")
    send_slow(conn, "[+] Session telemetry enabled .. OK\n\n")
    send(conn, "Handshake must be completed before authentication.\n")
    send(conn, "Type HELP for available commands.\n")


def show_help(conn, step):
    send(conn, "\n[HELP]\n")
    send(conn, "  HELLO           Begin handshake\n")
    send(conn, "  AUTH <token>    Authenticate after handshake\n")
    send(conn, "  STATUS          Show interface state\n")
    send(conn, "  HELP            Show this message\n")
    send(conn, "  EXIT            Close session\n")
    send(conn, f"  Current phase   {step}\n")


def show_status(conn, step):
    send(conn, "\n[STATUS]\n")
    send(conn, "  protocol        PROTO/1.0\n")
    send(conn, f"  phase           {step}\n")
    send(conn, "  auth_gateway    locked\n" if step == "hello" else "  auth_gateway    unlocked\n")
    send(conn, "  mode            restricted\n")


def handle(conn, addr):
    send_event("TCP_CONNECT", {"ip": addr[0]})

    try:
        show_banner(conn)
        step = "hello"
        bad_auth_count = 0
        prompt(conn)

        while True:
            msg = recv_line(conn)
            if msg is None:
                break

            msg = msg.strip()
            upper = msg.upper()

            send_event("TCP_INPUT", {"input": msg, "step": step})

            if upper == "EXIT":
                send(conn, "\n[INFO] Session terminated.\n")
                break

            if upper == "HELP":
                show_help(conn, step)
                prompt(conn)
                continue

            if upper == "STATUS":
                show_status(conn, step)
                prompt(conn)
                continue

            if step == "hello":
                if msg == "HELLO":
                    send_event("TCP_HELLO_OK")
                    send(conn, "\n[OK] Handshake accepted.\n")
                    send(conn, "[INFO] Authentication gateway unlocked.\n")
                    send(conn, "[NEXT] Send: AUTH <token>\n")
                    step = "auth"
                    prompt(conn)
                else:
                    send_event("TCP_BAD_HELLO")
                    send(conn, "\n[ERR] Invalid handshake.\n")
                    send(conn, "[HINT] Expected command: HELLO\n")
                    prompt(conn)

            elif step == "auth":
                if msg.startswith("AUTH "):
                    token = msg.split(" ", 1)[1]
                    send_event("TCP_AUTH_ATTEMPT", {"token": token})

                    if token == "letmein-proto":
                        send_event("FLAG_FOUND")
                        send(conn, "\n[OK] Authentication successful.\n")
                        send_slow(conn, "[INFO] Releasing secure payload ...\n", 0.003)
                        send(conn, f"[FLAG] {FLAG}\n")
                        send(conn, "[INFO] Remote host closed the session.\n")
                        break
                    else:
                        bad_auth_count += 1
                        send_event("TCP_BAD_AUTH")
                        send(conn, "\n[DENY] Invalid token.\n")
                        if bad_auth_count >= 3:
                            send(conn, "[WARN] Multiple authentication failures detected.\n")
                        else:
                            send(conn, "[HINT] Token format is correct, but the value is not.\n")
                        prompt(conn)
                else:
                    send_event("TCP_MALFORMED")
                    send(conn, "\n[ERR] Malformed command.\n")
                    send(conn, "[USAGE] AUTH <token>\n")
                    prompt(conn)

    finally:
        send_event("TCP_DISCONNECT")
        conn.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"Listening on {HOST}:{PORT}", flush=True)

        while True:
            conn, addr = s.accept()
            handle(conn, addr)


if __name__ == "__main__":
    main()
