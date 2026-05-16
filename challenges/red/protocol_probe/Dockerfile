FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY server.py .
EXPOSE 1337
CMD ["python", "-u", "server.py"]
