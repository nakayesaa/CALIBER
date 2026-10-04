FROM node:22.16-bookworm-slim AS web
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
ENV VITE_API_BASE_URL=/api/v1 VITE_DEMO_AUTH=true
RUN npm run build --workspace=@caliber/web

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 CALIBER_LLM_ENABLED=false CALIBER_WRITE_MODE=local OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY services/api/requirements.lock deployment/requirements.txt ./deployment/
RUN pip install --no-cache-dir -r deployment/requirements.lock -r deployment/requirements.txt
COPY services services
COPY deployment deployment
COPY --from=web /build/apps/web/dist apps/web/dist
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn deployment.runtime:create_deployment_app --factory --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
