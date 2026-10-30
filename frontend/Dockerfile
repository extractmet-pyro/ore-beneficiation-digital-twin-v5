# Operator desk v2 — nginx static container (on-prem control rooms, Render Docker, Kubernetes).
# docker build -t mdt-web . && docker run -p 8080:8080 -e BACKEND_BASE_URL=https://… mdt-web
FROM node:20-alpine AS config
WORKDIR /app
COPY . .
FROM nginx:1.27-alpine
RUN apk add --no-cache nodejs
ENV PORT=8080
COPY --from=config /app /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
RUN rm -f /usr/share/nginx/html/nginx.conf /usr/share/nginx/html/Dockerfile && rm -rf /usr/share/nginx/html/node_modules /usr/share/nginx/html/tests
# write config.js from container env at start-up, then hand over to the stock nginx entrypoint (envsubst for $PORT)
RUN printf '#!/bin/sh\nset -e\ncd /usr/share/nginx/html && node scripts/write-config.mjs\nexec /docker-entrypoint.sh "$@"\n' > /start.sh && chmod +x /start.sh
EXPOSE 8080
ENTRYPOINT ["/start.sh"]
CMD ["nginx", "-g", "daemon off;"]
