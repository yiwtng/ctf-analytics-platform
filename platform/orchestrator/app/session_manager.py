import docker
import json
import os
import random
import socket
import uuid

from app.events import write_event

client = docker.from_env()

BASE_PATH = "/app/challenges"
TRAEFIK_NETWORK = os.getenv("DOCKER_NETWORK", "ctf_edge")
WEB_BASE_DOMAIN = os.getenv("WEB_BASE_DOMAIN")
ORCH_PUBLIC_BASE = os.getenv("ORCH_PUBLIC_BASE")
PUBLIC_NC_HOST = os.getenv("PUBLIC_NC_HOST")
PUBLIC_SSH_HOST = os.getenv("PUBLIC_SSH_HOST")


def load_challenge(challenge_id: str):
    for root, _, files in os.walk(BASE_PATH):
        if "challenge.json" in files:
            path = os.path.join(root, "challenge.json")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data["id"] == challenge_id:
                    return data, root
    return None, None

def _port_in_use(host_port: int) -> bool:
    containers = client.containers.list(all=True)
    for c in containers:
        ports = c.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for _, bindings in ports.items():
            if not bindings:
                continue
            for b in bindings:
                try:
                    if int(b["HostPort"]) == host_port:
                        return True
                except Exception:
                    pass
    return False


def _tcp_bindable(host_port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", host_port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def find_free_port(start: int, end: int, max_tries: int = 200) -> int:
    candidates = list(range(start, end + 1))
    random.shuffle(candidates)

    for port in candidates[:max_tries]:
        if not _port_in_use(port) and _tcp_bindable(port):
            return port

    raise RuntimeError(f"No free ports available in range {start}-{end}")


def cleanup_old_sessions(user_id: str, challenge_id: str) -> None:
    prefix = f"sess-{user_id}-{challenge_id}"
    for c in client.containers.list(all=True, filters={"name": prefix}):
        try:
            c.remove(force=True)
        except Exception:
            pass


def build_env_vars(session_id: str, user_id: str, challenge_id: str) -> dict:
    return {
        "SESSION_ID": session_id,
        "USER_ID": user_id,
        "CHALLENGE_ID": challenge_id,
        "ORCH_URL": f"{ORCH_PUBLIC_BASE}/event"
    }


def start_session(user_id: str, challenge_id: str):
    challenge, _ = load_challenge(challenge_id)
    if not challenge:
        return {"status": "error", "message": "challenge not found"}

    cleanup_old_sessions(user_id, challenge_id)

    session_id = str(uuid.uuid4())[:8]
    image_name = f"challenge-{challenge_id}"
    container_name = f"sess-{user_id}-{challenge_id}-{session_id}"

    env_vars = build_env_vars(session_id, user_id, challenge_id)
    labels = {}
    ports = {}
    public_port = None

    chal_type = challenge["type"]
    internal_port = int(challenge["internal_port"])

    # WEB
    if chal_type == "web":
        host_name = f"u-{session_id}.{WEB_BASE_DOMAIN}"
        labels = {
            "traefik.enable": "true",
            "traefik.docker.network": TRAEFIK_NETWORK,
            f"traefik.http.routers.{container_name}.rule": f"Host(`{host_name}`)",
            f"traefik.http.routers.{container_name}.entrypoints": "web",
            f"traefik.http.services.{container_name}.loadbalancer.server.port": str(internal_port),
        }

        client.containers.run(
            image_name,
            name=container_name,
            detach=True,
            labels=labels,
            mem_limit=challenge.get("mem_limit", "512m"),
            nano_cpus=int(float(challenge.get("cpu_limit", "0.5")) * 1e9),
            network=TRAEFIK_NETWORK,
            environment=env_vars,
        )

        write_event(
            event_type="SESSION_START",
            user_key=user_id,
            challenge_id=challenge_id,
            session_id=session_id,
            payload={
                "container_name": container_name,
                "challenge_type": chal_type,
                "image": image_name,
                "host_name": host_name
            }
        )

        return {
            "status": "ok",
            "type": "web",
            "url": f"http://{host_name}",
            "session_id": session_id
        }

    # NC
    if chal_type == "nc":
        public_port = find_free_port(31001, 31999)
        ports = {f"{internal_port}/tcp": public_port}

        client.containers.run(
            image_name,
            name=container_name,
            detach=True,
            ports=ports,
            mem_limit=challenge.get("mem_limit", "512m"),
            nano_cpus=int(float(challenge.get("cpu_limit", "0.5")) * 1e9),
            environment=env_vars,
        )

        write_event(
            event_type="SESSION_START",
            user_key=user_id,
            challenge_id=challenge_id,
            session_id=session_id,
            payload={
                "container_name": container_name,
                "challenge_type": chal_type,
                "image": image_name,
                "public_port": public_port
            }
        )

        return {
            "status": "ok",
            "type": "nc",
            "host": PUBLIC_NC_HOST,
            "port": public_port,
            "session_id": session_id
        }

    # SSH
    if chal_type == "ssh":
        public_port = find_free_port(32223, 32999)
        ports = {f"{internal_port}/tcp": public_port}

        client.containers.run(
            image_name,
            name=container_name,
            detach=True,
            ports=ports,
            mem_limit=challenge.get("mem_limit", "512m"),
            nano_cpus=int(float(challenge.get("cpu_limit", "0.5")) * 1e9),
            environment=env_vars,
        )

        write_event(
            event_type="SESSION_START",
            user_key=user_id,
            challenge_id=challenge_id,
            session_id=session_id,
            payload={
                "container_name": container_name,
                "challenge_type": chal_type,
                "image": image_name,
                "public_port": public_port
            }
        )

        return {
            "status": "ok",
            "type": "ssh",
            "host": PUBLIC_SSH_HOST,
            "port": public_port,
            "username": "player",
            "password": "player123",
            "session_id": session_id
        }

    return {"status": "error", "message": f"unsupported challenge type: {chal_type}"}


def stop_session(session_id: str):
    containers = client.containers.list(all=True)

    for c in containers:
        if session_id in c.name:
            try:
                c.stop()
                c.remove(force=True)
                write_event(
                    event_type="SESSION_STOP",
                    session_id=session_id,
                    payload={"container_name": c.name}
                )
                return {"status": "ok", "message": f"session {session_id} stopped"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "session not found"}