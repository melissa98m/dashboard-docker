FROM node:20-alpine

WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY dashboard-web/package.json dashboard-web/package-lock.json* ./
RUN npm install

COPY dashboard-web/ .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
