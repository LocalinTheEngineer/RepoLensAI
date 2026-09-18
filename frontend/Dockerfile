# Derleme asamasi: node yalnizca burada gerekli, son imaja girmiyor.
FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Sunum asamasi: uretilen statik dosyalari nginx servis eder.
# Uygulama tek sayfa ve client-side routing kullanmiyor, bu yuzden nginx'in
# varsayilan yapilandirmasi yeterli - ayri bir nginx.conf'a gerek yok.
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
