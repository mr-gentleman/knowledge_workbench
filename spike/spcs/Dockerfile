# Build context = repo root (the image needs app/). See deploy.sh.
FROM --platform=linux/amd64 node:22-slim AS web
WORKDIR /web
COPY spike/spcs/web/package.json spike/spcs/web/package-lock.json ./
RUN npm ci
COPY spike/spcs/web/ ./
RUN npm run build

FROM --platform=linux/amd64 python:3.11-slim
WORKDIR /srv
COPY spike/spcs/api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY app/ app/
COPY spike/spcs/api/ api/
COPY --from=web /web/dist web/dist
ENV KW_WEB_DIST=/srv/web/dist PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "api.main:api", "--host", "0.0.0.0", "--port", "8080"]
