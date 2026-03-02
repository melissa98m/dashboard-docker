FROM node:20-alpine

WORKDIR /app

ARG NEXT_PUBLIC_API_URL=
ARG API_UPSTREAM_URL=http://dashboard-api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV API_UPSTREAM_URL=$API_UPSTREAM_URL

COPY dashboard-web/package.json dashboard-web/package-lock.json* ./
RUN npm install

COPY dashboard-web/ .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
