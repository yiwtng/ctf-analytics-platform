FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update && \
    apt-get install -y openssh-server bash coreutils findutils grep sed procps curl && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && \
    useradd -m -s /bin/bash player && \
    echo 'player:player123' | chpasswd && \
    mkdir -p /home/player/notes /home/player/.cache/sessions /srv/backups/.staging /opt/internal && \
    chown -R player:player /home/player

COPY files/ctf-telemetry /usr/local/bin/ctf-telemetry
COPY files/ctf-shell /usr/local/bin/ctf-shell
COPY files/ctf-bashrc /etc/ctf-bashrc
COPY files/bashrc_player /home/player/.bashrc
COPY files/motd.txt /opt/internal/motd.txt
COPY files/notes/ /home/player/notes/
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh /usr/local/bin/ctf-telemetry /usr/local/bin/ctf-shell && \
    chmod 644 /etc/ctf-bashrc && \
    chown player:player /home/player/.bashrc && \
    chown -R player:player /home/player/notes && \
    usermod -s /usr/local/bin/ctf-shell player

RUN printf '%s\n' \
    'Port 22' \
    'PermitRootLogin no' \
    'PasswordAuthentication yes' \
    'PubkeyAuthentication no' \
    'ChallengeResponseAuthentication no' \
    'UsePAM no' \
    'X11Forwarding no' \
    'PrintMotd no' \
    'PrintLastLog no' \
    'AcceptEnv LANG LC_*' \
    'Subsystem sftp /usr/lib/openssh/sftp-server' \
    > /etc/ssh/sshd_config

EXPOSE 22

CMD ["/entrypoint.sh"]
