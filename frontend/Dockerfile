# Derleme asamasi: node yalnizca burada gerekli, son imaja girmiyor.
FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Farkli bir host-a deploy ederken adres burada verilir:
#   docker build --build-arg VITE_API_URL=https://api.ornek.com ./frontend
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

COPY . .
RUN npm run build

# Sunum asamasi: uretilen statik dosyalari nginx servis eder.
# Uygulama tek sayfa ve client-side routing kullanmiyor, bu yuzden nginx'in
# varsayilan yapilandirmasi yeterli - ayri bir nginx.conf'a gerek yok.
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
